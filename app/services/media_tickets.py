"""Atomic, bounded, reusable process-local media credentials (no file storage)."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime

from app.config import Settings
from app.errors import AppError
from app.models import InternalCover, InternalImage, InternalNote, InternalVideo
from app.services.media_policy import MediaKind, validate_media_url


@dataclass(frozen=True)
class MediaRecord:
    url: str
    platform: str
    kind: MediaKind
    expires: int


@dataclass(frozen=True)
class Publication:
    note: InternalNote
    expires_at: datetime | None
    resource_ids: tuple[str, ...] = ()


class MediaTickets:
    def __init__(self, settings: Settings, clock: Callable[[], float] = time.time) -> None:
        self.settings, self.clock = settings, clock
        self.records: dict[str, MediaRecord] = {}
        self.bytes = 0

    @staticmethod
    def size(record: MediaRecord) -> int:
        return len(record.url.encode()) + 256

    def revoke(self, ids: tuple[str, ...]) -> None:
        for resource_id in ids:
            record = self.records.pop(resource_id, None)
            if record is not None:
                self.bytes -= self.size(record)

    def _sign(self, resource_id: str, record: MediaRecord) -> str:
        identity = hashlib.sha256(record.url.encode()).hexdigest()
        payload = f"{resource_id}\n{record.expires}\n{record.platform}\n{record.kind}\n{identity}"
        return hmac.new(
            self.settings.media_signing_key.encode(), payload.encode(), hashlib.sha256
        ).hexdigest()

    def resolve(self, resource_id: str, exp: str | None, sig: str | None) -> MediaRecord:
        if (
            not exp
            or not sig
            or not exp.isascii()
            or not exp.isdigit()
            or len(exp) > 12
            or re.fullmatch(r"[0-9a-f]{64}", sig) is None
        ):
            raise AppError("MEDIA_TICKET_INVALID", 403)
        record = self.records.get(resource_id)
        if record is None:
            raise AppError("MEDIA_TICKET_GONE", 410)
        if record.expires != int(exp) or not hmac.compare_digest(
            self._sign(resource_id, record), sig
        ):
            raise AppError("MEDIA_TICKET_INVALID", 403)
        if self.clock() >= record.expires:
            raise AppError("MEDIA_TICKET_EXPIRED", 410)
        return record

    def publish(self, note: InternalNote, platform: str) -> Publication:
        if not self.settings.media_publication_enabled:
            return Publication(note, None)
        now = self.clock()
        self.revoke(tuple(key for key, value in self.records.items() if value.expires <= now))
        expires = int(now) + self.settings.media_ticket_ttl_seconds
        pending: dict[str, MediaRecord] = {}
        published: dict[tuple[str, MediaKind], str] = {}

        def register(url: str, kind: MediaKind) -> str:
            key = (url, kind)
            if key not in published:
                validate_media_url(url, platform, kind)
                resource_id = secrets.token_urlsafe(24)
                record = MediaRecord(url, platform, kind, expires)
                pending[resource_id] = record
                published[key] = (
                    f"{self.settings.media_public_origin.rstrip('/')}/api/v1/media/"
                    f"{resource_id}?exp={expires}&sig={self._sign(resource_id, record)}"
                )
            return published[key]

        def video(item: InternalVideo) -> InternalVideo:
            return replace(item, url=register(item.url, "video"))

        def cover(item: InternalCover | None) -> InternalCover | None:
            return replace(item, url=register(item.url, "image")) if item else None

        images = tuple(
            InternalImage(
                register(item.url, "image"),
                item.source_width,
                item.source_height,
                item.index,
                video(item.live_video) if item.live_video else None,
            )
            for item in note.images
        )
        result = replace(
            note,
            images=images,
            videos=tuple(video(item) for item in note.videos),
            cover=cover(note.cover),
            author_avatar=cover(note.author_avatar),
        )
        cost = sum(self.size(record) for record in pending.values())
        if (
            len(self.records) + len(pending) > self.settings.media_ticket_max_entries
            or self.bytes + cost > self.settings.media_ticket_max_bytes
        ):
            raise AppError("MEDIA_TICKET_CAPACITY", 503, True, retry_after=2)
        # No awaits: admission/commit is atomic on the required single event loop.
        self.records.update(pending)
        self.bytes += cost
        return Publication(result, datetime.fromtimestamp(expires, UTC), tuple(pending))
