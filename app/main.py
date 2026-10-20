"""FastAPI application factory."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Awaitable, Callable
from uuid import uuid4

from fastapi import FastAPI, Request
from starlette.responses import Response

from app.api.error_handlers import error_response, install_error_handlers
from app.api.routes import router
from app.config import Settings
from app.errors import AppError
from app.services.parse_service import ParseService

MAX_REQUEST_BYTES = 8 * 1024
logger = logging.getLogger("parser_video")


def configure_logging() -> None:
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO, format="%(message)s")


def create_app(
    settings: Settings | None = None, parse_service: ParseService | None = None
) -> FastAPI:
    configure_logging()
    resolved_settings = settings or Settings.from_env()
    app = FastAPI(
        title="小红书与抖音媒体解析 API",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.settings = resolved_settings
    app.state.parse_service = parse_service or ParseService(resolved_settings)

    @app.middleware("http")
    async def request_boundary(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request.state.request_id = str(uuid4())
        started = time.monotonic()

        def finalize(response: Response) -> Response:
            response.headers["X-Request-ID"] = request.state.request_id
            event: dict[str, object] = {
                "event": "request_complete",
                "request_id": request.state.request_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round((time.monotonic() - started) * 1000, 2),
                "outcome_code": getattr(request.state, "outcome_code", "OK"),
            }
            note_id = getattr(request.state, "note_id", None)
            if note_id is not None:
                event["note_id"] = note_id
            cache_result = getattr(request.state, "cache_result", None)
            if cache_result is not None:
                event["cache"] = cache_result
            admission = getattr(app.state.parse_service, "admission", None)
            if admission is not None:
                event["upstream_active"] = admission.active
                event["upstream_waiting"] = admission.waiting
            logger.info(json.dumps(event, separators=(",", ":")))
            return response

        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > MAX_REQUEST_BYTES:
                    return finalize(
                        error_response(
                            request,
                            AppError("INPUT_TOO_LARGE", 413, detail="request body exceeds 8 KiB"),
                        )
                    )
            except ValueError:
                return finalize(
                    error_response(
                        request,
                        AppError("INVALID_REQUEST", 400, detail="invalid Content-Length"),
                    )
                )
        if request.method not in {"GET", "HEAD"}:
            chunks: list[bytes] = []
            total = 0
            while True:
                message = await request.receive()
                chunk = message.get("body", b"")
                if not isinstance(chunk, bytes):
                    return finalize(
                        error_response(
                            request,
                            AppError("INVALID_REQUEST", 400, detail="invalid request body"),
                        )
                    )
                total += len(chunk)
                if total > MAX_REQUEST_BYTES:
                    return finalize(
                        error_response(
                            request,
                            AppError("INPUT_TOO_LARGE", 413, detail="request body exceeds 8 KiB"),
                        )
                    )
                chunks.append(chunk)
                if not message.get("more_body", False):
                    break
            body = b"".join(chunks)
            replayed = False

            async def replay_body() -> dict[str, object]:
                nonlocal replayed
                if replayed:
                    return {"type": "http.request", "body": b"", "more_body": False}
                replayed = True
                return {"type": "http.request", "body": body, "more_body": False}

            request._receive = replay_body
        response = await call_next(request)
        return finalize(response)

    install_error_handlers(app)
    app.include_router(router)
    return app
