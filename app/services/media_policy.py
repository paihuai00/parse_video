"""Separate, fail-closed provider/media URL policies; never normalize signatures."""

from __future__ import annotations

import re
from typing import Literal
from urllib.parse import SplitResult, urlsplit

from app.errors import AppError
from app.parser.media import normalize_media_url

MediaKind = Literal["image", "video"]


def public_http_parts(raw_url: str, *, media: bool = False) -> SplitResult:
    code = "MEDIA_SOURCE_INVALID" if media else "INVALID_URL"
    try:
        if (
            not raw_url
            or len(raw_url) > 8192
            or not raw_url.isascii()
            or any(ord(c) <= 32 or ord(c) == 127 for c in raw_url)
            or "\\" in raw_url
        ):
            raise ValueError
        parts = urlsplit(raw_url)
        if (
            parts.scheme not in {"https", "http"}
            or not parts.hostname
            or parts.username is not None
            or parts.password is not None
            or parts.fragment
            or parts.hostname.endswith(".")
            or parts.port not in {None, 443 if parts.scheme == "https" else 80}
        ):
            raise ValueError
        # Domain names only: ipaddress also rejects unusual numeric spellings via DNS.
        if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", parts.hostname):
            raise ValueError
        import ipaddress

        try:
            ipaddress.ip_address(parts.hostname)
        except ValueError:
            return parts
        raise ValueError
    except ValueError as exc:
        raise AppError(code, 400, detail="invalid HTTP URL") from exc


def validate_media_url(raw_url: str, platform: str, kind: MediaKind) -> SplitResult:
    parts = public_http_parts(raw_url, media=True)
    host = parts.hostname or ""
    xhs = normalize_media_url(raw_url, kind=kind) is not None
    douyin_image = re.fullmatch(r"p[0-9]+(?:-pc)?-sign\.douyinpic\.com", host) is not None
    douyin_video = re.fullmatch(r"v[0-9]+(?:-[a-z0-9]+)*\.douyinvod\.com", host) is not None
    # Fixed playback entrypoints may redirect, but every CDN hop is checked again.
    playback = host in {
        "www.iesdouyin.com",
        "aweme.snssdk.com",
        "www.douyin.com",
    } and parts.path in {"/aweme/v1/play/", "/aweme/v1/play"}
    bilibili = re.fullmatch(r"[a-z0-9-]+\.bilivideo\.(?:com|cn)", host) is not None
    bilibili_image = host in {"i0.hdslb.com", "i1.hdslb.com", "i2.hdslb.com"}
    allowed = (
        (platform in {"xiaohongshu", "unknown"} and xhs)
        or (
            platform in {"douyin", "unknown"}
            and (
                (kind == "image" and douyin_image)
                or (kind == "video" and (douyin_video or playback))
            )
        )
        or (
            platform in {"bilibili", "unknown"}
            and ((kind == "video" and bilibili) or (kind == "image" and bilibili_image))
        )
    )
    if not allowed:
        raise AppError("MEDIA_SOURCE_FORBIDDEN", 403, detail="unsupported media host/type")
    return parts
