"""Exception-safe active/queued upstream admission."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from app.errors import AppError
from app.parser.client import Deadline


class AdmissionController:
    def __init__(self, active_limit: int, queue_capacity: int, queue_wait_seconds: float) -> None:
        self.active_limit = active_limit
        self.queue_capacity = queue_capacity
        self.queue_wait_seconds = queue_wait_seconds
        self.active = 0
        self.waiting = 0
        self._condition = asyncio.Condition()

    @asynccontextmanager
    async def waiter(self) -> AsyncIterator[None]:
        """Reserve one bounded waiting place for a coalesced caller."""
        async with self._condition:
            if self.waiting >= self.queue_capacity:
                raise AppError("BUSY", 503, True, "upstream queue is full", 2)
            self.waiting += 1
        try:
            yield
        finally:
            async with self._condition:
                self.waiting -= 1

    @asynccontextmanager
    async def slot(self, deadline: Deadline) -> AsyncIterator[None]:
        acquired = False
        queued = False
        async with self._condition:
            if self.active >= self.active_limit:
                if self.waiting >= self.queue_capacity:
                    raise AppError("BUSY", 503, True, "upstream queue is full", 2)
                self.waiting += 1
                queued = True
                wait_limit = min(self.queue_wait_seconds, deadline.remaining())
                end = time.monotonic() + wait_limit
                try:
                    while self.active >= self.active_limit:
                        remaining = end - time.monotonic()
                        if remaining <= 0:
                            raise AppError("BUSY", 503, True, "upstream queue wait timed out", 2)
                        try:
                            await asyncio.wait_for(self._condition.wait(), remaining)
                        except TimeoutError as exc:
                            raise AppError(
                                "BUSY", 503, True, "upstream queue wait timed out", 2
                            ) from exc
                finally:
                    self.waiting -= 1
                    queued = False
            self.active += 1
            acquired = True
        try:
            yield
        finally:
            if acquired:
                async with self._condition:
                    self.active -= 1
                    self._condition.notify(1)
            elif queued:
                async with self._condition:
                    self.waiting -= 1
