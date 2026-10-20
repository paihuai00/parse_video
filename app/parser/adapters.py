"""Platform adapters consumed by the shared parse scheduler."""

from __future__ import annotations

from typing import Literal, Protocol

from app.config import Settings
from app.errors import AppError
from app.models import InternalNote
from app.parser.client import Deadline, PageResponse, XiaohongshuClient
from app.parser.douyin.browser import DouyinBrowser
from app.parser.douyin.media import normalize_douyin_note
from app.parser.douyin.url_rules import douyin_cache_key, is_douyin_host, parse_douyin_url
from app.parser.media import normalize_note
from app.parser.state_reader import decode_initial_state, select_note
from app.parser.url_rules import cache_key, parse_url

Platform = Literal["xiaohongshu", "douyin"]


class PageFetcher(Protocol):
    async def fetch(self, raw_url: str, deadline: Deadline) -> PageResponse: ...


class Adapter(Protocol):
    def cache_identity(self, raw_url: str) -> str: ...

    async def parse(self, raw_url: str, deadline: Deadline) -> InternalNote: ...


class XiaohongshuAdapter:
    def __init__(self, settings: Settings, client: PageFetcher | None = None) -> None:
        self.client = client or XiaohongshuClient(settings)

    def cache_identity(self, raw_url: str) -> str:
        return cache_key(raw_url)

    async def parse(self, raw_url: str, deadline: Deadline) -> InternalNote:
        page = await self.client.fetch(raw_url, deadline)
        deadline.remaining()
        state = decode_initial_state(page.html)
        note = normalize_note(page.note_id, select_note(state, page.note_id))
        deadline.remaining()
        return note


class DouyinAdapter:
    def __init__(self, settings: Settings, browser: DouyinBrowser | None = None) -> None:
        self.browser = browser or DouyinBrowser(settings)

    def cache_identity(self, raw_url: str) -> str:
        return douyin_cache_key(raw_url)

    async def parse(self, raw_url: str, deadline: Deadline) -> InternalNote:
        target_id, detail = await self.browser.fetch_detail(raw_url, deadline)
        deadline.remaining()
        return normalize_douyin_note(target_id, detail)


def detect_platform(raw_url: str) -> Platform:
    if is_douyin_host(raw_url):
        parse_douyin_url(raw_url)
        return "douyin"
    try:
        parse_url(raw_url)
    except AppError as exc:
        raise AppError("INVALID_URL", 400, detail="unsupported platform URL") from exc
    return "xiaohongshu"
