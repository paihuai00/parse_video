"""Migrated provider contracts use synthetic payloads and offline transports."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from urllib.parse import parse_qs, urlsplit

import pytest

from app.config import Settings
from app.errors import AppError
from app.parser import providers
from app.parser.adapters import detect_platform
from app.parser.client import Deadline
from app.parser.providers import ProviderAdapter
from tests.test_media_proxy import IMAGE, MP4, VIDEO, FakeHTTP, response

DOUYIN = "https://v.douyin.com/synthetic/"


@pytest.fixture(autouse=True)
def public_dns(monkeypatch):
    async def resolve(host, port):
        return ("8.8.8.8",)

    monkeypatch.setattr(providers, "resolve_public_addresses", resolve)


def config(**kwargs):
    return replace(Settings(api_key="test", environment="test"), **kwargs)


def payload(data=None, code=200):
    return response(
        json.dumps({"code": code, "data": data or {"url": VIDEO, "title": "synthetic"}}).encode(),
        b"application/json",
    )


async def test_douyin_order_and_ifphp_credential_stays_server_side():
    http = FakeHTTP([payload(code=500), payload(code=500), payload()])
    adapter = ProviderAdapter(config(ifphp_api_key="server-only"), "douyin", http)
    result = await adapter.parse(DOUYIN, Deadline(2))
    assert result.kind == "video" and result.note_id is None
    assert [urlsplit(call[1]).path for call in http.calls] == [
        "/api/douyin",
        "/api/dyjx",
        "/api/svparse",
    ]
    assert all(parse_qs(urlsplit(call[1]).query)["url"] == [DOUYIN] for call in http.calls)
    assert (b"X-API-Key", b"server-only") in http.calls[-1][2]
    assert not any(key == b"X-API-Key" for key, _ in http.calls[0][2])


@pytest.mark.parametrize(
    "platform,source,paths",
    [
        ("douyin", DOUYIN, ["/api/douyin", "/api/dyjx", "/api/short_videos"]),
        ("bilibili", "https://b23.tv/synthetic", ["/api/bilibili", "/api/short_videos"]),
        ("unknown", "https://public.example/share", ["/api/short_videos"]),
    ],
)
async def test_exhaustion_and_missing_ifphp_do_not_use_native_adapter(platform, source, paths):
    http = FakeHTTP([payload(code=500) for _ in paths])
    with pytest.raises(AppError, match="PROVIDER_EXHAUSTED"):
        await ProviderAdapter(config(), platform, http).parse(source, Deadline(2))
    assert [urlsplit(call[1]).path for call in http.calls] == paths


async def test_transient_retry_is_bounded_within_one_deadline():
    http = FakeHTTP([response(status=503), payload()])
    assert (
        await ProviderAdapter(config(), "douyin", http).parse(DOUYIN, Deadline(2))
    ).kind == "video"
    assert len(http.calls) == 2 and http.calls[0][1] == http.calls[1][1]


async def test_provider_authentication_failure_is_terminal():
    http = FakeHTTP([response(status=401)])
    with pytest.raises(AppError, match="PROVIDER_ACCESS_DENIED"):
        await ProviderAdapter(config(), "douyin", http).parse(DOUYIN, Deadline(2))
    assert len(http.calls) == 1


async def test_deadline_cancels_http_without_starting_another_provider():
    cancelled = []

    class Slow(ProviderAdapter):
        async def fetch(self, provider, raw_url):
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.append(provider)

    with pytest.raises(AppError, match="UPSTREAM_TIMEOUT"):
        await Slow(config(), "douyin").parse(DOUYIN, Deadline(0.01))
    assert cancelled == ["douyin"]


async def test_provider_json_size_is_bounded_before_decode():
    http = FakeHTTP([payload()])
    adapter = ProviderAdapter(config(provider_max_json_bytes=2), "douyin", http)
    with pytest.raises(AppError, match="PROVIDER_UNAVAILABLE"):
        await adapter.fetch("douyin", DOUYIN)
    assert http.closed == 1


@pytest.mark.parametrize("provider", ["douyin", "dyjx", "ifphp", "short_videos"])
async def test_all_douyin_sources_preserve_motion_metadata(provider):
    http = FakeHTTP(
        [
            payload(
                {
                    "type": "live",
                    "images": [IMAGE, IMAGE.replace("image", "other")],
                    "live_photo": [{"image": IMAGE, "video": VIDEO}, None],
                    "desc": "description",
                    "author": {"name": "author", "avatar": "https://untrusted.example/private"},
                }
            )
        ]
    )
    adapter = ProviderAdapter(config(ifphp_api_key="test"), "douyin", http)
    data = await adapter.fetch(provider, DOUYIN)
    result = await adapter.normalize(data, DOUYIN)
    assert result.kind == "image" and len(result.images) == 2
    assert result.images[0].live_video.url == VIDEO and result.images[1].live_video is None
    assert result.desc == "description" and result.author_name == "author"
    assert result.author_avatar is None


async def test_ambiguous_video_url_requires_bounded_positive_mp4_probe():
    url = VIDEO.replace("motion.mp4", "play")
    http = FakeHTTP([response(MP4, b"application/octet-stream")])
    result = await ProviderAdapter(config(), "douyin", http).normalize({"url": url}, DOUYIN)
    assert result.videos[0].url == url and http.closed == 1


@pytest.mark.parametrize(
    "data",
    [
        {"type": "live", "images": [IMAGE]},
        {"type": "image", "images": [IMAGE, ""]},
        {"type": "live", "images": [IMAGE], "livePhotos": [{"image": "other", "video": VIDEO}]},
        {"type": "live", "images": [IMAGE], "live_photo": [{"video": ""}]},
        {"url": VIDEO, "images": [IMAGE]},
    ],
)
async def test_invalid_or_ambiguous_slots_do_not_become_partial_success(data):
    with pytest.raises(AppError):
        await ProviderAdapter(config(), "douyin").normalize(data, DOUYIN)


async def test_returned_unsafe_media_is_terminal_not_a_provider_fallback():
    http = FakeHTTP([payload({"url": "https://127.0.0.1/private.mp4"})])
    with pytest.raises(AppError, match="MEDIA_SOURCE_INVALID"):
        await ProviderAdapter(config(), "douyin", http).parse(DOUYIN, Deadline(2))
    assert len(http.calls) == 1


async def test_private_generic_input_is_not_forwarded(monkeypatch):
    async def unsafe(host, port):
        raise AppError("INVALID_URL", 400)

    monkeypatch.setattr(providers, "resolve_public_addresses", unsafe)
    http = FakeHTTP([])
    with pytest.raises(AppError):
        await ProviderAdapter(config(), "unknown", http).parse(
            "https://public.example/x", Deadline(2)
        )
    assert not http.calls


async def test_bilibili_metadata_cover_and_identity():
    data = {
        "url": "https://upos-sz-mirrorcos.bilivideo.com/a.mp4",
        "cover": "https://i0.hdslb.com/a.jpg",
        "description": "description",
        "auther": "author",
        "bvid": "BVsynthetic",
    }
    result = await ProviderAdapter(config(), "bilibili").normalize(data, "https://b23.tv/example")
    assert result.cover.url == data["cover"] and result.author_name == "author"
    assert result.note_id == "BVsynthetic" and result.desc == "description"


async def test_bilibili_user_name_fallback_is_preserved():
    result = await ProviderAdapter(config(), "bilibili").normalize(
        {"url": "https://upos-sz-mirrorcos.bilivideo.com/a.mp4", "user": {"name": "user-name"}},
        "https://b23.tv/example",
    )
    assert result.author_name == "user-name"


async def test_known_bilibili_avatar_is_published_and_unknown_avatar_is_omitted():
    from app.models import to_unified_public_note
    from app.services.media_tickets import MediaTickets

    for avatar, retained in (
        ("https://i0.hdslb.com/bfs/face/avatar.jpg", True),
        ("https://untrusted.example/private-avatar", False),
    ):
        data = {
            "url": "https://upos-sz-mirrorcos.bilivideo.com/a.mp4",
            "user": {"name": "author", "avatar": avatar},
        }
        result = await ProviderAdapter(config(), "bilibili").normalize(
            data, "https://b23.tv/example"
        )
        assert (result.author_avatar is not None) == retained
        relay_config = config(
            media_publication_enabled=True,
            media_signing_key="s" * 32,
            media_public_origin="https://media.example",
        )
        tickets = MediaTickets(relay_config)
        publication = tickets.publish(result, "bilibili")
        public = to_unified_public_note(publication.note, "bilibili", publication.expires_at)
        if retained:
            assert str(public.author.avatar).startswith("https://media.example/api/v1/media/")
            assert any(record.url == avatar for record in tickets.records.values())
        else:
            assert public.author.avatar is None
        assert avatar not in public.model_dump_json()


async def test_explicit_douyin_identity_mismatch_is_rejected():
    with pytest.raises(AppError, match="PARSE_FAILED"):
        await ProviderAdapter(config(), "douyin").normalize(
            {"url": VIDEO, "aweme_id": "7000000000000000002"},
            "https://www.douyin.com/video/7000000000000000001",
        )


@pytest.mark.parametrize(
    "url,platform",
    [
        (DOUYIN, "douyin"),
        ("https://b23.tv/synthetic", "bilibili"),
        ("https://www.xiaohongshu.com/explore/6ad2355f000000001a027848", "xiaohongshu"),
        ("https://public.example/share", "unknown"),
    ],
)
def test_platform_dispatch(url, platform):
    assert detect_platform(url) == platform
