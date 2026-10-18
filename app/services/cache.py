"""Success-only bounded TTL/LRU cache."""

from __future__ import annotations

import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.models import InternalNote


@dataclass(frozen=True)
class CacheEntry:
    value: InternalNote
    parsed_at: datetime
    expires_at: datetime
    monotonic_expires_at: float


class ResultCache:
    def __init__(
        self, ttl_seconds: float, max_entries: int, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._clock = clock
        self._entries: OrderedDict[str, CacheEntry] = OrderedDict()

    def get(self, key: str) -> CacheEntry | None:
        now = self._clock()
        self._remove_expired(now)
        entry = self._entries.get(key)
        if entry is None:
            return None
        self._entries.move_to_end(key)
        return entry

    def put(self, key: str, value: InternalNote, parsed_at: datetime | None = None) -> CacheEntry:
        now = self._clock()
        parsed = parsed_at or datetime.now(UTC)
        entry = CacheEntry(
            value=value,
            parsed_at=parsed,
            expires_at=parsed + timedelta(seconds=self.ttl_seconds),
            monotonic_expires_at=now + self.ttl_seconds,
        )
        self._remove_expired(now)
        self._entries[key] = entry
        self._entries.move_to_end(key)
        while len(self._entries) > self.max_entries:
            self._entries.popitem(last=False)
        return entry

    def _remove_expired(self, now: float) -> None:
        expired = [key for key, entry in self._entries.items() if entry.monotonic_expires_at <= now]
        for key in expired:
            self._entries.pop(key, None)

    def __len__(self) -> int:
        self._remove_expired(self._clock())
        return len(self._entries)
