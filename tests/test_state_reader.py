from __future__ import annotations

import pytest

from app.errors import AppError
from app.parser.state_reader import decode_initial_state, extract_initial_state, select_note


def test_extracts_balanced_state_and_replaces_only_value_undefined() -> None:
    html = (
        "<script>window.__INITIAL_STATE__ = "
        '{"value":undefined,"text":"undefined }"}; next();</script>'
    )
    state = decode_initial_state(html)
    assert state == {"value": None, "text": "undefined }"}


def test_selects_requested_id_not_first_entry(fixture_html) -> None:
    state = decode_initial_state(fixture_html("image_note.html"))
    note = select_note(state, "6ad2355f000000001a027848")
    assert note["title"] == "示例图文"
    with pytest.raises(AppError):
        select_note(state, "000000000000000000000000")


def test_rejects_truncated_state() -> None:
    with pytest.raises(AppError):
        extract_initial_state('window.__INITIAL_STATE__ = {"x":[1,2]')


def test_ignores_marker_text_that_is_not_an_assignment() -> None:
    html = (
        '<script>const label = "window.__INITIAL_STATE__";</script>'
        '<script>window.__INITIAL_STATE__={"ok":true};</script>'
    )
    assert decode_initial_state(html) == {"ok": True}
