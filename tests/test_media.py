from __future__ import annotations

import pytest

from app.errors import AppError
from app.parser.media import normalize_media_url, normalize_note
from app.parser.state_reader import decode_initial_state, select_note


def test_image_order_and_https_upgrade(fixture_html) -> None:
    state = decode_initial_state(fixture_html("image_note.html"))
    note = normalize_note(
        "6ad2355f000000001a027848", select_note(state, "6ad2355f000000001a027848")
    )
    assert note.kind == "image"
    assert [image.index for image in note.images] == [1, 2]
    assert note.images[0].url.startswith("https://")
    assert note.cover is None


def test_video_prefers_h264_then_resolution_and_keeps_cover_separate(fixture_html) -> None:
    state = decode_initial_state(fixture_html("video_note.html"))
    note = normalize_note(
        "6ad1f8610000000018018eef", select_note(state, "6ad1f8610000000018018eef")
    )
    assert note.kind == "video"
    assert note.images == ()
    assert len(note.videos) == 1
    assert "hd.mp4" in note.videos[0].url
    assert note.videos[0].duration_seconds == 7.175
    assert note.cover is not None


def test_video_without_mp4_fails() -> None:
    note = {"type": "video", "video": {"media": {"stream": {"h264": []}}}, "imageList": []}
    with pytest.raises(AppError) as caught:
        normalize_note("6ad1f8610000000018018eef", note)
    assert caught.value.code == "MEDIA_NOT_FOUND"


def test_live_photo_is_not_silently_downgraded() -> None:
    note = {
        "type": "normal",
        "imageList": [{"urlDefault": "https://a.xhscdn.com/x", "livePhoto": True}],
    }
    with pytest.raises(AppError) as caught:
        normalize_note("6ad1f8610000000018018eef", note)
    assert caught.value.code == "UNSUPPORTED_CONTENT"


def test_media_url_host_is_fail_closed() -> None:
    assert normalize_media_url("https://evil.example/video.mp4") is None
    assert normalize_media_url("https://unverified.xhscdn.com/video.mp4") is None
    assert normalize_media_url("https://sns-video-v6.xhscdn.com:bad/video.mp4") is None
    assert normalize_media_url("https://sns-video-v6.xhscdn.com:80/video.mp4") is None
    assert (
        normalize_media_url("https://sns-video-v6.xhscdn.com/video.mp4?token=keep")
        == "https://sns-video-v6.xhscdn.com/video.mp4?token=keep"
    )


def test_video_requires_positive_mp4_evidence() -> None:
    note = {
        "type": "video",
        "video": {
            "media": {
                "stream": {
                    "h264": [
                        {
                            "masterUrl": "https://sns-video-v6.xhscdn.com/ambiguous",
                            "videoCodec": "H264",
                        }
                    ]
                }
            }
        },
    }
    with pytest.raises(AppError) as caught:
        normalize_note("6ad1f8610000000018018eef", note)
    assert caught.value.code == "MEDIA_NOT_FOUND"


def test_mixed_normal_note_with_video_payload_is_rejected() -> None:
    note = {
        "type": "normal",
        "imageList": [{"urlDefault": "https://sns-webpic-qc.xhscdn.com/a.webp"}],
        "video": {
            "media": {
                "stream": {
                    "h264": [
                        {
                            "masterUrl": "https://sns-video-v6.xhscdn.com/a.mp4",
                            "format": "mp4",
                        }
                    ]
                }
            }
        },
    }
    with pytest.raises(AppError) as caught:
        normalize_note("6ad1f8610000000018018eef", note)
    assert caught.value.code == "UNSUPPORTED_CONTENT"
