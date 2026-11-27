"""Credential-authorized content retrieval, with response lifetime owning cleanup."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from collections.abc import AsyncIterator
from contextlib import suppress
from typing import Any

import httpcore
from fastapi import APIRouter, Request
from starlette.requests import ClientDisconnect
from starlette.responses import Response, StreamingResponse
from starlette.types import Receive, Scope, Send

from app.api.error_handlers import error_response
from app.config import Settings
from app.errors import AppError
from app.models import ParseError
from app.parser.client import Deadline
from app.services.admission import AdmissionController
from app.services.media_source import MediaSource, open_media_source
from app.services.media_tickets import MediaRecord
from app.services.rate_limit import RateLimiter
from app.services.safe_http import SafeHTTP

router = APIRouter()
logger = logging.getLogger("parser_video")


class MediaService:
    def __init__(self, settings: Settings, http: SafeHTTP | None = None) -> None:
        self.settings = settings
        self.http = http or SafeHTTP(
            settings.connect_timeout_seconds, settings.media_idle_timeout_seconds
        )
        self.admission = AdmissionController(
            settings.media_concurrency,
            settings.media_queue_capacity,
            settings.media_queue_wait_seconds,
        )
        self.rate_limiter = RateLimiter(settings.media_rate_limit_per_minute)


class MediaResponse(Response):
    """Do not open upstream until ASGI runs; own it through downstream send/cancel."""

    def __init__(self, request: Request, record: MediaRecord) -> None:
        super().__init__()
        self.request, self.record = request, record

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        async def disconnected() -> None:
            while True:
                if (await receive())["type"] == "http.disconnect":
                    return

        # Exactly one receive consumer, including queue/DNS/connect/header preflight.
        transfer = asyncio.create_task(self.transfer(scope, receive, send))
        watcher = asyncio.create_task(disconnected())
        try:
            done, _ = await asyncio.wait((transfer, watcher), return_when=asyncio.FIRST_COMPLETED)
            if transfer in done:
                await transfer
            else:
                await watcher
        finally:
            for task in (watcher, transfer):
                if not task.done():
                    task.cancel()
            for task in (watcher, transfer):
                with suppress(asyncio.CancelledError):
                    await task

    async def transfer(self, scope: Scope, receive: Receive, send: Send) -> None:
        service: MediaService = self.request.app.state.media_service
        settings = service.settings
        started = False
        completed = False
        transferred = 0
        outcome = "OK"
        began = time.monotonic()

        async def track(message: dict[str, object]) -> None:
            nonlocal started, transferred, completed
            if message["type"] == "http.response.start":
                started = True
            body = message.get("body")
            await send(message)
            if isinstance(body, bytes):
                transferred += len(body)
            if message["type"] == "http.response.body" and not message.get("more_body", False):
                completed = True

        try:
            async with asyncio.timeout(settings.media_timeout_seconds):
                async with service.admission.slot(Deadline(settings.media_timeout_seconds)):
                    async with open_media_source(
                        service.http,
                        settings,
                        self.record.url,
                        self.record.platform,
                        self.record.kind,
                        self.request.method,
                    ) as source:
                        if len(source.prefix) > settings.media_max_bytes:
                            raise AppError("MEDIA_UPSTREAM_BAD_RESPONSE", 502)
                        headers = {
                            "Content-Type": source.content_type,
                            "Cache-Control": "no-store",
                            "X-Request-ID": self.request.state.request_id,
                            "Accept-Ranges": "none",
                            "X-Content-Type-Options": "nosniff",
                        }
                        if source.length is not None:
                            headers["Content-Length"] = str(source.length)

                        async def chunks(value: MediaSource) -> AsyncIterator[bytes]:
                            total = len(value.prefix)
                            if value.prefix:
                                yield value.prefix
                            async for chunk in value.chunks:
                                total += len(chunk)
                                if total > settings.media_max_bytes:
                                    raise AppError("MEDIA_UPSTREAM_BAD_RESPONSE", 502)
                                yield chunk
                            if value.length is not None and total != value.length:
                                raise AppError("MEDIA_UPSTREAM_BAD_RESPONSE", 502)

                        if self.request.method == "HEAD":
                            response: Response = Response(headers=headers)
                            # HEAD must not invent an absent upstream length.
                            if source.length is None:
                                del response.headers["content-length"]
                        else:
                            response = StreamingResponse(chunks(source), headers=headers)
                        if isinstance(response, StreamingResponse):
                            # The outer watcher owns disconnects for the entire lifetime.
                            await response.stream_response(track)  # type: ignore[arg-type]
                        else:
                            await response(scope, receive, track)  # type: ignore[arg-type]
                        if not completed:
                            outcome = "MEDIA_CANCELLED"
        except asyncio.CancelledError:
            outcome = "MEDIA_CANCELLED"
            raise
        except ClientDisconnect:
            outcome = "MEDIA_CANCELLED"
        except (
            AppError,
            TimeoutError,
            httpcore.NetworkError,
            httpcore.ProtocolError,
            httpcore.TimeoutException,
        ) as exc:
            if isinstance(exc, AppError):
                error = exc
                if exc.code == "BUSY":
                    error = AppError("MEDIA_BUSY", 503, True, retry_after=2)
                elif exc.code == "INVALID_URL":
                    error = AppError("MEDIA_SOURCE_FORBIDDEN", 403)
                elif exc.code == "UPSTREAM_TIMEOUT":
                    error = AppError("MEDIA_UPSTREAM_TIMEOUT", 504)
                elif exc.code == "UPSTREAM_BAD_RESPONSE":
                    error = AppError("MEDIA_UPSTREAM_BAD_RESPONSE", 502)
                elif not exc.code.startswith("MEDIA_"):
                    error = AppError("INTERNAL_ERROR", 500)
            else:
                error = AppError(
                    "MEDIA_UPSTREAM_TIMEOUT"
                    if isinstance(exc, TimeoutError | httpcore.TimeoutException)
                    else "MEDIA_UPSTREAM_BAD_RESPONSE",
                    504 if isinstance(exc, TimeoutError | httpcore.TimeoutException) else 502,
                )
            outcome = error.code
            if started:
                raise
            await error_response(self.request, error)(scope, receive, send)
        finally:
            logger.info(
                json.dumps(
                    {
                        "event": "media_complete",
                        "request_id": self.request.state.request_id,
                        "bytes": transferred,
                        "duration_ms": round((time.monotonic() - began) * 1000),
                        "outcome_code": outcome,
                    }
                )
            )


MEDIA_ERRORS: dict[int | str, dict[str, Any]] = {
    status: {
        "model": ParseError,
        "headers": {
            "X-Media-Error-Code": {"schema": {"type": "string"}},
            "X-Request-ID": {"schema": {"type": "string"}},
        },
    }
    for status in (400, 403, 410, 429, 502, 503, 504)
}


@router.get(
    "/api/v1/media/{resource_id}",
    operation_id="getMedia",
    response_class=Response,
    responses={
        **MEDIA_ERRORS,
        200: {
            "content": {
                mime: {"schema": {"type": "string", "format": "binary"}}
                for mime in ("image/jpeg", "image/png", "image/webp", "image/gif", "video/mp4")
            }
        },
    },
)
@router.head(
    "/api/v1/media/{resource_id}",
    operation_id="headMedia",
    response_class=Response,
    responses=MEDIA_ERRORS,
)
async def get_media(
    resource_id: str, request: Request, exp: str | None = None, sig: str | None = None
) -> Response:
    identity = request.client.host if request.client else "unknown"
    try:
        request.app.state.media_service.rate_limiter.check(
            hashlib.sha256(identity.encode()).hexdigest()
        )
    except AppError as exc:
        raise AppError("MEDIA_RATE_LIMITED", 429, True, retry_after=exc.retry_after) from exc
    record = request.app.state.media_tickets.resolve(resource_id, exp, sig)
    return MediaResponse(request, record)
