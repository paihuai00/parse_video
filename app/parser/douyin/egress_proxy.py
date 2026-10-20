"""Loopback CONNECT proxy that pins Chromium egress to vetted public addresses."""

from __future__ import annotations

import asyncio
import socket
from contextlib import suppress

from app.parser.url_rules import is_public_address

MAX_PROXY_HEADER = 16 * 1024
WRITER_CLOSE_TIMEOUT = 1.0


async def _close_writer(writer: asyncio.StreamWriter) -> None:
    writer.close()
    with suppress(OSError, TimeoutError):
        await asyncio.wait_for(writer.wait_closed(), WRITER_CLOSE_TIMEOUT)


class _ByteBudget:
    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.used = 0
        self._lock = asyncio.Lock()

    async def consume(self, size: int) -> bool:
        async with self._lock:
            self.used += size
            return self.used <= self.limit


class BoundedConnectProxy:
    def __init__(
        self,
        allowed_hosts: frozenset[str],
        max_bytes: int,
        connect_timeout: float = 5.0,
    ) -> None:
        self.allowed_hosts = allowed_hosts
        self.budget = _ByteBudget(max_bytes)
        self.connect_timeout = connect_timeout
        self._server: asyncio.Server | None = None
        self._connections: set[asyncio.StreamWriter] = set()
        self._handlers: set[asyncio.Task[None]] = set()
        self._resolved: dict[str, tuple[str, ...]] = {}
        self._resolution_lock = asyncio.Lock()

    @property
    def server_url(self) -> str:
        if self._server is None or not self._server.sockets:
            raise RuntimeError("proxy has not started")
        port = self._server.sockets[0].getsockname()[1]
        return f"http://127.0.0.1:{port}"

    async def __aenter__(self) -> BoundedConnectProxy:
        self._server = await asyncio.start_server(
            self._handle, "127.0.0.1", 0, limit=MAX_PROXY_HEADER
        )
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._server is not None:
            self._server.close()
        handlers = tuple(self._handlers)
        for task in handlers:
            task.cancel()
        if handlers:
            await asyncio.gather(*handlers, return_exceptions=True)
        if self._server is not None:
            with suppress(TimeoutError):
                await asyncio.wait_for(self._server.wait_closed(), WRITER_CLOSE_TIMEOUT)
        writers = tuple(self._connections)
        await asyncio.gather(*(_close_writer(writer) for writer in writers))
        self._connections.clear()

    async def _resolve(self, host: str) -> tuple[str, ...]:
        async with self._resolution_lock:
            cached = self._resolved.get(host)
            if cached is not None:
                return cached
            loop = asyncio.get_running_loop()
            infos = await asyncio.wait_for(
                loop.getaddrinfo(host, 443, type=socket.SOCK_STREAM),
                self.connect_timeout,
            )
            addresses = tuple(dict.fromkeys(item[4][0] for item in infos))
            if not addresses or any(not is_public_address(address) for address in addresses):
                raise OSError("host did not resolve exclusively to public addresses")
            self._resolved[host] = addresses
            return addresses

    async def _connect(self, host: str) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        loop = asyncio.get_running_loop()
        expires_at = loop.time() + self.connect_timeout
        last_error: OSError | None = None
        for address in await self._resolve(host):
            remaining = expires_at - loop.time()
            if remaining <= 0:
                break
            try:
                return await asyncio.wait_for(asyncio.open_connection(address, 443), remaining)
            except OSError as exc:
                last_error = exc
        raise OSError("all vetted addresses failed") from last_error

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        handler = asyncio.current_task()
        if handler is not None:
            self._handlers.add(handler)
        self._connections.add(writer)
        upstream_writer: asyncio.StreamWriter | None = None
        try:
            header = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 5)
            if len(header) > MAX_PROXY_HEADER:
                raise ValueError("proxy header too large")
            first = header.split(b"\r\n", 1)[0].decode("ascii", errors="strict")
            method, authority, _ = first.split(" ", 2)
            host, separator, raw_port = authority.rpartition(":")
            normalized_host = host.lower().removesuffix(".")
            if (
                method != "CONNECT"
                or not separator
                or raw_port != "443"
                or normalized_host not in self.allowed_hosts
            ):
                writer.write(b"HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n")
                await writer.drain()
                return
            upstream_reader, upstream_writer = await self._connect(normalized_host)
            self._connections.add(upstream_writer)
            writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            await writer.drain()
            relays = {
                asyncio.create_task(self._relay(reader, upstream_writer)),
                asyncio.create_task(self._relay(upstream_reader, writer)),
            }
            _, pending = await asyncio.wait(relays, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
        except (OSError, ValueError, UnicodeError, asyncio.IncompleteReadError, TimeoutError):
            if not writer.is_closing():
                with suppress(OSError):
                    writer.write(b"HTTP/1.1 502 Bad Gateway\r\nConnection: close\r\n\r\n")
                    await writer.drain()
        finally:
            for connection in (upstream_writer, writer):
                if connection is not None:
                    self._connections.discard(connection)
                    await _close_writer(connection)
            if handler is not None:
                self._handlers.discard(handler)

    async def _relay(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            while chunk := await reader.read(64 * 1024):
                if not await self.budget.consume(len(chunk)):
                    return
                writer.write(chunk)
                await writer.drain()
        except (ConnectionError, OSError):
            return
