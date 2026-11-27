"""Validate one anonymous media response before exposing any downstream headers."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from urllib.parse import urljoin

from app.config import Settings
from app.errors import AppError
from app.services.media_policy import MediaKind, validate_media_url
from app.services.safe_http import SafeHTTP, response_headers


def sniff_type(prefix: bytes, kind: MediaKind) -> str:
    if kind == "video":
        if len(prefix) >= 16 and prefix[4:8] == b"ftyp":
            major = prefix[8:12]
            box_end = min(int.from_bytes(prefix[:4], "big"), len(prefix))
            brands = {major, *(prefix[i : i + 4] for i in range(16, box_end - 3, 4))}
            image_brands = {
                b"avif",
                b"avis",
                b"mif1",
                b"msf1",
                b"heic",
                b"heix",
                b"hevc",
                b"hevx",
                b"miaf",
            }
            video_brands = {
                b"isom",
                b"iso2",
                b"iso3",
                b"iso4",
                b"iso5",
                b"iso6",
                b"mp41",
                b"mp42",
                b"avc1",
                b"M4V ",
                b"dash",
                b"msdh",
                b"msix",
            }
            if brands & video_brands and not brands & image_brands:
                return "video/mp4"
    else:
        if prefix.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        if prefix.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        if prefix.startswith((b"GIF87a", b"GIF89a")):
            return "image/gif"
        if prefix[:4] == b"RIFF" and prefix[8:12] == b"WEBP":
            return "image/webp"
    raise AppError("MEDIA_UPSTREAM_BAD_RESPONSE", 502, detail="unsupported media signature")


@dataclass
class MediaSource:
    content_type: str
    length: int | None
    prefix: bytes
    chunks: AsyncIterator[bytes]


def media_redirect(base: str, location: str) -> str:
    target = urljoin(base, location)
    # urllib.urljoin loses an explicitly empty query (including Location: '?').
    if "?" in location and not location.split("?", 1)[1].split("#", 1)[0]:
        target = target.split("#", 1)[0].split("?", 1)[0] + "?"
    return target


@asynccontextmanager
async def open_media_source(
    http: SafeHTTP,
    settings: Settings,
    url: str,
    platform: str,
    kind: MediaKind,
    method: str = "GET",
) -> AsyncIterator[MediaSource]:
    for hop in range(settings.max_redirects + 1):
        validate_media_url(url, platform, kind)
        async with AsyncExitStack() as stack:
            response = await stack.enter_async_context(
                http.stream(
                    method,
                    url,
                    [
                        (b"Accept", b"*/*"),
                        (b"Accept-Encoding", b"identity"),
                        (b"User-Agent", b"Mozilla/5.0"),
                    ],
                )
            )
            headers = response_headers(response)
            if response.status in {301, 302, 303, 307, 308}:
                if hop == settings.max_redirects or not headers.get("location"):
                    raise AppError("MEDIA_UPSTREAM_BAD_RESPONSE", 502, detail="redirect limit")
                url = media_redirect(url, headers["location"])
                continue
            if response.status == 429:
                raise AppError("MEDIA_RATE_LIMITED", 429, True, retry_after=2)
            if response.status != 200:
                code = (
                    "MEDIA_UPSTREAM_REJECTED"
                    if response.status in {401, 403, 404, 410}
                    else "MEDIA_UPSTREAM_BAD_RESPONSE"
                )
                raise AppError(code, 502, detail="upstream media status")
            if headers.get("content-encoding", "identity").lower() not in {"", "identity"}:
                raise AppError("MEDIA_UPSTREAM_BAD_RESPONSE", 502, detail="encoded media")
            length_text = headers.get("content-length")
            if length_text is not None and (not length_text.isascii() or not length_text.isdigit()):
                raise AppError("MEDIA_UPSTREAM_BAD_RESPONSE", 502, detail="invalid media length")
            length = int(length_text) if length_text is not None else None
            if length is not None and (length == 0 or length > settings.media_max_bytes):
                raise AppError("MEDIA_UPSTREAM_BAD_RESPONSE", 502, detail="media size limit")
            declared = headers.get("content-type", "").split(";", 1)[0].strip().lower()
            allowed_types = (
                {"video/mp4"}
                if kind == "video"
                else {"image/jpeg", "image/png", "image/webp", "image/gif"}
            )
            if declared not in allowed_types | {"application/octet-stream"}:
                raise AppError("MEDIA_UPSTREAM_BAD_RESPONSE", 502, detail="invalid media type")
            chunks = response.aiter_stream()
            prefix = b""
            if method == "GET":
                while len(prefix) < 32:
                    try:
                        prefix += await anext(chunks)
                    except StopAsyncIteration:
                        break
                actual = sniff_type(prefix, kind)
                if declared != "application/octet-stream" and declared != actual:
                    raise AppError("MEDIA_UPSTREAM_BAD_RESPONSE", 502, detail="media type mismatch")
            else:
                # HEAD cannot prove file magic; never fabricate a MIME or length.
                if declared not in allowed_types:
                    raise AppError("MEDIA_UPSTREAM_BAD_RESPONSE", 502, detail="untyped HEAD")
                actual = declared
            yield MediaSource(actual, length, prefix, chunks)
            return
    raise AppError("MEDIA_UPSTREAM_BAD_RESPONSE", 502, detail="redirect limit")
