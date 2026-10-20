"""Fail-closed Douyin page URL policy."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from urllib.parse import SplitResult, urlsplit, urlunsplit

from app.errors import AppError, invalid_url

SHORT_HOST = "v.douyin.com"
DETAIL_HOST = "www.douyin.com"
SHARE_HOST = "www.iesdouyin.com"
PAGE_HOSTS = frozenset({SHORT_HOST, DETAIL_HOST, SHARE_HOST})
TOKEN_CHARS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")


@dataclass(frozen=True)
class ParsedDouyinUrl:
    normalized_url: str
    host: str
    item_id: str | None
    kind: str | None
    is_short_link: bool


def _host(parts: SplitResult) -> str:
    try:
        host = parts.hostname
        port = parts.port
    except ValueError as exc:
        raise invalid_url("invalid host or port") from exc
    if host is None or not host.isascii():
        raise invalid_url("missing or non-ASCII host")
    lowered = host.lower()
    raw_host = parts.netloc.rsplit("@", 1)[-1]
    if raw_host.endswith("."):
        if raw_host.endswith(".."):
            raise invalid_url("repeated trailing root dot")
        lowered = lowered.removesuffix(".")
    if port not in (None, 443):
        raise invalid_url("only the default HTTPS port is allowed")
    return lowered


def _segments(parts: SplitResult) -> list[str]:
    path = parts.path
    if "\\" in path or "%2f" in path.lower() or "%5c" in path.lower():
        raise invalid_url("encoded or literal path separator is not allowed")
    return [segment for segment in path.split("/") if segment]


def _item_id(value: str) -> str:
    if not value.isascii() or not value.isdigit() or not 18 <= len(value) <= 20:
        raise invalid_url("invalid Douyin item ID")
    return value


def parse_douyin_url(raw_url: str) -> ParsedDouyinUrl:
    if not raw_url or len(raw_url) > 4096:
        raise invalid_url("URL is empty or too long")
    if raw_url != raw_url.strip() or any(
        char.isspace() or ord(char) < 32 or ord(char) == 127 for char in raw_url
    ):
        raise invalid_url("URL contains whitespace or control characters")
    try:
        parts = urlsplit(raw_url)
    except ValueError as exc:
        raise invalid_url("URL could not be parsed") from exc
    if parts.scheme.lower() != "https" or parts.username or parts.password or parts.fragment:
        raise invalid_url("URL must be credential-free HTTPS without a fragment")
    host = _host(parts)
    if host not in PAGE_HOSTS:
        raise invalid_url("unsupported Douyin host")
    segments = _segments(parts)
    item_id: str | None = None
    kind: str | None = None
    is_short = host == SHORT_HOST
    if is_short:
        if len(segments) != 1 or not segments[0] or any(c not in TOKEN_CHARS for c in segments[0]):
            raise invalid_url("invalid Douyin short-link path")
    elif host == DETAIL_HOST:
        if len(segments) != 2 or segments[0] not in {"video", "note"}:
            raise invalid_url("unsupported Douyin detail path")
        kind, item_id = segments[0], _item_id(segments[1])
    else:
        if len(segments) != 3 or segments[:2] not in (["share", "video"], ["share", "note"]):
            raise invalid_url("unsupported Douyin share path")
        kind, item_id = segments[1], _item_id(segments[2])
    normalized = urlunsplit(("https", host, parts.path or "/", parts.query, ""))
    return ParsedDouyinUrl(normalized, host, item_id, kind, is_short)


def douyin_cache_key(raw_url: str) -> str:
    parsed = parse_douyin_url(raw_url)
    digest = hashlib.sha256(parsed.normalized_url.encode()).hexdigest()
    return f"douyin:{digest}"


def is_douyin_host(raw_url: str) -> bool:
    try:
        parts = urlsplit(raw_url)
        return _host(parts) in PAGE_HOSTS
    except (AppError, ValueError):
        return False
