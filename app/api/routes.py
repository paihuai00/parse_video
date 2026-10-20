"""Public API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.api.auth import require_api_key
from app.models import (
    CacheMetadata,
    HealthResponse,
    ParseRequest,
    ParseSuccess,
    ResponseMeta,
    UnifiedParseSuccess,
    to_public_note,
    to_unified_public_note,
)
from app.parser.adapters import detect_platform

router = APIRouter()


@router.get("/healthz", response_model=HealthResponse, operation_id="getHealth")
async def health() -> HealthResponse:
    return HealthResponse()


@router.post(
    "/api/v1/xiaohongshu/parse",
    response_model=ParseSuccess,
    operation_id="parseXiaohongshuNote",
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
    return ParseSuccess(
        data=to_public_note(result.note),
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
    return UnifiedParseSuccess(
        data=to_unified_public_note(result.note),
        meta=ResponseMeta(
            request_id=request.state.request_id,
            parsed_at=result.parsed_at,
            cache=CacheMetadata(hit=result.cache_hit, expires_at=result.expires_at),
        ),
    )
