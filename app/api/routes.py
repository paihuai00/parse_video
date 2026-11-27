"""Public API routes."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, Request

from app.api.auth import require_api_key
from app.models import (
    CacheMetadata,
    HealthResponse,
    ParseError,
    ParseRequest,
    ParseSuccess,
    ResponseMeta,
    UnifiedParseSuccess,
    to_public_note,
    to_unified_public_note,
)
from app.parser.adapters import detect_platform

router = APIRouter()
PARSE_ERRORS: dict[int | str, dict[str, Any]] = {
    status: {"model": ParseError}
    for status in (400, 401, 404, 405, 413, 422, 429, 500, 502, 503, 504)
}


@router.get("/healthz", response_model=HealthResponse, operation_id="getHealth")
async def health() -> HealthResponse:
    return HealthResponse()


@router.post(
    "/api/v1/xiaohongshu/parse",
    response_model=ParseSuccess,
    operation_id="parseXiaohongshuNote",
    responses=PARSE_ERRORS,
)
async def parse_note(
    body: ParseRequest,
    request: Request,
    api_key: str = Depends(require_api_key),
) -> ParseSuccess:
    result = await request.app.state.parse_service.parse(str(body.url), body.refresh, api_key)
    request.state.outcome_code = "OK"
    request.state.note_id = result.note.note_id
    request.state.cache_result = "hit" if result.cache_hit else "miss"
    publication = request.app.state.media_tickets.publish(result.note, "xiaohongshu")
    try:
        data = to_public_note(publication.note, publication.expires_at)
    except BaseException:
        request.app.state.media_tickets.revoke(publication.resource_ids)
        raise
    return ParseSuccess(
        data=data,
        meta=ResponseMeta(
            request_id=request.state.request_id,
            parsed_at=result.parsed_at,
            cache=CacheMetadata(hit=result.cache_hit, expires_at=result.expires_at),
        ),
    )


@router.post(
    "/api/v1/parse",
    response_model=UnifiedParseSuccess,
    operation_id="parseMediaWork",
    responses=PARSE_ERRORS,
)
async def parse_media(
    body: ParseRequest,
    request: Request,
    api_key: str = Depends(require_api_key),
) -> UnifiedParseSuccess:
    raw_url = str(body.url)
    platform = detect_platform(raw_url)
    result = await request.app.state.parse_service.parse(
        raw_url, body.refresh, api_key, platform=platform
    )
    request.state.outcome_code = "OK"
    request.state.note_id = result.note.note_id
    request.state.cache_result = "hit" if result.cache_hit else "miss"
    publication = request.app.state.media_tickets.publish(result.note, platform)
    public_platform: Literal["xhs", "douyin", "bilibili", "unknown"] = (
        "xhs" if platform == "xiaohongshu" else platform
    )
    try:
        data = to_unified_public_note(publication.note, public_platform, publication.expires_at)
    except BaseException:
        request.app.state.media_tickets.revoke(publication.resource_ids)
        raise
    return UnifiedParseSuccess(
        data=data,
        meta=ResponseMeta(
            request_id=request.state.request_id,
            parsed_at=result.parsed_at,
            cache=CacheMetadata(hit=result.cache_hit, expires_at=result.expires_at),
        ),
    )
