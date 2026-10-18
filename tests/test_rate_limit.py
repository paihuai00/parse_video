from __future__ import annotations

import pytest

from app.errors import AppError
from app.services.rate_limit import RateLimiter


def test_rolling_limit_and_expiry() -> None:
    now = 0.0
    limiter = RateLimiter(2, window_seconds=60, clock=lambda: now)
    limiter.check("key")
    limiter.check("key")
    with pytest.raises(AppError) as caught:
        limiter.check("key")
    assert caught.value.code == "RATE_LIMITED"
    assert caught.value.retry_after == 61
    now = 61.0
    limiter.check("key")
