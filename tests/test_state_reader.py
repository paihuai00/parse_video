from __future__ import annotations

import json

import pytest

from app.errors import AppError
from app.parser import state_reader
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


def test_extracts_set_array_with_nested_containers_and_escaped_strings() -> None:
    # Synthetic syntax example; no captured upstream page or comment IDs.
    source = (
        '{"originalCommentIds":new Set(["synthetic",'
        '{"nested":["braces } ] ) and escaped \\" quote",undefined]}]),"after":true}'
    )
    assert extract_initial_state(f"window.__INITIAL_STATE__={source}; next();") == source
    assert decode_initial_state("window.__INITIAL_STATE__=" + source) == {
        "originalCommentIds": [
            "synthetic",
            {"nested": ['braces } ] ) and escaped " quote', None]},
        ],
        "after": True,
    }


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("new Set([])", []),
        ('new Set(["synthetic-one","synthetic-two"])', ["synthetic-one", "synthetic-two"]),
        ("new \t\nSet \r( [1,null,true,undefined] \t)", [1, None, True, None]),
        ('new Set([{"nested":[1,2]},new Set(["synthetic"])])', [{"nested": [1, 2]}, ["synthetic"]]),
        ("[new Set([1]),new Set([2])]", [[1], [2]]),
        ("new Set([1,1])", [1, 1]),
    ],
)
def test_decodes_only_supported_set_array_values(value, expected) -> None:
    # Conversion preserves array data; it does not execute Set/deduplication semantics.
    html = 'window.__INITIAL_STATE__={"before":undefined,"ids":' + value + ',"after":true}'
    assert decode_initial_state(html) == {"before": None, "ids": expected, "after": True}


def test_set_normalization_preserves_string_values_keys_and_escapes() -> None:
    literals = {
        "new Set([undefined])": "new Set([undefined])",
        "escaped": 'quote " backslash \\ brackets ]) } new Set([1])',
        "unicode": "中文 new Set([])",
        "constructor_words": "new Date() new Map([]) undefined",
    }
    source = json.dumps(literals, ensure_ascii=False)
    html = "window.__INITIAL_STATE__=" + source[:-1] + ',"actual":new Set(["safe ]) }"])}'
    assert decode_initial_state(html) == {**literals, "actual": ["safe ]) }"]}


def test_synthetic_rednote_set_fixture_decodes_and_selects_desktop_note(fixture_html) -> None:
    state = decode_initial_state(fixture_html("synthetic_rednote_set_note.html"))
    assert state["comment"]["originalCommentIds"] == [
        "synthetic-comment-one",
        "synthetic-comment-two",
    ]
    selected = select_note_layout(state, "aaaaaaaaaaaaaaaaaaaaaaaa")
    assert selected.mobile is False
    assert selected.payload["desc"] == "Keep new Set([undefined]) as literal text"


@pytest.mark.parametrize(
    "value",
    [
        "new Set()",
        'new Set("synthetic")',
        "new Set({})",
        "new Set(undefined)",
        "new Set([1]",
        "new Set([1]))",
        "new Set([1], [2])",
        "new Set([1] + [2])",
        "new Set([1]).size",
        "new Set([1])()",
        "new Set([1,,2])",
        "new Set([1,])",
        "new Set(([1]))",
        "new Set([1) ])",
        "new Set([1/*comment*/])",
        "new Set([getValue()])",
        "new Set([...items])",
        "new Set([new Date()])",
        "new Map([])",
        "new SetX([])",
        "newSet([])",
        "Set([])",
        "new globalThis.Set([])",
        "new Set([undefinedIdentifier])",
        "new Set(['single-quoted'])",
        "new\u00a0Set([])",
        "new Set\u00a0([])",
        "new Set([1]\u00a0)",
    ],
)
def test_rejects_malformed_sets_and_other_javascript_without_evaluation(value: str) -> None:
    with pytest.raises(AppError) as caught:
        decode_initial_state('window.__INITIAL_STATE__={"ids":' + value + "}")
    assert caught.value.code == "PARSE_FAILED"


def test_set_compatibility_enforces_exact_source_size_limit(monkeypatch) -> None:
    source = '{"ids":new Set(["synthetic"])}'
    monkeypatch.setattr(state_reader, "MAX_STATE_CHARS", len(source))
    assert decode_initial_state("window.__INITIAL_STATE__=" + source) == {"ids": ["synthetic"]}
    monkeypatch.setattr(state_reader, "MAX_STATE_CHARS", len(source) - 1)
    with pytest.raises(AppError) as caught:
        decode_initial_state("window.__INITIAL_STATE__=" + source)
    assert caught.value.detail == "initial state exceeds limit"


def test_set_compatibility_preserves_depth_limit(monkeypatch) -> None:
    monkeypatch.setattr(state_reader, "MAX_DEPTH", 3)
    assert decode_initial_state('window.__INITIAL_STATE__={"ids":new Set([[1]])}') == {"ids": [[1]]}
    with pytest.raises(AppError) as caught:
        decode_initial_state('window.__INITIAL_STATE__={"ids":new Set([new Set([[1]])])}')
    assert caught.value.detail == "initial state nesting exceeds limit"


def test_set_compatibility_preserves_node_limit(monkeypatch) -> None:
    monkeypatch.setattr(state_reader, "MAX_NODES", 3)
    assert decode_initial_state('window.__INITIAL_STATE__={"ids":new Set([1])}') == {"ids": [1]}
    with pytest.raises(AppError) as caught:
        decode_initial_state('window.__INITIAL_STATE__={"ids":new Set([1,2])}')
    assert caught.value.detail == "initial state contains too many nodes"


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
