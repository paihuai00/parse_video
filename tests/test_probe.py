from __future__ import annotations

import pytest

from scripts.probe import check_media, redacted_summary, representative_media


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
    assert output["live_photo_count"] == 0
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


def test_probe_counts_live_photos_and_checks_one_still_plus_one_motion() -> None:
    data = {
        "type": "image",
        "images": [
            {
                "url": "https://sns-webpic-qc.xhscdn.com/a.webp?sig=still",
                "live_video": {"url": "https://sns-video-v6.xhscdn.com/a.mp4?sig=motion"},
            },
            {"url": "https://sns-webpic-qc.xhscdn.com/b.webp?sig=still"},
        ],
        "videos": [],
        "cover": None,
    }
    selected = representative_media(data)
    assert [kind for kind, _ in selected] == ["image", "live_video"]
    assert len(selected) == 2

    output = redacted_summary(
        {"success": True, "data": data, "meta": {"request_id": "request-id"}},
        False,
        False,
    )
    assert output["live_photo_count"] == 1
    assert "sig=still" not in str(output)
    assert "sig=motion" not in str(output)
