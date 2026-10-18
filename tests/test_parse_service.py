from __future__ import annotations

import asyncio

import pytest

from app.config import Settings
from app.errors import AppError
from app.parser.client import PageResponse
from app.services.parse_service import ParseService


class FakeClient:
    def __init__(self, html: str) -> None:
        self.html = html
        self.calls = 0
        self.gate = asyncio.Event()
        self.gate.set()

    async def fetch(self, raw_url, deadline):
        _ = raw_url, deadline
        self.calls += 1
        await self.gate.wait()
        return PageResponse(self.html, raw_url, "6ad2355f000000001a027848")


def settings(**overrides) -> Settings:
    values = {"api_key": "test-key", "environment": "test"}
    values.update(overrides)
    return Settings(**values)


async def test_cache_hit_refresh_and_same_key_coalescing(fixture_html) -> None:
    client = FakeClient(fixture_html("image_note.html"))
    service = ParseService(settings(), client)
    url = "https://www.xiaohongshu.com/explore/6ad2355f000000001a027848?xsec_token=one"

    client.gate.clear()
    first = asyncio.create_task(service.parse(url, False, "test-key"))
    second = asyncio.create_task(service.parse(url, False, "test-key"))
    await asyncio.sleep(0.01)
    assert client.calls == 1
    client.gate.set()
    values = await asyncio.gather(first, second)
    assert client.calls == 1
    assert values[0].note == values[1].note

    cached = await service.parse(url, False, "test-key")
    assert cached.cache_hit
    refreshed = await service.parse(url, True, "test-key")
    assert not refreshed.cache_hit
    assert client.calls == 2


async def test_rate_limit_is_applied_before_cache_lookup(fixture_html) -> None:
    client = FakeClient(fixture_html("image_note.html"))
    service = ParseService(settings(rate_limit_per_minute=1), client)
    url = "https://www.xiaohongshu.com/explore/6ad2355f000000001a027848"
    await service.parse(url, False, "test-key")
    with pytest.raises(AppError) as caught:
        await service.parse(url, False, "test-key")
    assert caught.value.code == "RATE_LIMITED"
    assert client.calls == 1


async def test_last_cancelled_waiter_cancels_orphaned_work(fixture_html) -> None:
    client = FakeClient(fixture_html("image_note.html"))
    client.gate.clear()
    service = ParseService(settings(request_timeout_seconds=1), client)
    url = "https://www.xiaohongshu.com/explore/6ad2355f000000001a027848"
    task = asyncio.create_task(service.parse(url, False, "test-key"))
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.sleep(0)
    assert service._inflight == {}
    assert service.admission.active == 0


async def test_coalesced_followers_share_the_bounded_waiter_budget(fixture_html) -> None:
    client = FakeClient(fixture_html("image_note.html"))
    client.gate.clear()
    service = ParseService(settings(upstream_concurrency=1, queue_capacity=2), client)
    url = "https://www.xiaohongshu.com/explore/6ad2355f000000001a027848"

    leader = asyncio.create_task(service.parse(url, False, "test-key"))
    while client.calls < 1:
        await asyncio.sleep(0)
    followers = [asyncio.create_task(service.parse(url, False, "test-key")) for _ in range(2)]
    while service.admission.waiting < 2:
        await asyncio.sleep(0)

    with pytest.raises(AppError) as caught:
        await service.parse(url, False, "test-key")
    assert caught.value.code == "BUSY"
    assert service.admission.waiting == 2

    client.gate.set()
    await asyncio.gather(leader, *followers)
    assert service.admission.waiting == 0


async def test_cancelling_one_caller_does_not_cancel_shared_work(fixture_html) -> None:
    client = FakeClient(fixture_html("image_note.html"))
    client.gate.clear()
    service = ParseService(settings(), client)
    url = "https://www.xiaohongshu.com/explore/6ad2355f000000001a027848"

    first = asyncio.create_task(service.parse(url, False, "test-key"))
    while client.calls < 1:
        await asyncio.sleep(0)
    second = asyncio.create_task(service.parse(url, False, "test-key"))
    while service.admission.waiting < 1:
        await asyncio.sleep(0)
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first

    client.gate.set()
    result = await second
    assert result.note.note_id == "6ad2355f000000001a027848"
    assert client.calls == 1
    assert service.admission.active == 0
    assert service.admission.waiting == 0


async def test_unique_requests_obey_queue_timeout(fixture_html) -> None:
    client = FakeClient(fixture_html("image_note.html"))
    client.gate.clear()
    service = ParseService(
        settings(upstream_concurrency=1, queue_capacity=1, queue_wait_seconds=0.01), client
    )
    first_url = "https://www.xiaohongshu.com/explore/6ad2355f000000001a027848?token=one"
    second_url = "https://www.xiaohongshu.com/explore/6ad2355f000000001a027848?token=two"
    first = asyncio.create_task(service.parse(first_url, False, "test-key"))
    while client.calls < 1:
        await asyncio.sleep(0)

    with pytest.raises(AppError) as caught:
        await service.parse(second_url, False, "test-key")
    assert caught.value.code == "BUSY"

    client.gate.set()
    await first
    assert service.admission.active == 0
    assert service.admission.waiting == 0
