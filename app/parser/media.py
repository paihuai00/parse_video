"""Normalize supported note media without guessing missing metadata."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit, urlunsplit

from app.errors import AppError
from app.models import InternalCover, InternalImage, InternalNote, InternalVideo

ALLOWED_MEDIA_HOSTS = frozenset(
    {
        "sns-video-v6.xhscdn.com",
        "sns-webpic-qc.xhscdn.com",
    }
)


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float) and value > 0:
        return int(value)
    return None


def _nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float) and value >= 0:
        return int(value)
    return None


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def normalize_media_url(value: Any) -> str | None:
    if not isinstance(value, str) or len(value) > 8192:
        return None
    try:
        parts = urlsplit(value)
    except ValueError:
        return None
    host = (parts.hostname or "").lower().rstrip(".")
    if host not in ALLOWED_MEDIA_HOSTS:
        return None
    try:
        port = parts.port
    except ValueError:
        return None
    expected_port = 443 if parts.scheme == "https" else 80
    if (
        parts.username is not None
        or parts.password is not None
        or port not in {None, expected_port}
    ):
        return None
    if parts.scheme not in {"http", "https"} or not parts.path:
        return None
    return urlunsplit(("https", host, parts.path, parts.query, ""))


def _image_url(item: dict[str, Any]) -> str | None:
    candidates: list[Any] = [item.get("urlDefault")]
    info_list = item.get("infoList")
    if isinstance(info_list, list):
        candidates.extend(
            info.get("url")
            for info in info_list
            if isinstance(info, dict) and info.get("imageScene") == "WB_DFT"
        )
    candidates.append(item.get("urlPre"))
    seen: set[str] = set()
    for candidate in candidates:
        url = normalize_media_url(candidate)
        if url and url not in seen:
            return url
        if url:
            seen.add(url)
    return None


def _has_live_media(note: dict[str, Any]) -> bool:
    note_type = str(note.get("type", "")).lower()
    if note_type in {"live", "live_photo", "livephoto"}:
        return True
    image_list = note.get("imageList")
    if not isinstance(image_list, list):
        return False
    live_keys = {"livePhoto", "livePhotoUrl", "videoUrl", "stream"}
    return any(
        isinstance(item, dict) and any(item.get(key) for key in live_keys) for item in image_list
    )


def _cover_from_images(items: Any) -> InternalCover | None:
    if not isinstance(items, list):
        return None
    for item in items:
        if not isinstance(item, dict):
            continue
        url = _image_url(item)
        if url:
            return InternalCover(
                url, _positive_int(item.get("width")), _positive_int(item.get("height"))
            )
    return None


def _stream_candidates(note: dict[str, Any]) -> list[dict[str, Any]]:
    video = note.get("video")
    if not isinstance(video, dict):
        return []
    media = video.get("media")
    if not isinstance(media, dict):
        return []
    stream = media.get("stream")
    if not isinstance(stream, dict):
        return []
    candidates: list[dict[str, Any]] = []
    for codec_group, values in stream.items():
        if not isinstance(values, list):
            continue
        for value in values:
            if isinstance(value, dict):
                candidate = dict(value)
                candidate.setdefault("_codec_group", codec_group)
                candidates.append(candidate)
    return candidates


def _candidate_url(candidate: dict[str, Any]) -> str | None:
    direct = normalize_media_url(candidate.get("masterUrl"))
    if direct:
        return direct
    backups = candidate.get("backupUrls")
    if isinstance(backups, list):
        for item in backups:
            url = normalize_media_url(item)
            if url:
                return url
    return None


def _codec(candidate: dict[str, Any]) -> str | None:
    value = _text(candidate.get("videoCodec")) or _text(candidate.get("codec"))
    if value:
        return value
    group = _text(candidate.get("_codec_group"))
    return group.upper() if group else None


def _is_mp4(candidate: dict[str, Any], url: str) -> bool:
    fmt = (_text(candidate.get("format")) or _text(candidate.get("container")) or "").lower()
    mime = (_text(candidate.get("mimeType")) or "").lower()
    path = urlsplit(url).path.lower()
    if fmt and fmt != "mp4":
        return False
    if mime and "mp4" not in mime:
        return False
    return (fmt == "mp4" or "mp4" in mime or path.endswith(".mp4")) and ".m3u8" not in path


def _rank(candidate: dict[str, Any]) -> tuple[int, int, int, int]:
    codec = (_codec(candidate) or "").lower().replace(".", "")
    h264 = int(codec in {"h264", "avc", "avc1"} or "264" in codec)
    width = _positive_int(candidate.get("width")) or 0
    height = _positive_int(candidate.get("height")) or 0
    bitrate = (
        _positive_int(candidate.get("avgBitrate")) or _positive_int(candidate.get("bitrate")) or 0
    )
    return h264, width * height, bitrate, width


def _duration_seconds(candidate: dict[str, Any], note: dict[str, Any]) -> float | None:
    value = candidate.get("duration")
    if value is None:
        video = note.get("video")
        value = video.get("duration") if isinstance(video, dict) else None
    if isinstance(value, bool) or not isinstance(value, int | float) or value < 0:
        return None
    return float(value) / 1000.0


def normalize_note(note_id: str, note: dict[str, Any]) -> InternalNote:
    if _has_live_media(note):
        raise AppError("UNSUPPORTED_CONTENT", 422, detail="live media detected")
    title = _text(note.get("title")) or _text(note.get("desc"))
    note_type = str(note.get("type", "normal")).lower()
    video_payload = note.get("video")
    if isinstance(video_payload, dict) and note_type != "video":
        raise AppError("UNSUPPORTED_CONTENT", 422, detail="mixed media note detected")
    has_video = note_type == "video"
    images = note.get("imageList")

    if has_video:
        valid: list[tuple[dict[str, Any], str]] = []
        for candidate in _stream_candidates(note):
            url = _candidate_url(candidate)
            if url and _is_mp4(candidate, url):
                valid.append((candidate, url))
        if not valid:
            raise AppError("MEDIA_NOT_FOUND", 502, detail="supported main MP4 is missing")
        candidate, url = max(valid, key=lambda item: _rank(item[0]))
        video = InternalVideo(
            url=url,
            source_width=_positive_int(candidate.get("width")),
            source_height=_positive_int(candidate.get("height")),
            codec=_codec(candidate),
            quality=_text(candidate.get("qualityType")) or _text(candidate.get("quality")),
            duration_seconds=_duration_seconds(candidate, note),
            size_bytes=_nonnegative_int(candidate.get("size")),
        )
        return InternalNote(note_id, title, "video", (), (video,), _cover_from_images(images))

    if note_type not in {"normal", "image", ""}:
        raise AppError("UNSUPPORTED_CONTENT", 422, detail="unsupported note type")
    normalized_images: list[InternalImage] = []
    if isinstance(images, list):
        for item in images:
            if not isinstance(item, dict):
                continue
            url = _image_url(item)
            if url:
                normalized_images.append(
                    InternalImage(
                        url,
                        _positive_int(item.get("width")),
                        _positive_int(item.get("height")),
                        len(normalized_images) + 1,
                    )
                )
    if not normalized_images:
        raise AppError("MEDIA_NOT_FOUND", 502, detail="body images are missing")
    return InternalNote(note_id, title, "image", tuple(normalized_images), (), None)
