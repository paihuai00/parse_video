from __future__ import annotations

import pytest

from app.errors import AppError
from app.parser.douyin.media import normalize_douyin_media_url, normalize_douyin_note


def test_static_images_keep_every_slot_and_original_order() -> None:
    target = "7000000000000000002"
    detail = {
        "awemeId": target,
        "desc": "静态图文",
        "images": [
            {
                "width": 1260,
                "height": 2388,
                "urlList": [
                    "https://evil.example/first.webp",
                    "https://p3-pc-sign.douyinpic.com/first.webp?sig=keep",
                ],
                "video": None,
            },
            {
                "width": 1260,
                "height": 2388,
                "urlList": ["https://p9-pc-sign.douyinpic.com/first.webp?sig=keep"],
                "video": None,
            },
        ],
        "video": {"uri": "background.mp3", "duration": 0, "bitRateList": []},
    }
    note = normalize_douyin_note(target, detail)
    assert note.kind == "image"
    assert [image.index for image in note.images] == [1, 2]
    assert [image.url for image in note.images] == [
        "https://p3-pc-sign.douyinpic.com/first.webp?sig=keep",
        "https://p9-pc-sign.douyinpic.com/first.webp?sig=keep",
    ]
    assert note.videos == () and note.cover is None


def test_dynamic_image_is_rejected_instead_of_silently_losing_motion() -> None:
    target = "7000000000000000003"
    detail = {
        "awemeId": target,
        "images": [
            {
                "urlList": ["https://p3-pc-sign.douyinpic.com/still.webp"],
                "video": {
                    "format": "mp4",
                    "playAddr": [{"src": "https://v11-weba.douyinvod.com/motion"}],
                },
            }
        ],
    }
    with pytest.raises(AppError) as caught:
        normalize_douyin_note(target, detail)
    assert caught.value.code == "UNSUPPORTED_CONTENT"


def test_video_prefers_h264_then_resolution_and_keeps_cover_separate() -> None:
    target = "7000000000000000001"
    detail = {
        "aweme_id": target,
        "desc": "普通视频",
        "images": None,
        "video": {
            "duration": 24600,
            "cover": {
                "width": 720,
                "height": 1280,
                "url_list": ["https://p3-pc-sign.douyinpic.com/cover.jpeg?sig=keep"],
            },
            "bit_rate": [
                {
                    "format": "mp4",
                    "isH265": 1,
                    "width": 2160,
                    "height": 3840,
                    "play_addr": {
                        "url_list": ["https://v26-web.douyinvod.com/h265?mime_type=video_mp4"]
                    },
                },
                {
                    "format": "mp4",
                    "isH265": 0,
                    "width": 1080,
                    "height": 1920,
                    "data_size": 12345,
                    "play_addr": {"url_list": ["https://v11-weba.douyinvod.com/h264?sig=keep"]},
                },
            ],
        },
    }
    note = normalize_douyin_note(target, detail)
    assert note.kind == "video" and note.images == () and len(note.videos) == 1
    assert note.videos[0].url.endswith("h264?sig=keep")
    assert note.videos[0].duration_seconds == 24.6
    assert note.cover is not None and "cover.jpeg" in note.cover.url


def test_video_prefers_the_independently_readable_cdn_for_one_variant() -> None:
    target = "7000000000000000001"
    note = normalize_douyin_note(
        target,
        {
            "awemeId": target,
            "video": {
                "duration": 1000,
                "bitRateList": [
                    {
                        "format": "mp4",
                        "isH265": 0,
                        "playAddr": [
                            {"src": ("https://v26-web.douyinvod.com/first?mime_type=video_mp4")},
                            {
                                "src": (
                                    "https://v11-weba.douyinvod.com/readable?mime_type=video_mp4"
                                )
                            },
                        ],
                    }
                ],
            },
        },
    )
    assert note.videos[0].url.startswith("https://v11-weba.douyinvod.com/readable")


def test_unknown_codec_does_not_get_mislabeled_h264() -> None:
    target = "7000000000000000001"
    note = normalize_douyin_note(
        target,
        {
            "awemeId": target,
            "video": {
                "duration": 1000,
                "bitRateList": [
                    {
                        "format": "mp4",
                        "width": 720,
                        "height": 1280,
                        "playAddr": [
                            {"src": "https://v11-weba.douyinvod.com/unknown?mime_type=video_mp4"}
                        ],
                    }
                ],
            },
        },
    )
    assert note.videos[0].codec is None


def test_video_needs_positive_mp4_evidence_and_a_known_exact_host() -> None:
    assert normalize_douyin_media_url("https://douyinvod.com/video.mp4") is None
    assert normalize_douyin_media_url("https://v11-weba.douyinvod.com.evil/video.mp4") is None
    target = "7000000000000000001"
    with pytest.raises(AppError) as caught:
        normalize_douyin_note(
            target,
            {
                "awemeId": target,
                "video": {"playAddr": [{"src": "https://v11-weba.douyinvod.com/ambiguous"}]},
            },
        )
    assert caught.value.code == "MEDIA_NOT_FOUND"
