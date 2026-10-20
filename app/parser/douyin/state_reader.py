"""Decode bounded Douyin JSON responses and React Flight page state."""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from app.errors import AppError

FLIGHT_PREFIX = "self.__pace_f.push("
MAX_NODES = 100_000
MAX_DEPTH = 40


def decode_detail_response(raw: bytes, target_id: str, max_bytes: int) -> dict[str, Any] | None:
    if len(raw) > max_bytes:
        raise AppError("UPSTREAM_BAD_RESPONSE", 502, detail="Douyin detail response exceeds limit")
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AppError("UPSTREAM_BAD_RESPONSE", 502, detail="invalid Douyin detail JSON") from exc
    if not isinstance(value, dict):
        raise AppError("UPSTREAM_BAD_RESPONSE", 502, detail="invalid Douyin detail payload")
    detail = value.get("aweme_detail")
    if detail is None:
        return None
    if not isinstance(detail, dict) or str(detail.get("aweme_id")) != target_id:
        raise AppError("PARSE_FAILED", 502, detail="Douyin detail target mismatch")
    return detail


def decode_flight_detail(
    scripts: Iterable[str], target_id: str, max_bytes: int
) -> dict[str, Any] | None:
    total = 0
    for script in scripts:
        total += len(script.encode("utf-8"))
        if total > max_bytes:
            raise AppError("UPSTREAM_BAD_RESPONSE", 502, detail="Douyin page state exceeds limit")
        if not script.startswith(FLIGHT_PREFIX) or not script.endswith(")"):
            continue
        try:
            outer = json.loads(script[len(FLIGHT_PREFIX) : -1])
        except json.JSONDecodeError:
            continue
        if not isinstance(outer, list) or len(outer) < 2 or not isinstance(outer[1], str):
            continue
        _, separator, raw = outer[1].partition(":")
        if not separator or not raw.startswith(("[", "{")):
            continue
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError:
            continue
        found = _find_target(decoded, target_id)
        if found is not None:
            return found
    return None


def _find_target(root: object, target_id: str) -> dict[str, Any] | None:
    stack: list[tuple[object, int]] = [(root, 0)]
    visited = 0
    while stack:
        value, depth = stack.pop()
        visited += 1
        if visited > MAX_NODES:
            raise AppError("PARSE_FAILED", 502, detail="Douyin state traversal limit exceeded")
        if isinstance(value, dict):
            candidate_id = value.get("awemeId", value.get("aweme_id"))
            if str(candidate_id) == target_id and (
                isinstance(value.get("images"), list) or isinstance(value.get("video"), dict)
            ):
                return value
            if depth < MAX_DEPTH:
                stack.extend((child, depth + 1) for child in value.values())
        elif isinstance(value, list) and depth < MAX_DEPTH:
            stack.extend((child, depth + 1) for child in value)
    return None
