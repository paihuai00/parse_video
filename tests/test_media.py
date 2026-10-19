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
    assert all(image.live_video is None for image in note.images)
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


def test_live_photos_keep_order_and_pair_one_selected_mp4(fixture_html) -> None:
    state = decode_initial_state(fixture_html("live_photo_note.html"))
    note = normalize_note(
        "aaaaaaaaaaaaaaaaaaaaaaaa", select_note(state, "aaaaaaaaaaaaaaaaaaaaaaaa")
    )
    assert note.kind == "image"
    assert note.videos == ()
    assert [image.index for image in note.images] == [1, 2, 3, 4]
    assert [image.live_video is not None for image in note.images] == [False, True, False, True]

    first_motion = note.images[1].live_video
    assert first_motion is not None
    assert first_motion.url.endswith("motion-2.mp4?sig=backup-two")
    assert first_motion.codec == "H264"
    assert first_motion.source_width is None
    assert first_motion.source_height is None
    assert first_motion.duration_seconds is None
    assert first_motion.size_bytes is None

    second_motion = note.images[3].live_video
    assert second_motion is not None
    assert second_motion.url.endswith("motion-4.mp4?sig=master-four")
    assert second_motion.duration_seconds == 2.4
    assert second_motion.size_bytes == 34567


def test_declared_live_photo_without_supported_mp4_fails_without_static_result() -> None:
    note = {
        "type": "normal",
        "imageList": [{"urlDefault": "https://sns-webpic-qc.xhscdn.com/x.webp", "livePhoto": True}],
    }
    with pytest.raises(AppError) as caught:
        normalize_note("6ad1f8610000000018018eef", note)
    assert caught.value.code == "MEDIA_NOT_FOUND"


def test_empty_image_stream_does_not_mark_an_ordinary_image_live() -> None:
    note = {
        "type": "normal",
        "imageList": [{"urlDefault": "https://sns-webpic-qc.xhscdn.com/x.webp", "stream": {}}],
    }
    result = normalize_note("6ad1f8610000000018018eef", note)
    assert result.images[0].live_video is None


def test_nonempty_image_stream_is_an_equivalent_live_photo_marker() -> None:
    note = {
        "type": "normal",
        "imageList": [
            {
                "urlDefault": "https://sns-webpic-qc.xhscdn.com/x.webp",
                "stream": {
                    "h264": [
                        {
                            "masterUrl": "https://sns-video-v6.xhscdn.com/x.mp4?sig=kept",
                            "format": "mp4",
                        }
                    ]
                },
            }
        ],
    }
    result = normalize_note("6ad1f8610000000018018eef", note)
    assert result.images[0].live_video is not None
    assert result.images[0].live_video.url.endswith("x.mp4?sig=kept")


def test_live_broadcast_note_remains_unsupported() -> None:
    with pytest.raises(AppError) as caught:
        normalize_note("6ad1f8610000000018018eef", {"type": "live", "imageList": []})
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
    for host in (
        "sns-video-v28.xhscdn.com",
        "sns-bak-v11.xhscdn.com",
        "sns-bak-v10.xhscdn.com",
    ):
        assert normalize_media_url(f"https://{host}/video.mp4?token=keep") == (
            f"https://{host}/video.mp4?token=keep"
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


def test_video_uses_supported_backup_when_master_is_not_mp4() -> None:
    note = {
        "type": "video",
        "video": {
            "media": {
                "stream": {
                    "h264": [
                        {
                            "masterUrl": "https://sns-video-v6.xhscdn.com/a.m3u8?sig=master",
                            "backupUrls": ["https://sns-video-v6.xhscdn.com/a.mp4?sig=backup"],
                            "videoCodec": "H264",
                        }
                    ]
                }
            }
        },
    }
    result = normalize_note("6ad1f8610000000018018eef", note)
    assert result.videos[0].url.endswith("a.mp4?sig=backup")


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
