"""Bounded per-key sliding-window rate limiting."""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable

from app.errors import AppError


class RateLimiter:
    def __init__(
        self,
        limit: int,
        window_seconds: float = 60.0,
        max_keys: int = 1024,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self.max_keys = max_keys
        self._clock = clock
        self._records: dict[str, deque[float]] = {}

    def check(self, key_id: str) -> None:
        now = self._clock()
        cutoff = now - self.window_seconds
        self._cleanup(cutoff)
        records = self._records.setdefault(key_id, deque())
        while records and records[0] <= cutoff:
            records.popleft()
        if len(records) >= self.limit:
            retry_after = max(1, int(records[0] + self.window_seconds - now) + 1)
            raise AppError("RATE_LIMITED", 429, True, "per-key rolling limit exceeded", retry_after)
        records.append(now)
        if len(self._records) > self.max_keys:
            oldest = min(self._records, key=lambda item: self._records[item][-1])
            if oldest != key_id:
                self._records.pop(oldest, None)

    def _cleanup(self, cutoff: float) -> None:
        stale: list[str] = []
        for key, records in self._records.items():
            while records and records[0] <= cutoff:
                records.popleft()
            if not records:
                stale.append(key)
        for key in stale:
            self._records.pop(key, None)
