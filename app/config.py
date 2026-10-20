"""Environment-backed application configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass


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
    if value <= 0:
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
        )
