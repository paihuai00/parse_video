"""Bounded extraction of window.__INITIAL_STATE__ JSON."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

from app.errors import AppError

MARKER = "window.__INITIAL_STATE__"
MAX_STATE_CHARS = 2 * 1024 * 1024
MAX_DEPTH = 80
MAX_NODES = 200_000


def _skip_space(text: str, index: int) -> int:
    while index < len(text) and text[index].isspace():
        index += 1
    return index


def extract_initial_state(html: str) -> str:
    search_from = 0
    while True:
        start = html.find(MARKER, search_from)
        if start < 0:
            raise AppError("PARSE_FAILED", 502, detail="initial state assignment missing")
        index = _skip_space(html, start + len(MARKER))
        if index < len(html) and html[index] == "=":
            break
        search_from = start + len(MARKER)
    index = _skip_space(html, index + 1)
    if index >= len(html) or html[index] not in "{[":
        raise AppError("PARSE_FAILED", 502, detail="initial state is not structured data")
    begin = index
    stack = [html[index]]
    in_string = False
    escaped = False
    index += 1
    while index < len(html):
        if index - begin > MAX_STATE_CHARS:
            raise AppError("PARSE_FAILED", 502, detail="initial state exceeds limit")
        char = html[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char in "{[":
            stack.append(char)
            if len(stack) > MAX_DEPTH:
                raise AppError("PARSE_FAILED", 502, detail="initial state nesting exceeds limit")
        elif char in "}]":
            expected = "{" if char == "}" else "["
            if not stack or stack[-1] != expected:
                raise AppError("PARSE_FAILED", 502, detail="initial state delimiters are invalid")
            stack.pop()
            if not stack:
                return html[begin : index + 1]
        index += 1
    raise AppError("PARSE_FAILED", 502, detail="initial state is truncated")


def replace_value_undefined(source: str) -> str:
    output: list[str] = []
    index = 0
    in_string = False
    escaped = False
    expecting_value = True
    while index < len(source):
        char = source[index]
        if in_string:
            output.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
                expecting_value = False
            index += 1
            continue
        if char == '"':
            in_string = True
            output.append(char)
            index += 1
            continue
        if char in "[:,":
            expecting_value = char in "[:,"
            output.append(char)
            index += 1
            continue
        if char in "}]":
            expecting_value = False
            output.append(char)
            index += 1
            continue
        if char.isspace():
            output.append(char)
            index += 1
            continue
        if expecting_value and source.startswith("undefined", index):
            end = index + len("undefined")
            if end == len(source) or not (source[end].isalnum() or source[end] in "_$"):
                output.append("null")
                index = end
                expecting_value = False
                continue
        output.append(char)
        expecting_value = False
        index += 1
    return "".join(output)


def _walk(value: Any, depth: int = 0) -> Iterator[Any]:
    if depth > MAX_DEPTH:
        raise AppError("PARSE_FAILED", 502, detail="decoded state nesting exceeds limit")
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk(child, depth + 1)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child, depth + 1)


def decode_initial_state(html: str) -> dict[str, Any]:
    raw = replace_value_undefined(extract_initial_state(html))
    try:
        state = json.loads(raw)
    except ValueError as exc:
        raise AppError("PARSE_FAILED", 502, detail="initial state is not valid JSON") from exc
    if not isinstance(state, dict):
        raise AppError("PARSE_FAILED", 502, detail="initial state root is not an object")
    for count, _ in enumerate(_walk(state), start=1):
        if count > MAX_NODES:
            raise AppError("PARSE_FAILED", 502, detail="initial state contains too many nodes")
    return state


def select_note(state: dict[str, Any], note_id: str) -> dict[str, Any]:
    note_root = state.get("note")
    if not isinstance(note_root, dict):
        raise AppError("PARSE_FAILED", 502, detail="note state is missing")
    detail_map = note_root.get("noteDetailMap")
    if not isinstance(detail_map, dict):
        raise AppError("PARSE_FAILED", 502, detail="note detail map is missing")
    entry = detail_map.get(note_id)
    if not isinstance(entry, dict):
        raise AppError("PARSE_FAILED", 502, detail="requested note id is absent from state")
    note = entry.get("note")
    if not isinstance(note, dict):
        raise AppError("PARSE_FAILED", 502, detail="requested note payload is missing")
    return note
