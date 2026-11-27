"""Environment-backed application configuration."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from urllib.parse import urlsplit


def _positive_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if value <= 0:
        raise RuntimeError(f"{name} must be positive")
    return value


def _positive_float(name: str, default: float) -> float:
    raw = os.getenv(name, str(default))
    try:
        value = float(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a number") from exc
    if not math.isfinite(value) or value <= 0:
        raise RuntimeError(f"{name} must be positive")
    return value


@dataclass(frozen=True)
class Settings:
    api_key: str
    environment: str = "production"
    impersonate: str = "chrome136"
    request_timeout_seconds: float = 20.0
    connect_timeout_seconds: float = 5.0
    upstream_concurrency: int = 2
    queue_capacity: int = 4
    queue_wait_seconds: float = 2.0
    cache_ttl_seconds: float = 120.0
    cache_max_entries: int = 256
    rate_limit_per_minute: int = 20
    max_redirects: int = 3
    max_html_bytes: int = 2 * 1024 * 1024
    douyin_browser_concurrency: int = 1
    douyin_browser_max_requests: int = 500
    douyin_browser_max_bytes: int = 32 * 1024 * 1024
    douyin_state_max_bytes: int = 2 * 1024 * 1024
    douyin_browser_channel: str | None = None
    media_publication_enabled: bool = False
    media_public_origin: str = "https://parser.example.com"
    media_signing_key: str = ""
    media_ticket_ttl_seconds: int = 1800
    media_ticket_max_entries: int = 2048
    media_ticket_max_bytes: int = 2 * 1024 * 1024
    media_concurrency: int = 2
    media_queue_capacity: int = 4
    media_queue_wait_seconds: float = 2.0
    media_timeout_seconds: float = 480.0
    media_idle_timeout_seconds: float = 30.0
    media_max_bytes: int = 200 * 1024 * 1024
    media_rate_limit_per_minute: int = 120
    provider_max_json_bytes: int = 1024 * 1024
    ifphp_api_key: str = ""

    def __post_init__(self) -> None:
        parts = urlsplit(self.media_public_origin)
        if (
            parts.scheme != "https"
            or not parts.hostname
            or parts.username
            or parts.password
            or parts.port not in {None, 443}
            or parts.path not in {"", "/"}
            or parts.query
            or parts.fragment
        ):
            raise RuntimeError("MEDIA_PUBLIC_ORIGIN must be an HTTPS origin")
        if self.media_publication_enabled and len(self.media_signing_key.encode()) < 32:
            raise RuntimeError("MEDIA_SIGNING_KEY must contain at least 32 bytes")

    @classmethod
    def from_env(cls) -> Settings:
        environment = os.getenv("XHS_ENV", "production").strip().lower()
        api_key = os.getenv("XHS_API_KEY", "").strip()
        if environment == "production" and not api_key:
            raise RuntimeError("XHS_API_KEY must be non-empty in production")
        return cls(
            api_key=api_key,
            environment=environment,
            impersonate=os.getenv("XHS_IMPERSONATE", "chrome136").strip() or "chrome136",
            request_timeout_seconds=_positive_float("XHS_REQUEST_TIMEOUT_SECONDS", 20),
            connect_timeout_seconds=_positive_float("XHS_CONNECT_TIMEOUT_SECONDS", 5),
            upstream_concurrency=_positive_int("XHS_UPSTREAM_CONCURRENCY", 2),
            queue_capacity=_positive_int("XHS_QUEUE_CAPACITY", 4),
            queue_wait_seconds=_positive_float("XHS_QUEUE_WAIT_SECONDS", 2),
            cache_ttl_seconds=_positive_float("XHS_CACHE_TTL_SECONDS", 120),
            cache_max_entries=_positive_int("XHS_CACHE_MAX_ENTRIES", 256),
            rate_limit_per_minute=_positive_int("XHS_RATE_LIMIT_PER_MINUTE", 20),
            max_redirects=_positive_int("XHS_MAX_REDIRECTS", 3),
            max_html_bytes=_positive_int("XHS_MAX_HTML_BYTES", 2 * 1024 * 1024),
            douyin_browser_concurrency=_positive_int("XHS_DOUYIN_BROWSER_CONCURRENCY", 1),
            douyin_browser_max_requests=_positive_int("XHS_DOUYIN_BROWSER_MAX_REQUESTS", 500),
            douyin_browser_max_bytes=_positive_int(
                "XHS_DOUYIN_BROWSER_MAX_BYTES", 32 * 1024 * 1024
            ),
            douyin_state_max_bytes=_positive_int("XHS_DOUYIN_STATE_MAX_BYTES", 2 * 1024 * 1024),
            douyin_browser_channel=(os.getenv("XHS_DOUYIN_BROWSER_CHANNEL", "").strip() or None),
            media_publication_enabled=os.getenv("MEDIA_PUBLICATION_ENABLED", "false").lower()
            == "true",
            media_public_origin=os.getenv("MEDIA_PUBLIC_ORIGIN", "https://parser.example.com"),
            media_signing_key=os.getenv("MEDIA_SIGNING_KEY", ""),
            media_ticket_ttl_seconds=_positive_int("MEDIA_TICKET_TTL_SECONDS", 1800),
            media_ticket_max_entries=_positive_int("MEDIA_TICKET_MAX_ENTRIES", 2048),
            media_ticket_max_bytes=_positive_int("MEDIA_TICKET_MAX_BYTES", 2 * 1024 * 1024),
            media_concurrency=_positive_int("MEDIA_CONCURRENCY", 2),
            media_queue_capacity=_positive_int("MEDIA_QUEUE_CAPACITY", 4),
            media_queue_wait_seconds=_positive_float("MEDIA_QUEUE_WAIT_SECONDS", 2),
            media_timeout_seconds=_positive_float("MEDIA_TIMEOUT_SECONDS", 480),
            media_idle_timeout_seconds=_positive_float("MEDIA_IDLE_TIMEOUT_SECONDS", 30),
            media_max_bytes=_positive_int("MEDIA_MAX_BYTES", 200 * 1024 * 1024),
            media_rate_limit_per_minute=_positive_int("MEDIA_RATE_LIMIT_PER_MINUTE", 120),
            provider_max_json_bytes=_positive_int("PROVIDER_MAX_JSON_BYTES", 1024 * 1024),
            ifphp_api_key=os.getenv("IFPHP_API_KEY", ""),
        )
