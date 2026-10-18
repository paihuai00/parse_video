from __future__ import annotations

import pytest

from scripts.probe import check_media, redacted_summary


def test_probe_summary_redacts_media_urls() -> None:
    payload = {
        "success": True,
        "data": {
            "note_id": "a" * 24,
            "type": "image",
            "images": [{"url": "https://x.xhscdn.com/a?secret=signed"}],
            "videos": [],
            "cover": None,
        },
        "meta": {"request_id": "request-id"},
    }
    output = redacted_summary(payload, False, False)
    assert output["image_count"] == 1
    assert "xhscdn" not in str(output)
    assert "signed" not in str(output)


def test_probe_rejects_unapproved_media_before_network(monkeypatch) -> None:
    called = False

    def fail_if_called(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("network must not be reached")

    monkeypatch.setattr("urllib.request.urlopen", fail_if_called)
    with pytest.raises(ValueError):
        check_media("http://127.0.0.1/private", False)
    assert not called
