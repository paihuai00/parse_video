"""Normalize one verified Douyin work into the shared internal media model."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from app.errors import AppError
from app.models import InternalCover, InternalImage, InternalNote, InternalVideo

IMAGE_HOSTS = frozenset({"p3-pc-sign.douyinpic.com", "p9-pc-sign.douyinpic.com"})
VIDEO_HOSTS = frozenset({"v11-weba.douyinvod.com", "v26-web.douyinvod.com"})
VIDEO_HOST_PRIORITY = ("v11-weba.douyinvod.com", "v26-web.douyinvod.com")
MEDIA_HOSTS = IMAGE_HOSTS | VIDEO_HOSTS


def normalize_douyin_media_url(value: object, hosts: frozenset[str] = MEDIA_HOSTS) -> str | None:
    if not isinstance(value, str) or not value or len(value) > 8192:
        return None
    try:
        parts = urlsplit(value)
        host = parts.hostname
        port = parts.port
    except ValueError:
        return None
    if (
        parts.scheme != "https"
        or host not in hosts
        or port not in (None, 443)
        or parts.username
        or parts.password
        or parts.fragment
    ):
        return None
    return value


def _integer(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def _number(value: object) -> float | None:
    if isinstance(value, int | float) and not isinstance(value, bool) and value >= 0:
        return float(value)
    return None


def _urls(value: object) -> list[object]:
    if isinstance(value, dict):
        candidate = value.get("url_list")
        return candidate if isinstance(candidate, list) else []
    if isinstance(value, list):
        return [item.get("src") if isinstance(item, dict) else item for item in value]
    return []


def _first_media_url(
    value: object,
    hosts: frozenset[str],
    host_priority: tuple[str, ...] = (),
) -> str | None:
    if isinstance(value, str):
        return normalize_douyin_media_url(value, hosts)
    normalized_urls: list[str] = []
    for candidate in _urls(value):
        normalized = normalize_douyin_media_url(candidate, hosts)
        if normalized is not None:
            normalized_urls.append(normalized)
    for preferred_host in host_priority:
        for normalized in normalized_urls:
            if urlsplit(normalized).hostname == preferred_host:
                return normalized
    return normalized_urls[0] if normalized_urls else None


def _format_is_mp4(candidate: dict[str, Any], url: str) -> bool:
    format_value = candidate.get("format", candidate.get("videoFormat"))
    if isinstance(format_value, str) and format_value.lower() == "mp4":
        return True
    parts = urlsplit(url)
    return parts.path.lower().endswith(".mp4") or "mime_type=video_mp4" in parts.query.lower()


def _video_candidates(video: dict[str, Any]) -> list[dict[str, Any]]:
    variants = video.get("bitRateList", video.get("bit_rate"))
    if isinstance(variants, list) and variants:
        return [item for item in variants if isinstance(item, dict)]
    return [video]


def _video(candidate: dict[str, Any], duration_ms: object = None) -> InternalVideo | None:
    play = candidate.get("playAddr", candidate.get("play_addr"))
    url = _first_media_url(play, VIDEO_HOSTS, VIDEO_HOST_PRIORITY)
    if url is None or not _format_is_mp4(candidate, url):
        return None
    duration = _number(candidate.get("duration", duration_ms))
    is_h265 = candidate.get("isH265", candidate.get("is_h265"))
    codec = "H265" if is_h265 == 1 else "H264" if is_h265 == 0 else None
    return InternalVideo(
        url=url,
        source_width=_integer(candidate.get("width")),
        source_height=_integer(candidate.get("height")),
        codec=codec,
        quality=(
            str(candidate.get("gearName")) if isinstance(candidate.get("gearName"), str) else None
        ),
        duration_seconds=duration / 1000 if duration is not None else None,
        size_bytes=_integer(candidate.get("dataSize", candidate.get("data_size"))),
    )


def _select_video(video: dict[str, Any]) -> InternalVideo:
    duration = video.get("duration")
    candidates: list[tuple[InternalVideo, int, int, int, str]] = []
    for raw in _video_candidates(video):
        normalized = _video(raw, duration)
        if normalized is None:
            continue
        area = (normalized.source_width or 0) * (normalized.source_height or 0)
        bitrate = _integer(raw.get("bitRate", raw.get("bit_rate"))) or 0
        codec_rank = 2 if normalized.codec == "H264" else 1 if normalized.codec is None else 0
        candidates.append((normalized, codec_rank, area, bitrate, normalized.url))
    if not candidates:
        raise AppError("MEDIA_NOT_FOUND", 502, detail="Douyin video lacks a verified MP4")
    return max(candidates, key=lambda item: item[1:])[0]


def _is_dynamic_image(image: dict[str, Any]) -> bool:
    marker = image.get("livePhotoType", image.get("live_photo_type"))
    if marker not in (None, "$undefined", 0, "0"):
        return True
    motion = image.get("video")
    return isinstance(motion, dict) and bool(motion)


def _normalize_images(raw_images: list[object]) -> tuple[InternalImage, ...]:
    images: list[InternalImage] = []
    for index, raw in enumerate(raw_images, 1):
        if not isinstance(raw, dict):
            raise AppError("MEDIA_NOT_FOUND", 502, detail="invalid Douyin image slot")
        if _is_dynamic_image(raw):
            raise AppError("UNSUPPORTED_CONTENT", 422, detail="dynamic Douyin image is unsupported")
        urls = raw.get("urlList", raw.get("url_list"))
        url = _first_media_url(urls, IMAGE_HOSTS)
        if url is None:
            raise AppError("MEDIA_NOT_FOUND", 502, detail="Douyin image slot lacks a valid URL")
        images.append(
            InternalImage(
                url=url,
                source_width=_integer(raw.get("width")),
                source_height=_integer(raw.get("height")),
                index=index,
            )
        )
    if not images:
        raise AppError("MEDIA_NOT_FOUND", 502, detail="Douyin image work is empty")
    return tuple(images)


def _cover(video: dict[str, Any]) -> InternalCover | None:
    raw = video.get("coverUrlList", video.get("cover"))
    url = _first_media_url(raw, IMAGE_HOSTS)
    if url is None:
        return None
    cover_value = video.get("cover")
    return InternalCover(
        url=url,
        source_width=_integer(cover_value.get("width")) if isinstance(cover_value, dict) else None,
        source_height=(
            _integer(cover_value.get("height")) if isinstance(cover_value, dict) else None
        ),
    )


def normalize_douyin_note(target_id: str, detail: dict[str, Any]) -> InternalNote:
    actual_id = str(detail.get("awemeId", detail.get("aweme_id", "")))
    if actual_id != target_id:
        raise AppError("PARSE_FAILED", 502, detail="Douyin target ID mismatch")
    title = detail.get("desc")
    normalized_title = title if isinstance(title, str) and title else None
    raw_images = detail.get("images")
    if isinstance(raw_images, list) and raw_images:
        return InternalNote(
            note_id=target_id,
            title=normalized_title,
            kind="image",
            images=_normalize_images(raw_images),
            videos=(),
            cover=None,
        )
    raw_video = detail.get("video")
    if not isinstance(raw_video, dict):
        raise AppError("MEDIA_NOT_FOUND", 502, detail="Douyin work has no supported media")
    video = _select_video(raw_video)
    return InternalNote(
        note_id=target_id,
        title=normalized_title,
        kind="video",
        images=(),
        videos=(video,),
        cover=_cover(raw_video),
    )
