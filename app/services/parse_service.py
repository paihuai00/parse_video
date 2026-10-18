"""Compose deadline, rate, cache, coalescing, parsing, and admission."""

from __future__ import annotations

import asyncio
import hashlib
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.config import Settings
from app.errors import AppError
from app.models import InternalNote
from app.parser.client import Deadline, PageResponse, XiaohongshuClient
from app.parser.media import normalize_note
from app.parser.state_reader import decode_initial_state, select_note
from app.parser.url_rules import cache_key
from app.services.admission import AdmissionController
from app.services.cache import CacheEntry, ResultCache
from app.services.rate_limit import RateLimiter


class PageFetcher(Protocol):
    async def fetch(self, raw_url: str, deadline: Deadline) -> PageResponse: ...


@dataclass(frozen=True)
class ServiceResult:
    note: InternalNote
    parsed_at: datetime
    expires_at: datetime
    cache_hit: bool


@dataclass
class InFlight:
    task: asyncio.Task[CacheEntry]
    waiters: int = 0


class ParseService:
    def __init__(self, settings: Settings, client: PageFetcher | None = None) -> None:
        self.settings = settings
        self.client = client or XiaohongshuClient(settings)
        self.cache = ResultCache(settings.cache_ttl_seconds, settings.cache_max_entries)
        self.rate_limiter = RateLimiter(settings.rate_limit_per_minute)
        self.admission = AdmissionController(
            settings.upstream_concurrency, settings.queue_capacity, settings.queue_wait_seconds
        )
        self._inflight: dict[str, InFlight] = {}
        self._inflight_lock = asyncio.Lock()

    async def parse(self, raw_url: str, refresh: bool, api_key: str) -> ServiceResult:
        key_id = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
        self.rate_limiter.check(key_id)
        key = cache_key(raw_url)
        if not refresh:
            cached = self.cache.get(key)
            if cached:
                return ServiceResult(cached.value, cached.parsed_at, cached.expires_at, True)

        deadline = Deadline(self.settings.request_timeout_seconds)
        flight_key = f"refresh:{key}" if refresh else key
        is_follower = False
        async with self._inflight_lock:
            flight = self._inflight.get(flight_key)
            if flight is None:
                if (
                    len(self._inflight)
                    >= self.settings.upstream_concurrency + self.settings.queue_capacity
                ):
                    raise AppError("BUSY", 503, True, "in-flight table is full", 2)
                task = asyncio.create_task(self._run_leader(raw_url, key, deadline))
                flight = InFlight(task=task)
                self._inflight[flight_key] = flight
            else:
                is_follower = True
            flight.waiters += 1

        try:
            if is_follower:
                async with self.admission.waiter():
                    entry = await asyncio.wait_for(
                        asyncio.shield(flight.task), deadline.remaining()
                    )
            else:
                entry = await asyncio.wait_for(asyncio.shield(flight.task), deadline.remaining())
            return ServiceResult(entry.value, entry.parsed_at, entry.expires_at, False)
        except TimeoutError as exc:
            raise AppError("UPSTREAM_TIMEOUT", 504, True, "caller deadline exceeded") from exc
        finally:
            orphaned_task: asyncio.Task[CacheEntry] | None = None
            async with self._inflight_lock:
                flight.waiters -= 1
                if flight.waiters == 0:
                    if not flight.task.done():
                        flight.task.cancel()
                        orphaned_task = flight.task
                    self._inflight.pop(flight_key, None)
            if orphaned_task is not None:
                with suppress(asyncio.CancelledError, Exception):
                    await orphaned_task

    async def _run_leader(
        self, raw_url: str, cache_identity: str, deadline: Deadline
    ) -> CacheEntry:
        async with self.admission.slot(deadline):
            page = await self.client.fetch(raw_url, deadline)
            deadline.remaining()
            state = decode_initial_state(page.html)
            note = normalize_note(page.note_id, select_note(state, page.note_id))
            deadline.remaining()
            return self.cache.put(cache_identity, note)
