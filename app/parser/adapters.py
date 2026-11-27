"""Platform adapters consumed by the shared parse scheduler."""

from __future__ import annotations

from typing import Literal, Protocol

from app.config import Settings
from app.errors import AppError
from app.models import InternalNote
from app.parser.client import Deadline, PageResponse, XiaohongshuClient
from app.parser.douyin.browser import DouyinBrowser
from app.parser.douyin.media import normalize_douyin_note
from app.parser.douyin.share_client import DouyinShareClient
from app.parser.douyin.url_rules import douyin_cache_key, is_douyin_host, parse_douyin_url
from app.parser.media import normalize_mobile_note, normalize_note
from app.parser.state_reader import decode_initial_state, select_note_layout
from app.parser.url_rules import cache_key, parse_url

Platform = Literal["xiaohongshu", "douyin", "bilibili", "unknown"]


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
        selected = select_note_layout(state, page.note_id)
        normalize = normalize_mobile_note if selected.mobile else normalize_note
        note = normalize(page.note_id, selected.payload)
        deadline.remaining()
        return note


class DouyinAdapter:
    def __init__(self, settings: Settings, browser: DouyinBrowser | None = None) -> None:
        self.browser = browser or DouyinBrowser(settings)
        self.share_client = DouyinShareClient(settings)

    def cache_identity(self, raw_url: str) -> str:
        return douyin_cache_key(raw_url)

    async def parse(self, raw_url: str, deadline: Deadline) -> InternalNote:
        target = parse_douyin_url(raw_url)
        if target.is_short_link:
            target = await self.share_client.resolve_short_link(target, deadline)
        if target.kind == "video":
            note = await self.share_client.fetch_video(target, deadline)
            if note is not None:
                return note
        target_id, detail = await self.browser.fetch_detail(target.normalized_url, deadline)
        if target.item_id is not None and target.item_id != target_id:
            raise AppError("PARSE_FAILED", 502, detail="Douyin browser target mismatch")
        deadline.remaining()
        return normalize_douyin_note(target_id, detail)


def detect_platform(raw_url: str) -> Platform:
    from app.services.media_policy import public_http_parts

    parts = public_http_parts(raw_url)
    if is_douyin_host(raw_url):
        parse_douyin_url(raw_url)
        return "douyin"
    if parts.hostname in {"b23.tv", "bilibili.com", "www.bilibili.com", "m.bilibili.com"}:
        return "bilibili"
    if parts.hostname in {
        "xiaohongshu.com",
        "www.xiaohongshu.com",
        "www.rednote.com",
        "xhslink.com",
        "xhslink.cn",
    }:
        parse_url(raw_url)
        return "xiaohongshu"
    return "unknown"
