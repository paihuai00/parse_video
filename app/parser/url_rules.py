"""Fail-closed Xiaohongshu URL and DNS policy."""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import SplitResult, urlsplit, urlunsplit

from app.errors import AppError, invalid_url

ALLOWED_HOSTS = frozenset({"www.xiaohongshu.com", "xiaohongshu.com", "xhslink.com"})
DETAIL_HOSTS = frozenset({"www.xiaohongshu.com", "xiaohongshu.com"})
NOTE_ID_LENGTH = 24


@dataclass(frozen=True)
class ParsedUrl:
    normalized_url: str
    host: str
    port: int
    note_id: str | None
    is_short_link: bool


@dataclass(frozen=True)
class ResolvedHop:
    normalized_url: str
    host: str
    port: int
    note_id: str | None
    addresses: tuple[str, ...]

    @property
    def resolve_entries(self) -> list[str]:
        return [f"{self.host}:{self.port}:{','.join(self.addresses)}"]


def _normalized_host(parts: SplitResult) -> str:
    if parts.username is not None or parts.password is not None:
        raise invalid_url("URL credentials are forbidden")
    try:
        host = (parts.hostname or "").encode("idna").decode("ascii").lower().rstrip(".")
    except UnicodeError as exc:
        raise invalid_url("invalid hostname") from exc
    if not host or host not in ALLOWED_HOSTS:
        raise invalid_url("unsupported host")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return host
    raise invalid_url("IP literals are forbidden")


def _note_id_from_path(host: str, path: str) -> str | None:
    if host == "xhslink.com":
        if path in {"", "/"}:
            raise invalid_url("short link path is missing")
        return None
    segments = [segment for segment in path.split("/") if segment]
    if len(segments) != 3 and len(segments) != 2:
        raise invalid_url("unsupported note path")
    if len(segments) == 3:
        valid = segments[0] == "discovery" and segments[1] == "item"
        note_id = segments[2]
    else:
        valid = segments[0] == "explore"
        note_id = segments[1]
    if (
        not valid
        or len(note_id) != NOTE_ID_LENGTH
        or any(c not in "0123456789abcdefABCDEF" for c in note_id)
    ):
        raise invalid_url("unsupported note path or note id")
    return note_id.lower()


def parse_url(raw_url: str) -> ParsedUrl:
    if len(raw_url) > 4096:
        raise invalid_url("URL is too long")
    if any(char.isspace() or ord(char) == 127 for char in raw_url):
        raise invalid_url("URL contains whitespace or control characters")
    try:
        parts = urlsplit(raw_url)
    except ValueError as exc:
        raise invalid_url("malformed URL") from exc
    scheme = parts.scheme.lower()
    if scheme not in {"http", "https"}:
        raise invalid_url("only HTTP(S) is supported")
    if parts.fragment:
        parts = parts._replace(fragment="")
    host = _normalized_host(parts)
    try:
        explicit_port = parts.port
    except ValueError as exc:
        raise invalid_url("invalid port") from exc
    expected_port = 443 if scheme == "https" else 80
    if explicit_port is not None and explicit_port != expected_port:
        raise invalid_url("unexpected port")
    note_id = _note_id_from_path(host, parts.path)
    netloc = host if explicit_port is None else f"{host}:{explicit_port}"
    normalized = urlunsplit((scheme, netloc, parts.path, parts.query, ""))
    return ParsedUrl(normalized, host, expected_port, note_id, host == "xhslink.com")


def is_public_address(address: str) -> bool:
    try:
        parsed = ipaddress.ip_address(address.split("%", 1)[0])
    except ValueError:
        return False
    return parsed.is_global and not parsed.is_multicast


async def resolve_url(raw_url: str) -> ResolvedHop:
    parsed = parse_url(raw_url)
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(
            parsed.host,
            parsed.port,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        )
    except socket.gaierror as exc:
        raise AppError("UPSTREAM_BAD_RESPONSE", 502, True, "DNS resolution failed") from exc
    addresses = tuple(dict.fromkeys(info[4][0] for info in infos))
    if not addresses or any(not is_public_address(address) for address in addresses):
        raise invalid_url("hostname resolved to a non-public address")
    return ResolvedHop(
        normalized_url=parsed.normalized_url,
        host=parsed.host,
        port=parsed.port,
        note_id=parsed.note_id,
        addresses=addresses,
    )


def cache_key(raw_url: str) -> str:
    normalized = parse_url(raw_url).normalized_url
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
