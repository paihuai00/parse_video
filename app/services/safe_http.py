"""Pull-based HTTP/1 transport with vetted-IP connections and original TLS identity.

httpcore is exactly pinned. A fresh one-connection pool per hop prevents a cached
connection or resolver from bypassing that hop's DNS decision. No environment
proxies, redirects, content decoding, response buffering, or background reader.
"""

from __future__ import annotations

import asyncio
import ssl
import time
from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager

import httpcore
from httpcore._backends.anyio import AnyIOBackend
from httpcore._backends.base import SOCKET_OPTION, AsyncNetworkBackend, AsyncNetworkStream

from app.errors import AppError
from app.parser.url_rules import resolve_public_addresses
from app.services.media_policy import public_http_parts


class PinnedBackend(AsyncNetworkBackend):
    def __init__(self, host: str, port: int, addresses: tuple[str, ...]) -> None:
        self.host, self.port, self.addresses = host, port, addresses
        self.backend = AnyIOBackend()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[SOCKET_OPTION] | None = None,
    ) -> AsyncNetworkStream:
        if (host, port) != (self.host, self.port):
            raise httpcore.ConnectError("unapproved origin")
        # Numeric IP only. TLS is started by httpcore using the original host.
        end = time.monotonic() + timeout if timeout is not None else None
        for index, address in enumerate(self.addresses):
            remaining = end - time.monotonic() if end is not None else None
            if remaining is not None and remaining <= 0:
                raise httpcore.ConnectTimeout("vetted connection budget exhausted")
            budget = remaining / (len(self.addresses) - index) if remaining else None
            try:
                return await self.backend.connect_tcp(
                    address, port, budget, local_address, socket_options
                )
            except (httpcore.ConnectError, httpcore.ConnectTimeout):
                if index == len(self.addresses) - 1:
                    raise
        raise httpcore.ConnectError("no vetted address")


class SafeHTTP:
    def __init__(self, connect_timeout: float = 5.0, idle_timeout: float = 30.0) -> None:
        self.connect_timeout = connect_timeout
        self.idle_timeout = idle_timeout

    @asynccontextmanager
    async def stream(
        self,
        method: str,
        raw_url: str,
        headers: list[tuple[bytes, bytes]] | None = None,
    ) -> AsyncIterator[httpcore.Response]:
        parts = public_http_parts(raw_url)
        host = parts.hostname or ""
        port = parts.port or (443 if parts.scheme == "https" else 80)
        addresses = await asyncio.wait_for(
            resolve_public_addresses(host, port), self.connect_timeout
        )
        # SplitResult.path keeps semicolon parameters. Preserve even a trailing '?'.
        target = (parts.path or "/") + ("?" + parts.query if "?" in raw_url else "")
        url = httpcore.URL(scheme=parts.scheme, host=host, port=port, target=target)
        async with (
            httpcore.AsyncConnectionPool(
                ssl_context=ssl.create_default_context(),
                max_connections=1,
                max_keepalive_connections=0,
                retries=0,
                http2=False,
                network_backend=PinnedBackend(host, port, addresses),
            ) as pool,
            pool.stream(
                method,
                url,
                headers=headers,
                extensions={
                    "timeout": {
                        "connect": self.connect_timeout,
                        "read": self.idle_timeout,
                        "write": self.idle_timeout,
                        "pool": self.connect_timeout,
                    }
                },
            ) as response,
        ):
            yield response


def response_headers(response: httpcore.Response) -> dict[str, str]:
    values: dict[str, str] = {}
    for key, value in response.headers:
        name = key.decode("ascii").lower()
        if name in values and name in {
            "content-length",
            "content-type",
            "location",
            "content-encoding",
        }:
            raise AppError("MEDIA_UPSTREAM_BAD_RESPONSE", 502, detail="ambiguous response headers")
        values[name] = value.decode("latin1")
    return values
