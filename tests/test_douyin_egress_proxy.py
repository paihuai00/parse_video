from __future__ import annotations

import asyncio

import pytest

from app.parser.douyin.egress_proxy import BoundedConnectProxy


async def test_proxy_rejects_unknown_hosts_before_connecting() -> None:
    async with BoundedConnectProxy(frozenset({"www.douyin.com"}), 1024) as proxy:
        port = int(proxy.server_url.rsplit(":", 1)[1])
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(b"CONNECT 127.0.0.1:443 HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n")
        await writer.drain()
        response = await reader.read(1024)
        writer.close()
        await writer.wait_closed()
    assert response.startswith(b"HTTP/1.1 403")


async def test_proxy_rejects_a_host_if_any_dns_answer_is_private(monkeypatch) -> None:
    async def fake_getaddrinfo(*args, **kwargs):
        _ = args, kwargs
        return [
            (2, 1, 6, "", ("8.8.8.8", 443)),
            (2, 1, 6, "", ("127.0.0.1", 443)),
        ]

    loop = asyncio.get_running_loop()
    monkeypatch.setattr(loop, "getaddrinfo", fake_getaddrinfo)
    proxy = BoundedConnectProxy(frozenset({"www.douyin.com"}), 1024)
    with pytest.raises(OSError):
        await proxy._resolve("www.douyin.com")


async def test_proxy_bounds_dns_resolution_time(monkeypatch) -> None:
    async def blocked_getaddrinfo(*args, **kwargs):
        _ = args, kwargs
        await asyncio.Event().wait()

    loop = asyncio.get_running_loop()
    monkeypatch.setattr(loop, "getaddrinfo", blocked_getaddrinfo)
    proxy = BoundedConnectProxy(
        frozenset({"www.douyin.com"}),
        1024,
        connect_timeout=0.01,
    )
    with pytest.raises(TimeoutError):
        await proxy._resolve("www.douyin.com")


async def test_proxy_exit_cancels_in_progress_handlers(monkeypatch) -> None:
    started = asyncio.Event()

    async def blocked_connect(_host: str):
        started.set()
        await asyncio.Event().wait()

    proxy = BoundedConnectProxy(frozenset({"www.douyin.com"}), 1024)
    monkeypatch.setattr(proxy, "_connect", blocked_connect)
    async with proxy:
        proxy_port = int(proxy.server_url.rsplit(":", 1)[1])
        _, writer = await asyncio.open_connection("127.0.0.1", proxy_port)
        writer.write(b"CONNECT www.douyin.com:443 HTTP/1.1\r\nHost: www.douyin.com:443\r\n\r\n")
        await writer.drain()
        await asyncio.wait_for(started.wait(), 1)
        assert proxy._handlers
    await asyncio.sleep(0)
    assert not proxy._handlers
    writer.close()
    await asyncio.wait_for(writer.wait_closed(), 1)


async def test_proxy_stops_a_tunnel_when_the_shared_byte_budget_is_exhausted(
    monkeypatch,
) -> None:
    received = bytearray()

    async def upstream(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        received.extend(await reader.read())
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(upstream, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]

    async def fake_connect(_host: str):
        return await asyncio.open_connection("127.0.0.1", port)

    proxy = BoundedConnectProxy(frozenset({"www.douyin.com"}), 8)
    monkeypatch.setattr(proxy, "_connect", fake_connect)
    try:
        async with proxy:
            proxy_port = int(proxy.server_url.rsplit(":", 1)[1])
            reader, writer = await asyncio.open_connection("127.0.0.1", proxy_port)
            writer.write(b"CONNECT www.douyin.com:443 HTTP/1.1\r\nHost: www.douyin.com:443\r\n\r\n")
            await writer.drain()
            assert (await reader.readuntil(b"\r\n\r\n")).startswith(b"HTTP/1.1 200")
            writer.write(b"too-many-bytes")
            await writer.drain()
            assert await asyncio.wait_for(reader.read(), 1) == b""
            writer.close()
            await writer.wait_closed()
    finally:
        server.close()
        await server.wait_closed()
    assert received == b""
    assert proxy.budget.used > proxy.budget.limit
