from __future__ import annotations

import pytest

from app.errors import AppError
from app.parser.state_reader import (
    decode_initial_state,
    extract_initial_state,
    select_note,
    select_note_layout,
)


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


def test_mobile_selection_matches_target_and_retains_desktop_layout(fixture_html) -> None:
    state = decode_initial_state(fixture_html("mobile_image_note.html"))
    selected = select_note_layout(state, "aaaaaaaaaaaaaaaaaaaaaaaa")
    assert selected.mobile is True
    assert selected.payload["title"] == "Mobile static image fixture"
    assert select_note(state, "aaaaaaaaaaaaaaaaaaaaaaaa") == selected.payload
    desktop = select_note_layout(
        decode_initial_state(fixture_html("image_note.html")), "6ad2355f000000001a027848"
    )
    assert desktop.mobile is False


@pytest.mark.parametrize("root", [None, [], {}, {"hasError": True}, {"hasError": 0}])
def test_mobile_requires_explicit_success_state(root) -> None:
    with pytest.raises(AppError) as caught:
        select_note({"noteData": root}, "aaaaaaaaaaaaaaaaaaaaaaaa")
    assert caught.value.code == "PARSE_FAILED"


@pytest.mark.parametrize(
    "payload",
    [None, [], {}, {"noteId": "bbbbbbbbbbbbbbbbbbbbbbbb"}, {"noteId": 123}],
)
def test_mobile_cannot_select_an_unrelated_or_malformed_payload(payload) -> None:
    state = {"noteData": {"hasError": False, "data": {"noteData": payload}}}
    with pytest.raises(AppError) as caught:
        select_note(state, "aaaaaaaaaaaaaaaaaaaaaaaa")
    assert caught.value.code == "PARSE_FAILED"


def test_unrelated_mobile_recommendation_is_not_selected() -> None:
    state = {
        "noteData": {
            "hasError": False,
            "data": {"noteData": {}, "recommendation": {"noteId": "aaaaaaaaaaaaaaaaaaaaaaaa"}},
        }
    }
    with pytest.raises(AppError):
        select_note(state, "aaaaaaaaaaaaaaaaaaaaaaaa")


def test_malformed_desktop_state_is_not_rescued_by_shadow_mobile_data(fixture_html) -> None:
    state = decode_initial_state(fixture_html("mobile_image_note.html"))
    state["note"] = None
    with pytest.raises(AppError):
        select_note(state, "aaaaaaaaaaaaaaaaaaaaaaaa")
