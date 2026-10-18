from __future__ import annotations

import asyncio

import pytest

from app.errors import AppError
from app.parser.client import Deadline
from app.services.admission import AdmissionController


async def test_queue_capacity_and_release_after_cancellation() -> None:
    admission = AdmissionController(active_limit=1, queue_capacity=1, queue_wait_seconds=0.05)
    entered = asyncio.Event()
    release = asyncio.Event()

    async def holder() -> None:
        async with admission.slot(Deadline(1)):
            entered.set()
            await release.wait()

    holder_task = asyncio.create_task(holder())
    await entered.wait()
    waiter = asyncio.create_task(_wait_for_slot(admission))
    await asyncio.sleep(0)
    with pytest.raises(AppError) as caught:
        async with admission.slot(Deadline(1)):
            pass
    assert caught.value.code == "BUSY"
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    assert admission.waiting == 0
    release.set()
    await holder_task
    assert admission.active == 0


async def _wait_for_slot(admission: AdmissionController) -> None:
    async with admission.slot(Deadline(1)):
        pass
