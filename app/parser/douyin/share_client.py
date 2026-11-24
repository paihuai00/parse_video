"""Acquire ordinary Douyin videos through their public mobile share pages."""

from __future__ import annotations

import asyncio
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from curl_cffi import CurlECode, CurlError, CurlOpt
from curl_cffi.curl import CURL_WRITEFUNC_ERROR
from curl_cffi.requests import AsyncSession, Response

from app.config import Settings
from app.errors import AppError, invalid_url
from app.models import InternalNote
from app.parser.client import REDIRECT_STATUSES, Deadline
from app.parser.douyin.media import (
    VIDEO_HOSTS,
    normalize_douyin_media_url,
    normalize_share_video,
)
from app.parser.douyin.state_reader import classify_douyin_page_text, decode_share_detail
from app.parser.douyin.url_rules import (
    PAGE_HOSTS,
    SHARE_HOST,
    ParsedDouyinUrl,
    douyin_https_parts,
    parse_douyin_url,
)
from app.parser.url_rules import resolve_public_addresses

SHARE_ORIGIN = f"https://{SHARE_HOST}/"
PLAY_HOST = "aweme.snssdk.com"
PLAY_PATHS = frozenset({"/aweme/v1/playwm/", "/aweme/v1/play/"})
SHARE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
    ),
    "Referer": SHARE_ORIGIN,
    "Accept": "text/html,application/xhtml+xml",
}


class _PageText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hidden_tag: str | None = None
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self.hidden_tag = tag

    def handle_endtag(self, tag: str) -> None:
        if tag == self.hidden_tag:
            self.hidden_tag = None

    def handle_data(self, data: str) -> None:
        if self.hidden_tag is None:
            self.parts.append(data)


def _classify_page(url: str, html: str) -> None:
    reader = _PageText()
    reader.feed(html)
    reader.close()
    text = " ".join(reader.parts)
    if any(
        marker in text.lower() for marker in ("访问过于频繁", "请求过于频繁", "too many requests")
    ):
        raise AppError("UPSTREAM_RATE_LIMITED", 503, True, "Douyin rate limited", 30)
    classify_douyin_page_text(url, text)


def _check_status(response: Response, *, work_page: bool = False) -> None:
    status = response.status_code
    if status == 200 or status in REDIRECT_STATUSES:
        return
    if status == 429:
        raise AppError("UPSTREAM_RATE_LIMITED", 503, True, "Douyin rate limited", 30)
    if status == 401:
        raise AppError("UPSTREAM_LOGIN_REQUIRED", 503, detail="Douyin requires login")
    if status == 403:
        raise AppError("UPSTREAM_ACCESS_RESTRICTED", 503, detail="Douyin denied access")
    if work_page and status in (404, 410):
        raise AppError("NOTE_NOT_FOUND", 404, detail="Douyin work is unavailable")
    raise AppError("UPSTREAM_BAD_RESPONSE", 502, status >= 500, "unexpected Douyin HTTP status")


def _redirect_url(source: str, response: Response) -> str:
    location = response.headers.get("location")
    if not location:
        raise AppError("UPSTREAM_BAD_RESPONSE", 502, detail="Douyin redirect lacks Location")
    if any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in location):
        raise invalid_url("Douyin redirect contains whitespace or control characters")
    try:
        return urljoin(source, location)
    except ValueError as exc:
        raise invalid_url("invalid Douyin redirect") from exc


def _page_redirect(source: str, response: Response) -> ParsedDouyinUrl:
    target = _redirect_url(source, response)
    parts = douyin_https_parts(target)
    if parts.hostname in PAGE_HOSTS:
        path = parts.path.lower()
        if path == "/captcha" or path.startswith(("/captcha/", "/verify/")) or path == "/verify":
            raise AppError("UPSTREAM_ACCESS_RESTRICTED", 503, detail="Douyin verification redirect")
        if path == "/login" or path.startswith("/login/"):
            raise AppError("UPSTREAM_LOGIN_REQUIRED", 503, detail="Douyin login redirect")
    return parse_douyin_url(target)


class DouyinShareClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def resolve_short_link(
        self, initial: ParsedDouyinUrl, deadline: Deadline
    ) -> ParsedDouyinUrl:
        target = initial
        async with AsyncSession(trust_env=False) as session:
            for redirects in range(self.settings.max_redirects + 1):
                response, html = await self._get(session, target.normalized_url, deadline)
                _check_status(response, work_page=True)
                if response.status_code == 200:
                    _classify_page(target.normalized_url, html)
                    return target
                if redirects == self.settings.max_redirects:
                    break
                target = _page_redirect(target.normalized_url, response)
                if not target.is_short_link:
                    return target
        raise AppError("UPSTREAM_BAD_RESPONSE", 502, detail="Douyin redirect limit exceeded")

    async def fetch_video(self, target: ParsedDouyinUrl, deadline: Deadline) -> InternalNote | None:
        assert target.item_id is not None and target.kind == "video"
        item_id = target.item_id
        page_url = f"{SHARE_ORIGIN}share/video/{item_id}/"
        if target.host == SHARE_HOST and (query := urlsplit(target.normalized_url).query):
            page_url += f"?{query}"
        async with AsyncSession(trust_env=False) as guest:
            # The initial origin response can set a guest cookie and redirect to the desktop site.
            warmup, html = await self._get(guest, SHARE_ORIGIN, deadline)
            _check_status(warmup)
            if warmup.status_code == 200:
                _classify_page(SHARE_ORIGIN, html)
            response, html = await self._get(guest, page_url, deadline)
            _check_status(response, work_page=True)
        if response.status_code in REDIRECT_STATUSES:
            redirected = _page_redirect(page_url, response)
            if redirected.item_id != item_id or redirected.kind != "video":
                raise AppError("PARSE_FAILED", 502, detail="Douyin share redirect target mismatch")
            return None
        detail = decode_share_detail(html, item_id)
        if detail is None:
            _classify_page(page_url, html)
            return None
        video = detail.get("video")
        if detail.get("images") or not isinstance(video, dict):
            return None
        play = video.get("play_addr")
        urls = play.get("url_list") if isinstance(play, dict) else None
        if not isinstance(urls, list):
            return None
        # The playback host must not receive the share site's visitor cookies.
        async with AsyncSession(trust_env=False) as playback:
            for url in urls:
                if not isinstance(url, str) or not url:
                    continue
                media_url = await self._media_url(playback, url, deadline)
                if media_url is None:
                    continue
                try:
                    return normalize_share_video(item_id, detail, media_url)
                except AppError as exc:
                    if exc.code != "MEDIA_NOT_FOUND":
                        raise
        return None

    async def _media_url(
        self, session: AsyncSession[Response], url: str, deadline: Deadline
    ) -> str | None:
        parts = douyin_https_parts(url, max_length=8192)
        if parts.hostname == PLAY_HOST:
            if parts.path not in PLAY_PATHS:
                raise invalid_url("unsupported Douyin playback path")
            response, html = await self._get(session, url, deadline)
            _check_status(response)
            if response.status_code == 200:
                _classify_page(url, html)
                return None
            url = _redirect_url(url, response)
        if normalize_douyin_media_url(url, VIDEO_HOSTS) is None:
            raise invalid_url("unsupported Douyin video CDN address")
        host = douyin_https_parts(url, max_length=8192).hostname
        assert host is not None
        await self._resolve_host(host, deadline)
        return url

    async def _resolve_host(self, host: str, deadline: Deadline) -> tuple[str, ...]:
        try:
            return await asyncio.wait_for(resolve_public_addresses(host, 443), deadline.remaining())
        except TimeoutError as exc:
            raise AppError("UPSTREAM_TIMEOUT", 504, True, "Douyin DNS timed out") from exc

    async def _get(
        self, session: AsyncSession[Response], url: str, deadline: Deadline
    ) -> tuple[Response, str]:
        host = urlsplit(url).hostname
        assert host is not None
        addresses = await self._resolve_host(host, deadline)
        pinned = ",".join(f"[{address}]" if ":" in address else address for address in addresses)
        session.curl_options = {CurlOpt.RESOLVE: [f"{host}:443:{pinned}"], CurlOpt.FRESH_CONNECT: 1}
        body = bytearray()
        limit = min(self.settings.max_html_bytes, self.settings.douyin_state_max_bytes)
        overflow = False

        def collect(chunk: bytes) -> int:
            nonlocal overflow
            if len(body) + len(chunk) > limit:
                overflow = True
                return CURL_WRITEFUNC_ERROR
            body.extend(chunk)
            return len(chunk)

        remaining = deadline.remaining()
        try:
            response = await asyncio.wait_for(
                session.get(
                    url,
                    allow_redirects=False,
                    verify=True,
                    quote=False,
                    timeout=(min(remaining, self.settings.connect_timeout_seconds), remaining),
                    headers=SHARE_HEADERS,
                    content_callback=collect,
                ),
                remaining,
            )
        except (TimeoutError, CurlError, OSError) as exc:
            if overflow:
                raise AppError(
                    "UPSTREAM_BAD_RESPONSE", 502, detail="Douyin body exceeds limit"
                ) from exc
            if isinstance(exc, TimeoutError) or (
                isinstance(exc, CurlError) and exc.code == CurlECode.OPERATION_TIMEDOUT
            ):
                raise AppError("UPSTREAM_TIMEOUT", 504, True, "Douyin request timed out") from exc
            raise AppError("UPSTREAM_BAD_RESPONSE", 502, True, "Douyin transport failed") from exc
        deadline.remaining()
        return response, body.decode("utf-8", errors="replace")
