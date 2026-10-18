"""Pinned, bounded, manually redirected curl_cffi transport."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, cast
from urllib.parse import urljoin, urlsplit

from curl_cffi import CurlECode, CurlError, CurlOpt
from curl_cffi.curl import CURL_WRITEFUNC_ERROR
from curl_cffi.requests import AsyncSession, Response

from app.config import Settings
from app.errors import AppError
from app.parser.url_rules import resolve_url

TEMPORARY_STATUSES = frozenset({500, 502, 504})
REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})


@dataclass(frozen=True)
class PageResponse:
    html: str
    final_url: str
    note_id: str


class Deadline:
    def __init__(self, seconds: float) -> None:
        self._end = time.monotonic() + seconds

    def remaining(self) -> float:
        remaining = self._end - time.monotonic()
        if remaining <= 0:
            raise AppError("UPSTREAM_TIMEOUT", 504, True, "total deadline exceeded")
        return remaining


def _response_encoding(response: Response) -> str:
    content_type = response.headers.get("content-type", "")
    for part in content_type.split(";"):
        part = part.strip().lower()
        if part.startswith("charset="):
            return part.split("=", 1)[1].strip('"') or "utf-8"
    return "utf-8"


def classify_page(response: Response, html: str) -> None:
    final_path = urlsplit(str(response.url)).path.lower()
    lowered = html.lower()
    if response.status_code == 404 or any(
        marker in lowered for marker in ("笔记不存在", "内容已删除")
    ):
        raise AppError("NOTE_NOT_FOUND", 404, detail="upstream explicitly reported missing note")
    if "/login" in final_path or any(
        marker in lowered for marker in ("登录后查看", "请先登录", "login-container")
    ):
        raise AppError("UPSTREAM_LOGIN_REQUIRED", 503, detail="upstream login page")
    if any(marker in lowered for marker in ("captcha", "滑块验证", "安全验证", "verify-page")):
        raise AppError("UPSTREAM_ACCESS_RESTRICTED", 503, detail="upstream verification challenge")
    if response.status_code == 429 or any(
        marker in lowered for marker in ("访问频繁", "请求频繁", "too many requests")
    ):
        raise AppError("UPSTREAM_RATE_LIMITED", 503, True, "upstream rate limited", 30)
    if response.status_code >= 400:
        raise AppError(
            "UPSTREAM_BAD_RESPONSE", 502, response.status_code >= 500, "unexpected upstream status"
        )


class XiaohongshuClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def fetch(self, raw_url: str, deadline: Deadline) -> PageResponse:
        last_transport_error: Exception | None = None
        for attempt in range(2):
            try:
                return await self._fetch_once(raw_url, deadline)
            except AppError as exc:
                if attempt == 0 and exc.code == "UPSTREAM_BAD_RESPONSE" and exc.retryable:
                    continue
                raise
            except (CurlError, OSError) as exc:
                if isinstance(exc, CurlError) and exc.code == CurlECode.OPERATION_TIMEDOUT:
                    raise AppError("UPSTREAM_TIMEOUT", 504, True, "curl request timed out") from exc
                last_transport_error = exc
                if attempt == 0:
                    continue
                break
        raise AppError(
            "UPSTREAM_BAD_RESPONSE", 502, True, "temporary transport failure"
        ) from last_transport_error

    async def _fetch_once(self, raw_url: str, deadline: Deadline) -> PageResponse:
        current_url = raw_url
        redirect_count = 0
        async with AsyncSession(
            impersonate=cast(Any, self.settings.impersonate), trust_env=False
        ) as session:
            while True:
                try:
                    hop = await asyncio.wait_for(resolve_url(current_url), deadline.remaining())
                except TimeoutError as exc:
                    raise AppError(
                        "UPSTREAM_TIMEOUT", 504, True, "DNS resolution timed out"
                    ) from exc
                # This option is session-scoped in curl_cffi 0.13.0. Requests in a
                # parse are sequential, so replacing it before each hop pins that
                # connection while preserving the session's anonymous cookie jar.
                session.curl_options = {CurlOpt.RESOLVE: hop.resolve_entries}
                chunks: list[bytes] = []
                size = 0
                overflow = False

                def collect(chunk: bytes, chunks_ref: list[bytes] = chunks) -> int:
                    nonlocal size, overflow
                    size += len(chunk)
                    if size > self.settings.max_html_bytes:
                        overflow = True
                        return CURL_WRITEFUNC_ERROR
                    chunks_ref.append(chunk)
                    return len(chunk)

                remaining = deadline.remaining()
                try:
                    response = await asyncio.wait_for(
                        session.get(
                            hop.normalized_url,
                            allow_redirects=False,
                            verify=True,
                            timeout=(
                                min(self.settings.connect_timeout_seconds, remaining),
                                remaining,
                            ),
                            headers={
                                "Accept": "text/html,application/xhtml+xml",
                                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                                "Referer": "https://www.xiaohongshu.com/",
                            },
                            content_callback=collect,
                        ),
                        timeout=remaining,
                    )
                except TimeoutError as exc:
                    raise AppError(
                        "UPSTREAM_TIMEOUT", 504, True, "upstream request timed out"
                    ) from exc
                except CurlError as exc:
                    if overflow:
                        raise AppError(
                            "UPSTREAM_BAD_RESPONSE", 502, detail="HTML response exceeds limit"
                        ) from exc
                    raise
                if response.status_code in REDIRECT_STATUSES:
                    location = response.headers.get("location")
                    if not location:
                        raise AppError(
                            "UPSTREAM_BAD_RESPONSE", 502, detail="redirect lacks Location"
                        )
                    if redirect_count >= self.settings.max_redirects:
                        raise AppError(
                            "UPSTREAM_BAD_RESPONSE", 502, detail="redirect limit exceeded"
                        )
                    current_url = urljoin(hop.normalized_url, location)
                    redirect_count += 1
                    continue
                if response.status_code in TEMPORARY_STATUSES:
                    raise AppError("UPSTREAM_BAD_RESPONSE", 502, True, "temporary upstream status")
                body = b"".join(chunks)
                deadline.remaining()
                try:
                    html = body.decode(_response_encoding(response), errors="replace")
                except LookupError as exc:
                    raise AppError(
                        "UPSTREAM_BAD_RESPONSE", 502, detail="unsupported response charset"
                    ) from exc
                classify_page(response, html)
                deadline.remaining()
                if hop.note_id is None:
                    raise AppError(
                        "UPSTREAM_BAD_RESPONSE", 502, detail="short link did not resolve to a note"
                    )
                return PageResponse(html, hop.normalized_url, hop.note_id)
