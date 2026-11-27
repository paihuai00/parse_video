"""Offline wire-level proof for the pinned, pull-driven media transport."""

from __future__ import annotations

import asyncio
import ssl

import httpcore
import pytest

from app.errors import AppError
from app.services import safe_http
from app.services.safe_http import PinnedBackend, SafeHTTP


class Wire(httpcore.AsyncMockStream):
    def __init__(self):
        super().__init__(
            [
                b"HTTP/1.1 200 OK\r\nContent-Length: 12\r\n\r\n",
                b"first-",
                b"second",
            ]
        )
        self.writes = []
        self.reads = 0
        self.tls_name = None
        self.context = None

    async def read(self, max_bytes, timeout=None):
        self.reads += 1
        return await super().read(max_bytes, timeout)

    async def write(self, buffer, timeout=None):
        self.writes.append(buffer)

    async def start_tls(self, ssl_context, server_hostname=None, timeout=None):
        self.tls_name, self.context = server_hostname, ssl_context
        return self


async def test_wire_preserves_target_tls_pinning_and_pull_backpressure(monkeypatch):
    wire = Wire()
    connections = []

    class Backend:
        async def connect_tcp(self, host, port, timeout, local_address, socket_options):
            connections.append((host, port))
            return wire

    async def resolve(host, port):
        assert host == "p26-sign.douyinpic.com"
        return ("8.8.8.8",)

    monkeypatch.setattr(safe_http, "AnyIOBackend", Backend)
    monkeypatch.setattr(safe_http, "resolve_public_addresses", resolve)
    raw = "https://p26-sign.douyinpic.com/a;param/%2f!x?sig=a%2Bb+z&x=1&x=2&empty="
    async with SafeHTTP().stream("GET", raw) as response:
        assert connections == [("8.8.8.8", 443)]
        assert wire.tls_name == "p26-sign.douyinpic.com"
        assert wire.context.verify_mode == ssl.CERT_REQUIRED
        assert wire.context.check_hostname
        assert b"GET /a;param/%2f!x?sig=a%2Bb+z&x=1&x=2&empty= HTTP/1.1" in b"".join(wire.writes)
        assert b"Host: p26-sign.douyinpic.com" in b"".join(wire.writes)
        reads = wire.reads
        await asyncio.sleep(0)
        assert wire.reads == reads  # no producer/queue downloading behind the consumer
        iterator = response.aiter_stream()
        assert await anext(iterator) == b"first-"
        reads = wire.reads
        await asyncio.sleep(0)
        assert wire.reads == reads
    assert wire._closed


async def test_cancel_closes_upstream_and_no_environment_proxy(monkeypatch):
    wire = Wire()
    entered = asyncio.Event()
    gate = asyncio.Event()

    class Backend:
        async def connect_tcp(self, host, port, timeout, local_address, socket_options):
            assert host == "8.8.8.8"
            return wire

    async def resolve(host, port):
        return ("8.8.8.8",)

    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:1234")
    monkeypatch.setattr(safe_http, "AnyIOBackend", Backend)
    monkeypatch.setattr(safe_http, "resolve_public_addresses", resolve)

    async def consume():
        async with SafeHTTP().stream("GET", "https://p26-sign.douyinpic.com/a"):
            entered.set()
            await gate.wait()

    task = asyncio.create_task(consume())
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert wire._closed


async def test_remaining_vetted_ips_are_attempted_in_connect_budget():
    backend = PinnedBackend("safe.example", 443, ("2001:4860:4860::8888", "8.8.8.8"))
    seen = []

    class Delegate:
        async def connect_tcp(self, host, port, timeout, local_address, socket_options):
            seen.append((host, timeout))
            if len(seen) == 1:
                raise httpcore.ConnectError("offline IPv6")
            return Wire()

    backend.backend = Delegate()
    await backend.connect_tcp("safe.example", 443, timeout=2)
    assert [v[0] for v in seen] == ["2001:4860:4860::8888", "8.8.8.8"]
    assert seen[0][1] <= 1 and seen[1][1] <= 2
    with pytest.raises(httpcore.ConnectError):
        await backend.connect_tcp("other.example", 443)


async def test_unsafe_dns_never_connects(monkeypatch):
    async def resolve(host, port):
        raise AppError("INVALID_URL", 400)

    monkeypatch.setattr(safe_http, "resolve_public_addresses", resolve)
    with pytest.raises(AppError):
        async with SafeHTTP().stream("GET", "https://p26-sign.douyinpic.com/a"):
            pytest.fail("must not connect")
