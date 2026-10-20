"""Acquire one target Douyin work in an isolated, bounded browser process."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import Any
from urllib.parse import urlsplit

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Request, Route, async_playwright
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from app.config import Settings
from app.errors import AppError
from app.parser.client import Deadline
from app.parser.douyin.egress_proxy import BoundedConnectProxy
from app.parser.douyin.state_reader import decode_detail_response, decode_flight_detail
from app.parser.douyin.url_rules import PAGE_HOSTS, ParsedDouyinUrl, parse_douyin_url

SCRIPT_HOSTS = frozenset(
    {
        "lf-c-flwb.bytetos.com",
        "lf-cdn-tos.bytescm.com",
        "lf-douyin-pc-web.douyinstatic.com",
        "lf-rc1.yhgfb-cn-static.com",
        "lf-security.bytegoofy.com",
        "lf-static.applogcdn.com",
        "lf-zt.douyin.com",
        "lf3-pendah.bytetos.com",
        "lf3-static.bytednsdoc.com",
        "lf3-webcast.bytetos.com",
        "lf9-sec.bytetos.com",
        "sf1-cdn-tos.douyinstatic.com",
    }
)
ALLOWED_EGRESS_HOSTS = PAGE_HOSTS | SCRIPT_HOSTS
ALLOWED_RESOURCE_TYPES = frozenset({"document", "script", "xhr", "fetch"})
MAX_SCRIPT_ELEMENTS = 1_000


class DouyinBrowser:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._semaphore = asyncio.Semaphore(settings.douyin_browser_concurrency)

    async def fetch_detail(self, raw_url: str, deadline: Deadline) -> tuple[str, dict[str, Any]]:
        initial = parse_douyin_url(raw_url)
        acquired = False
        try:
            await asyncio.wait_for(self._semaphore.acquire(), deadline.remaining())
            acquired = True
        except TimeoutError as exc:
            raise AppError("BUSY", 503, True, "Douyin browser queue timed out", 2) from exc
        try:
            try:
                return await asyncio.wait_for(
                    self._fetch_once(initial, deadline), deadline.remaining()
                )
            except TimeoutError as exc:
                raise AppError("UPSTREAM_TIMEOUT", 504, True, "Douyin browser timed out") from exc
            except OSError as exc:
                raise AppError(
                    "UPSTREAM_BAD_RESPONSE", 502, True, "Douyin browser transport failed"
                ) from exc
        finally:
            if acquired:
                self._semaphore.release()

    async def _fetch_once(
        self, initial: ParsedDouyinUrl, deadline: Deadline
    ) -> tuple[str, dict[str, Any]]:
        request_count = 0
        response_tasks: set[asyncio.Task[None]] = set()
        captured_details: dict[str, dict[str, Any]] = {}
        detail_event = asyncio.Event()
        blocked_navigation_error: AppError | None = None

        async with BoundedConnectProxy(
            ALLOWED_EGRESS_HOSTS,
            self.settings.douyin_browser_max_bytes,
            self.settings.connect_timeout_seconds,
        ) as proxy:
            playwright_manager = async_playwright()
            playwright = None
            browser = None
            try:
                playwright = await playwright_manager.start()
                launch_options: dict[str, object] = {
                    "headless": True,
                    # The bundled headless shell has no Linux sandbox helper.
                    # The Chromium channel selects the full bundled browser,
                    # whose helper is configured in the container image.
                    "channel": self.settings.douyin_browser_channel or "chromium",
                    "chromium_sandbox": True,
                    "proxy": {"server": proxy.server_url},
                    "args": [
                        "--disable-background-networking",
                        "--disable-component-update",
                        "--disable-default-apps",
                        "--disable-features=MediaRouter,OptimizationHints,WebRtcAllowInputVolumeAdjustment",
                        "--disable-quic",
                        "--disable-sync",
                        "--no-first-run",
                        "--no-pings",
                    ],
                }
                browser = await playwright.chromium.launch(**launch_options)  # type: ignore[arg-type]
                context = await browser.new_context(
                    locale="zh-CN",
                    timezone_id="Asia/Shanghai",
                    viewport={"width": 1280, "height": 900},
                    service_workers="block",
                )
                try:
                    page = await context.new_page()

                    async def control(route: Route, request: Request) -> None:
                        nonlocal blocked_navigation_error, request_count
                        request_count += 1
                        if request_count > self.settings.douyin_browser_max_requests:
                            await route.abort("blockedbyclient")
                            return
                        parts = urlsplit(request.url)
                        host = parts.hostname
                        if (
                            parts.scheme != "https"
                            or host not in ALLOWED_EGRESS_HOSTS
                            or request.resource_type not in ALLOWED_RESOURCE_TYPES
                        ):
                            await route.abort("blockedbyclient")
                            return
                        if request.resource_type == "document":
                            try:
                                parse_douyin_url(request.url)
                            except AppError:
                                blocked_navigation_error = _blocked_document_error(request.url)
                                await route.abort("blockedbyclient")
                                return
                        elif (request.resource_type == "script" and host not in SCRIPT_HOSTS) or (
                            request.resource_type in {"xhr", "fetch"} and host != "www.douyin.com"
                        ):
                            await route.abort("blockedbyclient")
                            return
                        await route.continue_()

                    await page.route("**/*", control)

                    async def capture_detail(response: Any) -> None:
                        if urlsplit(response.url).path != "/aweme/v1/web/aweme/detail/":
                            return
                        try:
                            candidate_id = _item_id_from_detail_url(response.url)
                            if candidate_id is None:
                                return
                            content_length = await response.header_value("content-length")
                            if (
                                content_length is not None
                                and content_length.isascii()
                                and content_length.isdigit()
                                and int(content_length) > self.settings.douyin_state_max_bytes
                            ):
                                return
                            raw = await response.body()
                            detail = decode_detail_response(
                                raw, candidate_id, self.settings.douyin_state_max_bytes
                            )
                            if detail is not None:
                                captured_details[candidate_id] = detail
                                detail_event.set()
                        except (AppError, PlaywrightError):
                            return

                    def schedule_capture(response: Any) -> None:
                        task = asyncio.create_task(capture_detail(response))
                        response_tasks.add(task)
                        task.add_done_callback(response_tasks.discard)

                    page.on("response", schedule_capture)
                    timeout_ms = max(1, int(deadline.remaining() * 1000))
                    try:
                        response = await page.goto(
                            initial.normalized_url,
                            wait_until="domcontentloaded",
                            timeout=timeout_ms,
                        )
                    except PlaywrightError as exc:
                        if blocked_navigation_error is not None:
                            raise blocked_navigation_error from exc
                        raise
                    if response is None or response.status >= 400:
                        raise AppError(
                            "UPSTREAM_BAD_RESPONSE",
                            502,
                            response is not None and response.status >= 500,
                            "Douyin navigation failed",
                        )
                    final = parse_douyin_url(page.url)
                    if final.item_id is None or final.kind is None:
                        raise AppError(
                            "UPSTREAM_BAD_RESPONSE",
                            502,
                            detail="Douyin short link did not resolve",
                        )
                    if initial.item_id is not None and initial.item_id != final.item_id:
                        raise AppError(
                            "PARSE_FAILED", 502, detail="Douyin redirect target mismatch"
                        )
                    scripts = await _bounded_script_texts(
                        page, self.settings.douyin_state_max_bytes
                    )
                    detail = decode_flight_detail(
                        scripts, final.item_id, self.settings.douyin_state_max_bytes
                    )
                    if detail is None:
                        wait_seconds = min(7.0, deadline.remaining())
                        detail = await _wait_for_target_detail(
                            captured_details,
                            detail_event,
                            final.item_id,
                            wait_seconds,
                        )
                    if detail is None:
                        text = await page.locator("body").evaluate(
                            "element => (element.innerText || '').slice(0, 10000)"
                        )
                        if not isinstance(text, str):
                            text = ""
                        _classify_missing_page(page.url, text)
                        raise AppError("PARSE_FAILED", 502, detail="Douyin target detail absent")
                    return final.item_id, detail
                finally:
                    with suppress(Exception):
                        await asyncio.wait_for(context.close(), 2)
            except PlaywrightTimeoutError as exc:
                raise AppError("UPSTREAM_TIMEOUT", 504, True, "Douyin browser timed out") from exc
            except PlaywrightError as exc:
                raise AppError(
                    "UPSTREAM_BAD_RESPONSE", 502, True, "Douyin browser process failed"
                ) from exc
            finally:
                for task in response_tasks:
                    task.cancel()
                if response_tasks:
                    with suppress(Exception):
                        await asyncio.gather(*response_tasks, return_exceptions=True)
                if browser is not None:
                    with suppress(Exception):
                        await asyncio.wait_for(browser.close(), 3)
                if playwright is not None:
                    with suppress(Exception):
                        await asyncio.wait_for(playwright.stop(), 3)


async def _bounded_script_texts(page: Any, max_bytes: int) -> list[str]:
    locator = page.locator("script")
    remaining = max_bytes
    scripts: list[str] = []
    expression = """
        (element, limit) => {
            const text = element.textContent || "";
            return new TextEncoder().encode(text).length > limit ? null : text;
        }
    """
    index = 0
    while True:
        count = await locator.count()
        if count > MAX_SCRIPT_ELEMENTS:
            raise AppError("UPSTREAM_BAD_RESPONSE", 502, detail="too many Douyin script elements")
        while index < count:
            text = await locator.nth(index).evaluate(expression, remaining)
            if not isinstance(text, str):
                raise AppError(
                    "UPSTREAM_BAD_RESPONSE", 502, detail="Douyin page state exceeds limit"
                )
            size = len(text.encode("utf-8"))
            if size > remaining:
                raise AppError(
                    "UPSTREAM_BAD_RESPONSE", 502, detail="Douyin page state exceeds limit"
                )
            remaining -= size
            scripts.append(text)
            index += 1
        if await locator.count() == count:
            return scripts


async def _wait_for_target_detail(
    captured: dict[str, dict[str, Any]],
    event: asyncio.Event,
    target_id: str,
    timeout: float,
) -> dict[str, Any] | None:
    loop = asyncio.get_running_loop()
    end = loop.time() + timeout
    while True:
        detail = captured.get(target_id)
        if detail is not None:
            return detail
        event.clear()
        detail = captured.get(target_id)
        if detail is not None:
            return detail
        remaining = end - loop.time()
        if remaining <= 0:
            return None
        try:
            await asyncio.wait_for(event.wait(), remaining)
        except TimeoutError:
            return None


def _item_id_from_detail_url(url: str) -> str | None:
    from urllib.parse import parse_qs

    values = parse_qs(urlsplit(url).query).get("aweme_id", [])
    value = values[0] if values else None
    if value is not None and value.isdigit() and 18 <= len(value) <= 20:
        return value
    return None


def _classify_missing_page(url: str, text: str) -> None:
    lowered = text.lower()
    path = urlsplit(url).path.lower()
    if any(marker in text for marker in ("作品已删除", "作品不存在", "内容已下架")):
        raise AppError("NOTE_NOT_FOUND", 404, detail="Douyin explicitly reported missing work")
    if "/login" in path or any(marker in text for marker in ("登录后查看该作品", "请先登录后查看")):
        raise AppError("UPSTREAM_LOGIN_REQUIRED", 503, detail="Douyin requires login")
    if any(marker in lowered for marker in ("captcha", "verify-page")) or any(
        marker in text for marker in ("安全验证", "完成验证")
    ):
        raise AppError("UPSTREAM_ACCESS_RESTRICTED", 503, detail="Douyin verification challenge")


def _blocked_document_error(url: str) -> AppError:
    path = urlsplit(url).path.lower()
    if path == "/login" or path.startswith("/login/"):
        return AppError("UPSTREAM_LOGIN_REQUIRED", 503, detail="Douyin redirected to login")
    if "captcha" in path or "verify" in path:
        return AppError(
            "UPSTREAM_ACCESS_RESTRICTED", 503, detail="Douyin redirected to verification"
        )
    return AppError("INVALID_URL", 400, detail="unsafe Douyin document redirect")
