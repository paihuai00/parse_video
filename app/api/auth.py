"""API-key authentication."""

from __future__ import annotations

import secrets

from fastapi import Header, Request

from app.errors import AppError


async def require_api_key(request: Request, x_api_key: str | None = Header(default=None)) -> str:
    expected: str = request.app.state.settings.api_key
    supplied = x_api_key or ""
    if (
        not expected
        or not supplied
        or not secrets.compare_digest(expected.encode("utf-8"), supplied.encode("utf-8"))
    ):
        raise AppError("UNAUTHORIZED", 401, detail="missing or invalid API key")
    return supplied
