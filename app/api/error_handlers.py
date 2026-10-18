"""Translate all application and framework failures to one JSON envelope."""

from __future__ import annotations

import json
import logging
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.errors import MESSAGES, AppError
from app.models import ErrorDetails, ParseError, ResponseMeta

logger = logging.getLogger("parser_video")


def request_id(request: Request) -> str:
    return getattr(request.state, "request_id", str(uuid4()))


def error_response(request: Request, error: AppError) -> JSONResponse:
    request.state.outcome_code = error.code
    payload = ParseError(
        error=ErrorDetails(
            code=error.code,
            message=error.public_message,
            retryable=error.retryable,
        ),
        meta=ResponseMeta(request_id=request_id(request), parsed_at=None, cache=None),
    )
    headers = {"X-Request-ID": request_id(request)}
    if error.retry_after is not None:
        headers["Retry-After"] = str(error.retry_after)
    return JSONResponse(
        payload.model_dump(mode="json"), status_code=error.status_code, headers=headers
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return error_response(request, exc)

    @app.exception_handler(RequestValidationError)
    async def handle_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        _ = exc
        return error_response(
            request, AppError("INVALID_REQUEST", 400, detail="request validation failed")
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_framework(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        if exc.status_code == 404:
            error = AppError("ROUTE_NOT_FOUND", 404, detail="route not found")
        elif exc.status_code == 405:
            error = AppError("METHOD_NOT_ALLOWED", 405, detail="method not allowed")
        else:
            error = AppError("INVALID_REQUEST", exc.status_code, detail="framework request error")
        return error_response(request, error)

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            json.dumps(
                {
                    "event": "unexpected_error",
                    "request_id": request_id(request),
                    "exception_type": type(exc).__name__,
                },
                separators=(",", ":"),
            )
        )
        return error_response(
            request, AppError("INTERNAL_ERROR", 500, detail=MESSAGES["INTERNAL_ERROR"])
        )
