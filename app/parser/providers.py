"""Fixed third-party parse providers, isolated from native Douyin acquisition."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from typing import Any
from urllib.parse import urlencode, urlsplit

import httpcore

from app.config import Settings
from app.errors import AppError
from app.models import InternalCover, InternalImage, InternalNote, InternalVideo
from app.parser.client import Deadline
from app.parser.douyin.url_rules import parse_douyin_url
from app.parser.url_rules import resolve_public_addresses
from app.services.media_policy import public_http_parts, validate_media_url
from app.services.media_source import open_media_source
from app.services.safe_http import SafeHTTP, response_headers

PROVIDERS = {
    "douyin": ("douyin", "dyjx", "ifphp", "short_videos"),
    "bilibili": ("bilibili", "short_videos"),
    "unknown": ("short_videos",),
}


def validate_input(raw_url: str, platform: str) -> None:
    parts = public_http_parts(raw_url)
    if platform == "douyin":
        parse_douyin_url(raw_url)
    elif platform == "bilibili" and parts.hostname not in {
        "b23.tv",
        "bilibili.com",
        "www.bilibili.com",
        "m.bilibili.com",
    }:
        raise AppError("INVALID_URL", 400)


def _text(value: object) -> str:
    return value[:8192] if isinstance(value, str) else ""


def _url(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return _text(
            value.get("url") or value.get("src") or value.get("image") or value.get("origin")
        )
    return ""


class ProviderAdapter:
    def __init__(self, settings: Settings, platform: str, http: SafeHTTP | None = None) -> None:
        self.settings, self.platform = settings, platform
        self.http = http or SafeHTTP(
            settings.connect_timeout_seconds, settings.connect_timeout_seconds
        )

    def cache_identity(self, raw_url: str) -> str:
        validate_input(raw_url, self.platform)
        return f"providers-v1:{self.platform}:{hashlib.sha256(raw_url.encode()).hexdigest()}"

    async def parse(self, raw_url: str, deadline: Deadline) -> InternalNote:
        validate_input(raw_url, self.platform)
        parts = public_http_parts(raw_url)
        # Even generic share URLs must not designate private destinations. We never fetch them.
        await asyncio.wait_for(
            resolve_public_addresses(
                parts.hostname or "", parts.port or (443 if parts.scheme == "https" else 80)
            ),
            deadline.remaining(),
        )
        for provider in PROVIDERS[self.platform]:
            for attempt in range(2):
                try:
                    async with asyncio.timeout(deadline.remaining()):
                        data = await self.fetch(provider, raw_url)
                        result = await self.normalize(data, raw_url)
                        deadline.remaining()
                        return result
                except AppError as exc:
                    if exc.code in {
                        "INVALID_URL",
                        "MEDIA_SOURCE_INVALID",
                        "MEDIA_SOURCE_FORBIDDEN",
                        "UNAUTHORIZED",
                        "PROVIDER_ACCESS_DENIED",
                    }:
                        raise
                    if not exc.retryable or attempt == 1:
                        break
                except (
                    httpcore.NetworkError,
                    httpcore.ProtocolError,
                    httpcore.TimeoutException,
                    TimeoutError,
                ):
                    deadline.remaining()
                    if attempt == 1:
                        break
        raise AppError("PROVIDER_EXHAUSTED", 502, True)

    async def fetch(self, provider: str, raw_url: str) -> dict[str, Any]:
        headers = [(b"Accept", b"application/json"), (b"Accept-Encoding", b"identity")]
        if provider == "ifphp":
            if not self.settings.ifphp_api_key:
                raise AppError("PROVIDER_UNAVAILABLE", 503)
            endpoint = "https://api-new.ifphp.com/api/svparse"
            headers.append((b"X-API-Key", self.settings.ifphp_api_key.encode("ascii")))
        else:
            endpoint = f"https://api.bugpk.com/api/{provider}"
        async with self.http.stream(
            "GET", endpoint + "?" + urlencode({"url": raw_url}), headers
        ) as response:
            if response.status in {401, 403}:
                raise AppError("PROVIDER_ACCESS_DENIED", 502)
            if response.status != 200:
                raise AppError(
                    "PROVIDER_UNAVAILABLE", 502, response.status in {429, 500, 502, 503, 504}
                )
            values = response_headers(response)
            if values.get("content-encoding", "identity").lower() not in {"identity", ""}:
                raise AppError("PROVIDER_UNAVAILABLE", 502)
            body = bytearray()
            async for chunk in response.aiter_stream():
                if len(body) + len(chunk) > self.settings.provider_max_json_bytes:
                    raise AppError("PROVIDER_UNAVAILABLE", 502)
                body.extend(chunk)
            try:
                payload = json.loads(body)
            except (ValueError, RecursionError) as exc:
                raise AppError("PROVIDER_UNAVAILABLE", 502) from exc
            if (
                not isinstance(payload, dict)
                or payload.get("code") != 200
                or not isinstance(payload.get("data"), dict)
            ):
                raise AppError("PROVIDER_UNAVAILABLE", 502)
            return payload["data"]  # type: ignore[no-any-return]

    async def normalize(self, data: dict[str, Any], raw_url: str) -> InternalNote:
        image_values = data.get("images") or []
        if not isinstance(image_values, list) or len(image_values) > 128:
            raise AppError("MEDIA_NOT_FOUND", 502)
        images = [_url(value) for value in image_values]
        if any(not value for value in images):
            raise AppError("MEDIA_NOT_FOUND", 502)
        if any(
            isinstance(value, dict)
            and any(
                value.get(key)
                for key in ("live_video", "live_photo", "livePhotos", "video", "motion")
            )
            for value in image_values
        ):
            # Unknown per-slot schemas must not silently lose a motion rendition.
            raise AppError("UNSUPPORTED_CONTENT", 422)
        if (
            data.get("live_photo")
            and data.get("livePhotos")
            and data["live_photo"] != data["livePhotos"]
        ):
            raise AppError("UNSUPPORTED_CONTENT", 422)
        motion = data.get("live_photo", data.get("livePhotos", [])) or []
        if not isinstance(motion, list) or len(motion) > len(images):
            raise AppError("UNSUPPORTED_CONTENT", 422)
        if _text(data.get("type")).lower() == "live" and not any(motion):
            raise AppError("UNSUPPORTED_CONTENT", 422)
        slots: list[InternalImage] = []
        for i, image in enumerate(images):
            validate_media_url(image, self.platform, "image")
            live_video = None
            if i < len(motion) and motion[i] is not None:
                item = motion[i]
                if not isinstance(item, dict) or not _url(item.get("video")):
                    raise AppError("UNSUPPORTED_CONTENT", 422)
                if item.get("image") and item["image"] != image:
                    raise AppError("UNSUPPORTED_CONTENT", 422)
                live_video = await self.video(_url(item["video"]))
            slots.append(InternalImage(image, None, None, i + 1, live_video))
        video_url = _url(data.get("url"))
        is_gallery = _text(data.get("type")).lower() in {"image", "images", "live"}
        videos = () if is_gallery or not video_url else (await self.video(video_url),)
        if not videos and not slots:
            raise AppError("MEDIA_NOT_FOUND", 502)
        # The public union cannot express unrelated mixed top-level media.
        if videos and slots:
            raise AppError("UNSUPPORTED_CONTENT", 422)
        cover_url = _url(data.get("cover"))
        cover = None
        if cover_url and videos:
            validate_media_url(cover_url, self.platform, "image")
            cover = InternalCover(cover_url, None, None)
        # Only explicit provider identities; never hash a share token into a fake ID.
        identity = data.get("aweme_id") if self.platform == "douyin" else data.get("bvid")
        note_id = (
            str(identity)
            if isinstance(identity, str | int) and not isinstance(identity, bool)
            else None
        )
        if note_id is not None and not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", note_id):
            raise AppError("PARSE_FAILED", 502)
        if self.platform == "douyin":
            target_id = parse_douyin_url(raw_url).item_id
            if target_id and note_id and target_id != note_id:
                raise AppError("PARSE_FAILED", 502)
        author_value = data.get("author")
        author = author_value if isinstance(author_value, dict) else {}
        user_value = data.get("user")
        user = user_value if isinstance(user_value, dict) else {}
        author_name = _text(author.get("name") or data.get("auther") or user.get("name"))
        avatar_url = _url(author.get("avatar") or data.get("avatar") or user.get("avatar"))
        avatar = None
        if avatar_url:
            try:
                validate_media_url(avatar_url, self.platform, "image")
            except AppError:
                # Optional unsupported avatars never fail the work or leak a raw URL.
                pass
            else:
                avatar = InternalCover(avatar_url, None, None)
        return InternalNote(
            note_id,
            _text(data.get("title")),
            "video" if videos else "image",
            tuple(slots),
            videos,
            cover,
            _text(data.get("desc") or data.get("description")),
            author_name,
            avatar,
        )

    async def video(self, url: str) -> InternalVideo:
        validate_media_url(url, self.platform, "video")
        # Positive evidence for ambiguous provider URLs, not merely a declared type.
        if not urlsplit(url).path.lower().endswith(".mp4"):
            async with open_media_source(self.http, self.settings, url, self.platform, "video"):
                pass
        return InternalVideo(url, None, None, None, None, None, None)
