"""Bounded extraction and data-only normalization of initial state."""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from app.errors import AppError

MARKER = "window.__INITIAL_STATE__"
MAX_STATE_CHARS = 2 * 1024 * 1024
MAX_DEPTH = 80
MAX_NODES = 200_000
JSON_WHITESPACE = " \t\r\n"


@dataclass(frozen=True)
class SelectedNote:
    payload: dict[str, Any]
    mobile: bool


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
        if index - begin >= MAX_STATE_CHARS:
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


def _skip_json_space(source: str, index: int) -> int:
    while index < len(source) and source[index] in JSON_WHITESPACE:
        index += 1
    return index


def _set_array_start(source: str, index: int) -> int | None:
    """Recognize only the literal prefix of new Set(array), never an expression."""
    if not source.startswith("new", index):
        return None
    index += 3
    if index >= len(source) or source[index] not in JSON_WHITESPACE:
        return None
    for token in ("Set", "("):
        index = _skip_json_space(source, index)
        if not source.startswith(token, index):
            return None
        index += len(token)
    index = _skip_json_space(source, index)
    return index if index < len(source) and source[index] == "[" else None


def _normalize_state_values(source: str) -> str:
    """Preserve strings; normalize undefined and exact Set-array value wrappers.

    The extracted source is already bounded and balanced. Arrays track whether
    their close must also consume one constructor parenthesis. The final JSON
    decoder validates every remaining token; no constructor is executed.
    """
    output: list[str] = []
    set_arrays: list[bool] = []
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
            if char == "[":
                set_arrays.append(False)
            expecting_value = char in "[:,"
            output.append(char)
            index += 1
            continue
        if char in "}]":
            if char == "]" and set_arrays.pop():
                index = _skip_json_space(source, index + 1)
                if index >= len(source) or source[index] != ")":
                    raise AppError(
                        "PARSE_FAILED", 502, detail="Set constructor must end after its array"
                    )
            expecting_value = False
            output.append(char)
            index += 1
            continue
        if char.isspace():
            output.append(char)
            index += 1
            continue
        if expecting_value:
            array_start = _set_array_start(source, index)
            if array_start is not None:
                output.append("[")
                set_arrays.append(True)
                index = array_start + 1
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
    raw = _normalize_state_values(extract_initial_state(html))
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
    return select_note_layout(state, note_id).payload


def select_note_layout(state: dict[str, Any], note_id: str) -> SelectedNote:
    if "note" not in state:
        return SelectedNote(_select_mobile_note(state, note_id), mobile=True)
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
    return SelectedNote(note, mobile=False)


def _select_mobile_note(state: dict[str, Any], note_id: str) -> dict[str, Any]:
    root = state.get("noteData")
    if not isinstance(root, dict) or root.get("hasError") is not False:
        raise AppError("PARSE_FAILED", 502, detail="mobile note state is absent or has an error")
    data = root.get("data")
    if not isinstance(data, dict):
        raise AppError("PARSE_FAILED", 502, detail="mobile note data is missing")
    note = data.get("noteData")
    if not isinstance(note, dict):
        raise AppError("PARSE_FAILED", 502, detail="mobile note payload is missing")
    actual_id = note.get("noteId")
    if not isinstance(actual_id, str) or actual_id.lower() != note_id:
        raise AppError("PARSE_FAILED", 502, detail="mobile requested note id is absent from state")
    return note
