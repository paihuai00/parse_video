"""Decode bounded Douyin JSON responses and React Flight page state."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from typing import Any
from urllib.parse import urlsplit

from app.errors import AppError

FLIGHT_PREFIX = "self.__pace_f.push("
SHARE_STATE = re.compile(r"\bwindow\._ROUTER_DATA\s*=\s*")
MAX_NODES = 100_000
MAX_DEPTH = 40


def decode_share_detail(html: str, target_id: str) -> dict[str, Any] | None:
    marker = SHARE_STATE.search(html)
    if marker is None:
        return None
    try:
        state, _ = json.JSONDecoder().raw_decode(html, marker.end())
    except json.JSONDecodeError:
        return None
    except RecursionError as exc:
        raise AppError(
            "UPSTREAM_BAD_RESPONSE", 502, detail="Douyin share state is too deep"
        ) from exc

    try:
        page = state["loaderData"]["video_(id)/page"]
        items = page["videoInfoRes"]["item_list"]
    except (KeyError, TypeError):
        return None
    if not isinstance(items, list):
        return None
    page_id = page.get("itemId")
    if page_id is not None and str(page_id) != target_id:
        raise AppError("PARSE_FAILED", 502, detail="Douyin share page target mismatch")
    details = [
        item for item in items if isinstance(item, dict) and item.get("aweme_id") is not None
    ]
    for detail in details:
        if str(detail["aweme_id"]) == target_id:
            return detail
    if details:
        raise AppError("PARSE_FAILED", 502, detail="Douyin share detail target mismatch")
    return None


def classify_douyin_page_text(url: str, text: str) -> None:
    lowered = text.lower()
    path = urlsplit(url).path.lower()
    if any(marker in text for marker in ("作品已删除", "作品不存在", "内容已下架")):
        raise AppError("NOTE_NOT_FOUND", 404, detail="Douyin explicitly reported missing work")
    if "/login" in path or any(marker in text for marker in ("登录后查看该作品", "请先登录后查看")):
        raise AppError("UPSTREAM_LOGIN_REQUIRED", 503, detail="Douyin requires login")
    if any(marker in lowered for marker in ("captcha", "verify-page")) or any(
        marker in text for marker in ("安全验证", "完成验证")
    ):
        raise AppError("UPSTREAM_ACCESS_RESTRICTED", 503, detail="Douyin verification challenge")


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
