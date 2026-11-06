from __future__ import annotations

import pytest

from app.errors import AppError
from app.parser.media import normalize_media_url, normalize_mobile_note, normalize_note
from app.parser.state_reader import decode_initial_state, select_note, select_note_layout

REGIONAL_VIDEO_HOSTS = (
    "sns-v28.rednotecdn.com",
    "sns-v11.rednotecdn.com",
    "sns-v27.rednotecdn.com",
)


@pytest.mark.parametrize("host", REGIONAL_VIDEO_HOSTS)
def test_regional_video_host_is_video_only(host: str) -> None:
    raw = f"http://{host}/synthetic-motion.mp4?sig=synthetic#discard"
    assert normalize_media_url(raw, kind="video") == (
        f"https://{host}/synthetic-motion.mp4?sig=synthetic"
    )
    assert normalize_media_url(raw, kind="image") is None
    assert normalize_media_url(raw) is None


@pytest.mark.parametrize("host", REGIONAL_VIDEO_HOSTS)
def test_regional_host_supports_normal_video(host: str) -> None:
    result = normalize_note(
        "a" * 24,
        {
            "type": "video",
            "video": {"media": {"stream": {"h264": [{"masterUrl": f"http://{host}/motion.mp4"}]}}},
        },
    )
    assert result.images == ()
    assert result.videos[0].url == f"https://{host}/motion.mp4"


@pytest.mark.parametrize("host", REGIONAL_VIDEO_HOSTS)
@pytest.mark.parametrize("path", ["motion.m3u8", "ambiguous"])
def test_regional_video_hosts_require_positive_mp4(host: str, path: str) -> None:
    note = {
        "type": "video",
        "video": {"media": {"stream": {"h264": [{"masterUrl": f"https://{host}/{path}"}]}}},
    }
    with pytest.raises(AppError) as caught:
        normalize_note("a" * 24, note)
    assert caught.value.code == "MEDIA_NOT_FOUND"


@pytest.mark.parametrize("host", REGIONAL_VIDEO_HOSTS)
@pytest.mark.parametrize(
    "authority",
    ["{host}.evil.example", "evil{host}", "user:pass@{host}", "{host}:444"],
)
def test_regional_video_hosts_reject_unsafe_authorities(host: str, authority: str) -> None:
    assert (
        normalize_media_url(f"https://{authority.format(host=host)}/motion.mp4", kind="video")
        is None
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://sns-v999.rednotecdn.com/motion.mp4",
        "https://sns-v29.rednotecdn.com/motion.mp4",
        "https://sns-v\uff12\uff18.rednotecdn.com/motion.mp4",
        "https://sns-v28.rednotecdn.com:80/motion.mp4",
        "http://sns-v28.rednotecdn.com:443/motion.mp4",
        "ftp://sns-v28.rednotecdn.com/motion.mp4",
    ],
)
def test_regional_video_hosts_keep_shard_and_scheme_bounds(url: str) -> None:
    assert normalize_media_url(url, kind="video") is None


def test_synthetic_regional_four_slot_live_photo_fixture(fixture_html) -> None:
    state = decode_initial_state(fixture_html("synthetic_rednote_live_photo_note.html"))
    assert state["ids"] == ["synthetic"]
    assert state["cursor"] is None
    selected = select_note_layout(state, "a" * 24)
    assert selected.mobile is False
    result = normalize_note("a" * 24, selected.payload)
    assert result.videos == ()
    assert [i.index for i in result.images] == [1, 2, 3, 4]
    for index, image in enumerate(result.images, 1):
        assert image.url == (
            f"https://sns-web-i10.rednotecdn.com/synthetic-still-{index}.jpg?sig=synthetic"
        )
        assert image.live_video is not None
        assert image.live_video.url == (
            f"https://sns-v28.rednotecdn.com/synthetic-motion-{index}.mp4?sig=synthetic"
        )
        assert image.live_video.codec == "H264"


@pytest.mark.parametrize("candidate_source", ["urlDefault", "WB_DFT"])
def test_synthetic_rednote_web_image_is_selected_and_normalized(
    fixture_html, candidate_source
) -> None:
    state = decode_initial_state(fixture_html("synthetic_rednote_web_image_note.html"))
    assert state["comment"]["originalCommentIds"] == ["synthetic-comment"]
    assert state["comment"]["cursor"] is None
    selected = select_note_layout(state, "aaaaaaaaaaaaaaaaaaaaaaaa")
    assert selected.mobile is False
    note = selected.payload
    assert note["desc"] is None
    if candidate_source == "WB_DFT":
        note["imageList"][0]["urlDefault"] = None
    result = normalize_note("aaaaaaaaaaaaaaaaaaaaaaaa", note)
    assert result.title == "Synthetic rednote web image fixture"
    assert result.videos == ()
    assert len(result.images) == 1
    expected_path = (
        "synthetic-default.jpg" if candidate_source == "urlDefault" else "synthetic-detail.jpg"
    )
    assert result.images[0].url == (
        f"https://sns-web-i10.rednotecdn.com/{expected_path}?sig=synthetic"
    )
    assert result.images[0].live_video is None


def test_new_regional_host_is_image_only_and_keeps_existing_url_normalization() -> None:
    url = "http://sns-web-i10.rednotecdn.com/synthetic.jpg?sig=synthetic#discard"
    assert normalize_media_url(url) == (
        "https://sns-web-i10.rednotecdn.com/synthetic.jpg?sig=synthetic"
    )
    assert normalize_media_url(url, kind="video") is None


@pytest.mark.parametrize(
    "url",
    [
        "https://sns-web-i10.rednotecdn.com.evil.example/image.jpg",
        "https://evil-sns-web-i10.rednotecdn.com/image.jpg",
        "https://sns-web-i10.evilrednotecdn.com/image.jpg",
        "https://sns-web-i11.rednotecdn.com/image.jpg",
        "https://sns-web-i999.rednotecdn.com/image.jpg",
        "https://sns-web-i\uff11\uff10.rednotecdn.com/image.jpg",
        "https://user:pass@sns-web-i10.rednotecdn.com/image.jpg",
        "https://sns-web-i10.rednotecdn.com:444/image.jpg",
        "https://sns-web-i10.rednotecdn.com:80/image.jpg",
        "http://sns-web-i10.rednotecdn.com:443/image.jpg",
        "https://sns-web-i10.rednotecdn.com:bad/image.jpg",
        "ftp://sns-web-i10.rednotecdn.com/image.jpg",
        "file://sns-web-i10.rednotecdn.com/image.jpg",
        "//sns-web-i10.rednotecdn.com/image.jpg",
    ],
)
def test_rednote_web_image_host_rejects_unsafe_or_unobserved_urls(url: str) -> None:
    assert normalize_media_url(url) is None


@pytest.mark.parametrize("note_type", ["normal", "video"])
@pytest.mark.parametrize("candidate_field", ["masterUrl", "backupUrls"])
def test_new_image_host_never_becomes_a_video_or_live_photo_mp4(note_type, candidate_field) -> None:
    candidate = {
        "format": "mp4",
        candidate_field: (
            "https://sns-web-i10.rednotecdn.com/synthetic.mp4"
            if candidate_field == "masterUrl"
            else ["https://sns-web-i10.rednotecdn.com/synthetic.mp4"]
        ),
    }
    stream = {"h264": [candidate]}
    note = (
        {"type": "video", "video": {"media": {"stream": stream}}}
        if note_type == "video"
        else {
            "type": "normal",
            "imageList": [
                {
                    "urlDefault": "https://sns-webpic-qc.xhscdn.com/synthetic-still.jpg",
                    "livePhoto": True,
                    "stream": stream,
                }
            ],
        }
    )
    with pytest.raises(AppError) as caught:
        normalize_note("aaaaaaaaaaaaaaaaaaaaaaaa", note)
    assert caught.value.code == "MEDIA_NOT_FOUND"


def test_new_image_host_as_video_master_does_not_hide_supported_backup() -> None:
    result = normalize_note(
        "aaaaaaaaaaaaaaaaaaaaaaaa",
        {
            "type": "video",
            "video": {
                "media": {
                    "stream": {
                        "h264": [
                            {
                                "masterUrl": "https://sns-web-i10.rednotecdn.com/synthetic.mp4",
                                "backupUrls": ["http://sns-bak-v1.xhscdn.com/synthetic.mp4"],
                            }
                        ]
                    }
                }
            },
        },
    )
    assert result.videos[0].url == "https://sns-bak-v1.xhscdn.com/synthetic.mp4"


def test_new_image_host_retains_mobile_preview_protection() -> None:
    preview = "http://sns-web-i10.rednotecdn.com/synthetic-preview.jpg"
    with pytest.raises(AppError) as caught:
        normalize_mobile_note(
            "aaaaaaaaaaaaaaaaaaaaaaaa",
            {
                "type": "normal",
                "imageList": [
                    {"url": preview, "infoList": [{"imageScene": "H5_PRV", "url": preview}]}
                ],
            },
        )
    assert caught.value.code == "MEDIA_NOT_FOUND"


@pytest.mark.parametrize(
    "host", ["sns-video-v4.xhscdn.com", "sns-bak-v1.xhscdn.com", "sns-bak-v6.xhscdn.com"]
)
def test_observed_live_photo_hosts_preserve_motion_and_signed_query(host: str) -> None:
    result = normalize_note(
        "aaaaaaaaaaaaaaaaaaaaaaaa",
        {
            "type": "normal",
            "imageList": [
                {
                    "urlDefault": "https://sns-webpic-qc.xhscdn.com/still.jpg",
                    "width": 1400,
                    "height": 1200,
                    "livePhoto": True,
                    "stream": {"h264": [{"masterUrl": f"http://{host}/motion.mp4?sig=synthetic"}]},
                }
            ],
        },
    )
    assert result.videos == ()
    motion = result.images[0].live_video
    assert motion is not None
    assert motion.url == f"https://{host}/motion.mp4?sig=synthetic"
    assert motion.codec == "H264"
    assert motion.source_width is None
    assert motion.source_height is None


@pytest.mark.parametrize(
    "host", ["sns-video-v4.xhscdn.com", "sns-bak-v1.xhscdn.com", "sns-bak-v6.xhscdn.com"]
)
@pytest.mark.parametrize("path", ["motion.m3u8", "ambiguous"])
def test_observed_live_photo_hosts_still_require_mp4_evidence(host: str, path: str) -> None:
    with pytest.raises(AppError) as caught:
        normalize_note(
            "aaaaaaaaaaaaaaaaaaaaaaaa",
            {
                "type": "normal",
                "imageList": [
                    {
                        "urlDefault": "https://sns-webpic-qc.xhscdn.com/still.jpg",
                        "livePhoto": True,
                        "stream": {"h264": [{"masterUrl": f"https://{host}/{path}"}]},
                    }
                ],
            },
        )
    assert caught.value.code == "MEDIA_NOT_FOUND"


@pytest.mark.parametrize(
    "host", ["sns-video-v4.xhscdn.com", "sns-bak-v1.xhscdn.com", "sns-bak-v6.xhscdn.com"]
)
@pytest.mark.parametrize(
    "authority", ["{host}.evil.example", "evil{host}", "user:pass@{host}", "{host}:444"]
)
def test_observed_live_photo_hosts_reject_unsafe_authorities(host: str, authority: str) -> None:
    assert normalize_media_url(f"https://{authority.format(host=host)}/motion.mp4") is None


@pytest.mark.parametrize("host", ["sns-video-v999.xhscdn.com", "sns-bak-v999.xhscdn.com"])
def test_unobserved_video_shards_remain_rejected(host: str) -> None:
    assert normalize_media_url(f"https://{host}/motion.mp4") is None


@pytest.mark.parametrize("host", ["sns-i11.rednotecdn.com", "sns-i27.rednotecdn.com"])
def test_regional_image_shards_preserve_full_media_url(host: str) -> None:
    url = f"http://{host}/image.jpg?sig=synthetic"
    assert normalize_media_url(url) == f"https://{host}/image.jpg?sig=synthetic"


@pytest.mark.parametrize(
    "authority",
    [
        "sns-i11.rednotecdn.com.evil.example",
        "evil.rednotecdn.com",
        "sns-i11.evilrednotecdn.com",
        "user:pass@sns-i11.rednotecdn.com",
        "sns-i11.rednotecdn.com:444",
    ],
)
def test_regional_image_shards_reject_unsafe_authorities(authority: str) -> None:
    assert normalize_media_url(f"https://{authority}/image.jpg") is None


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


def mobile_note(fixture_html):
    return select_note(
        decode_initial_state(fixture_html("mobile_image_note.html")), "aaaaaaaaaaaaaaaaaaaaaaaa"
    )


def test_mobile_preserves_all_images_and_prefers_detail_over_preview(fixture_html) -> None:
    result = normalize_mobile_note("aaaaaaaaaaaaaaaaaaaaaaaa", mobile_note(fixture_html))
    assert result.kind == "image"
    assert result.videos == ()
    assert result.cover is None
    assert [x.index for x in result.images] == [1, 2]
    assert result.images[0].url == ("https://sns-webpic-qc.xhscdn.com/detail-one.jpg?sig=synthetic")
    assert result.images[1].url.endswith("/detail-two.jpg")
    assert [(x.source_width, x.source_height) for x in result.images] == [(1400, 1200), (900, 1000)]
    assert all(x.live_video is None for x in result.images)


@pytest.mark.parametrize(
    "bad_slot",
    [
        None,
        {},
        {"url": "https://evil.example/image.jpg"},
        {
            "url": "https://sns-webpic-qc.xhscdn.com/preview.jpg",
            "infoList": [
                {"imageScene": "H5_PRV", "url": "http://sns-webpic-qc.xhscdn.com/preview.jpg"}
            ],
        },
        {"url": "https://sns-webpic-qc.xhscdn.com/a.jpg", "infoList": "invalid"},
        {"url": "https://sns-webpic-qc.xhscdn.com/a.jpg", "infoList": [None]},
        {"url": "https://sns-webpic-qc.xhscdn.com/a.jpg", "livePhoto": "false"},
        {"url": "https://sns-webpic-qc.xhscdn.com/a.jpg", "stream": []},
    ],
)
def test_mobile_never_skips_an_invalid_image_slot(fixture_html, bad_slot) -> None:
    payload = mobile_note(fixture_html)
    payload["imageList"].append(bad_slot)
    with pytest.raises(AppError) as caught:
        normalize_mobile_note("aaaaaaaaaaaaaaaaaaaaaaaa", payload)
    assert caught.value.code == "MEDIA_NOT_FOUND"


@pytest.mark.parametrize(
    "motion",
    [
        {"livePhoto": True},
        {"stream": {"unknown": []}},
        {"videoUrl": "https://sns-video-v6.xhscdn.com/a.mp4"},
        {"livePhotoUrl": "https://sns-video-v6.xhscdn.com/a.mp4"},
    ],
)
def test_mobile_motion_cannot_be_returned_as_static_image(fixture_html, motion) -> None:
    payload = mobile_note(fixture_html)
    payload["imageList"][1].update(motion)
    with pytest.raises(AppError) as caught:
        normalize_mobile_note("aaaaaaaaaaaaaaaaaaaaaaaa", payload)
    assert caught.value.code == "UNSUPPORTED_CONTENT"


@pytest.mark.parametrize("explicit_marker", [False, True])
def test_mobile_complete_live_photo_preserves_detail_image_motion_and_metadata(
    fixture_html, explicit_marker
) -> None:
    note = select_note(
        decode_initial_state(fixture_html("synthetic_mobile_live_photo_note.html")),
        "aaaaaaaaaaaaaaaaaaaaaaaa",
    )
    note["imageList"][0]["livePhoto"] = explicit_marker
    result = normalize_mobile_note("aaaaaaaaaaaaaaaaaaaaaaaa", note)
    assert result.videos == ()
    assert len(result.images) == 1
    image = result.images[0]
    assert image.url == "https://sns-webpic-qc.xhscdn.com/synthetic-detail.jpg"
    assert image.index == 1
    assert image.source_width == 1400
    assert image.live_video is not None
    assert image.live_video.url == (
        "https://sns-video-v4.xhscdn.com/synthetic-motion.mp4?sig=synthetic"
    )
    assert image.live_video.source_width is None
    assert image.live_video.source_height is None
    assert image.live_video.duration_seconds == 2.4
    assert image.live_video.size_bytes == 34567


@pytest.mark.parametrize(
    "motion_url",
    [
        "https://evil.example/motion.mp4",
        "https://sns-video-v4.xhscdn.com/ambiguous",
        "https://sns-video-v4.xhscdn.com/motion.m3u8",
    ],
)
def test_mobile_unusable_motion_never_returns_partial_images(fixture_html, motion_url) -> None:
    note = mobile_note(fixture_html)
    note["imageList"][1].update(livePhoto=True, stream={"h264": [{"masterUrl": motion_url}]})
    with pytest.raises(AppError) as caught:
        normalize_mobile_note("aaaaaaaaaaaaaaaaaaaaaaaa", note)
    assert caught.value.code == "UNSUPPORTED_CONTENT"


def test_mobile_live_photo_still_requires_complete_detail_image(fixture_html) -> None:
    note = select_note(
        decode_initial_state(fixture_html("synthetic_mobile_live_photo_note.html")),
        "aaaaaaaaaaaaaaaaaaaaaaaa",
    )
    note["imageList"][0]["infoList"] = note["imageList"][0]["infoList"][:1]
    with pytest.raises(AppError) as caught:
        normalize_mobile_note("aaaaaaaaaaaaaaaaaaaaaaaa", note)
    assert caught.value.code == "MEDIA_NOT_FOUND"


@pytest.mark.parametrize("images", [None, [], "invalid"])
def test_mobile_requires_nonempty_image_list(images) -> None:
    with pytest.raises(AppError) as caught:
        normalize_mobile_note("aaaaaaaaaaaaaaaaaaaaaaaa", {"type": "normal", "imageList": images})
    assert caught.value.code == "MEDIA_NOT_FOUND"


def test_mobile_video_remains_unsupported(fixture_html) -> None:
    payload = mobile_note(fixture_html)
    payload["type"] = "video"
    with pytest.raises(AppError) as caught:
        normalize_mobile_note("aaaaaaaaaaaaaaaaaaaaaaaa", payload)
    assert caught.value.code == "UNSUPPORTED_CONTENT"
