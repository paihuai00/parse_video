from __future__ import annotations

import asyncio
import json
import socket
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

import pytest
from curl_cffi import CurlECode, CurlError, CurlOpt
from curl_cffi.curl import CURL_WRITEFUNC_ERROR
from curl_cffi.requests import Headers, Response

from app.config import Settings
from app.errors import AppError
from app.parser.adapters import DouyinAdapter
from app.parser.client import Deadline
from app.parser.douyin import share_client
from app.parser.douyin.share_client import SHARE_ORIGIN

ITEM_ID = "7000000000000000001"
OTHER_ID = "7000000000000000002"
SHORT = "https://v.douyin.com/exampleToken/"
VIDEO = f"https://www.douyin.com/video/{ITEM_ID}?source=%2f"
NOTE = f"https://www.douyin.com/note/{ITEM_ID}?source=%2f"
SHARE = f"{SHARE_ORIGIN}share/video/{ITEM_ID}/"
SLIDES = f"{SHARE_ORIGIN}share/slides/{ITEM_ID}/?source=%2f"
PLAY = "https://aweme.snssdk.com/aweme/v1/playwm/?video_id=synthetic%2Fvalue"
MEDIA = (
    "https://v5-se-bjtc-cold.douyinvod.com/video/tos/example/"
    "?mime_type=video_mp4&signature=%2fA%2B+value"
)
COVER = "https://p3-pc-sign.douyinpic.com/example.jpeg"


def share_html(item_id: str = ITEM_ID, *, urls: list[str] | None = None) -> bytes:
    item = {
        "aweme_id": item_id,
        "desc": "测试视频",
        "video": {
            "width": 1080,
            "height": 1920,
            "duration": 12900,
            "cover": {"url_list": [COVER]},
            "play_addr": {"url_list": [PLAY] if urls is None else urls},
        },
    }
    state = {"loaderData": {"video_(id)/page": {"videoInfoRes": {"item_list": [item]}}}}
    return f"<script>window._ROUTER_DATA = {json.dumps(state)};</script>".encode()


@dataclass
class FakeSession:
    upstream: FakeUpstream
    curl_options: dict[CurlOpt, Any] = field(default_factory=dict)
    cookies: dict[str, str] = field(default_factory=dict)

    async def __aenter__(self) -> FakeSession:
        return self

    async def __aexit__(self, *_: object) -> None:
        pass

    async def get(self, url: str, **kwargs: Any) -> Response:
        assert kwargs["allow_redirects"] is False and kwargs["verify"] is True
        assert kwargs["quote"] is False
        assert "iPhone" in kwargs["headers"]["User-Agent"]
        assert kwargs["headers"]["Referer"] == SHARE_ORIGIN
        assert self.curl_options == {
            CurlOpt.RESOLVE: [f"{url.split('/')[2]}:443:8.8.8.8"],
            CurlOpt.FRESH_CONNECT: 1,
        }
        self.upstream.requests.append((url, self.cookies.copy()))
        status, headers, body = self.upstream.responses[url]
        if "set-cookie" in headers:
            self.cookies["ttwid"] = headers["set-cookie"]
        if kwargs["content_callback"](body) == CURL_WRITEFUNC_ERROR:
            raise CurlError("bounded fake response", CurlECode.WRITE_ERROR)
        response = Response()
        response.status_code = status
        response.headers = Headers(headers)
        return response


class FakeUpstream:
    def __init__(self) -> None:
        self.requests: list[tuple[str, dict[str, str]]] = []
        self.dns: list[str] = []
        self.responses: dict[str, tuple[int, dict[str, str], bytes]] = {
            SHORT: (302, {"location": VIDEO}, b""),
            SHARE_ORIGIN: (
                301,
                {"location": "https://www.douyin.com/", "set-cookie": "anonymous"},
                b"",
            ),
            SHARE: (200, {}, share_html()),
            PLAY: (302, {"location": MEDIA}, b""),
        }

    def session(self, *, trust_env: bool) -> FakeSession:
        assert not trust_env
        return FakeSession(self)

    async def getaddrinfo(self, host: str, port: int, **_: object) -> list[tuple]:
        assert port == 443
        self.dns.append(host)
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("8.8.8.8", port))]


class FakeBrowser:
    def __init__(self, target_id: str = ITEM_ID) -> None:
        self.calls: list[tuple[str, Deadline]] = []
        self.target_id = target_id

    async def fetch_detail(self, url: str, deadline: Deadline) -> tuple[str, dict[str, Any]]:
        self.calls.append((url, deadline))
        return self.target_id, {
            "aweme_id": self.target_id,
            "images": [{"url_list": [COVER]}] if "/note/" in url else [],
            "video": {
                "playAddr": ["https://v11-weba.douyinvod.com/browser-example.mp4"],
            },
        }


@pytest.fixture
def upstream(monkeypatch: pytest.MonkeyPatch) -> FakeUpstream:
    fake = FakeUpstream()
    monkeypatch.setattr(share_client, "AsyncSession", fake.session)
    return fake


def pin_dns(monkeypatch: pytest.MonkeyPatch, upstream: FakeUpstream) -> None:
    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", upstream.getaddrinfo)


@pytest.mark.parametrize("url", [SHORT, VIDEO, SHARE])
@pytest.mark.parametrize("media_url", [MEDIA, MEDIA.replace("v5-se-bjtc-cold", "v9-chc")])
async def test_http_video_returns_only_verified_rendition_metadata(
    monkeypatch: pytest.MonkeyPatch, upstream: FakeUpstream, url: str, media_url: str
) -> None:
    pin_dns(monkeypatch, upstream)
    upstream.responses[PLAY] = (302, {"location": media_url}, b"")
    browser = FakeBrowser()
    note = await DouyinAdapter(Settings(api_key="test"), browser).parse(url, Deadline(2))

    assert not browser.calls
    assert note.note_id == ITEM_ID and note.title == "测试视频" and note.kind == "video"
    assert note.cover and note.cover.url == COVER
    (video,) = note.videos
    assert video.url == media_url
    assert video.duration_seconds is video.source_width is video.source_height is None
    assert upstream.requests[-3:] == [
        (SHARE_ORIGIN, {}),
        (SHARE, {"ttwid": "anonymous"}),
        (PLAY, {}),
    ]
    assert upstream.dns[-4:] == [
        "www.iesdouyin.com",
        "www.iesdouyin.com",
        "aweme.snssdk.com",
        urlsplit(media_url).hostname,
    ]


async def test_browser_fallback_preserves_verified_target_and_deadline(
    monkeypatch: pytest.MonkeyPatch, upstream: FakeUpstream
) -> None:
    pin_dns(monkeypatch, upstream)
    upstream.responses[SHARE] = (200, {}, b"<script>window._ROUTER_DATA = {};</script>")
    browser = FakeBrowser()
    deadline = Deadline(2)
    note = await DouyinAdapter(Settings(api_key="test"), browser).parse(SHORT, deadline)
    assert note.note_id == ITEM_ID
    assert browser.calls == [(VIDEO, deadline)]


@pytest.mark.parametrize("location", [NOTE, SLIDES])
async def test_short_link_to_note_uses_existing_browser_path(
    monkeypatch: pytest.MonkeyPatch, upstream: FakeUpstream, location: str
) -> None:
    pin_dns(monkeypatch, upstream)
    upstream.responses[SHORT] = (302, {"location": location}, b"")
    browser = FakeBrowser()
    note = await DouyinAdapter(Settings(api_key="test"), browser).parse(SHORT, Deadline(2))
    assert note.kind == "image" and note.images[0].url == COVER
    assert upstream.requests == [(SHORT, {})]
    assert browser.calls[0][0] == NOTE


@pytest.mark.parametrize(
    ("url", "response", "code"),
    [
        (SHARE, (200, {}, share_html(OTHER_ID)), "PARSE_FAILED"),
        (SHARE, (403, {}, b""), "UPSTREAM_ACCESS_RESTRICTED"),
        (SHARE, (429, {}, b""), "UPSTREAM_RATE_LIMITED"),
        (SHARE, (200, {}, "<h1>请先登录后查看</h1>".encode()), "UPSTREAM_LOGIN_REQUIRED"),
        (SHARE, (302, {"location": "/captcha/"}, b""), "UPSTREAM_ACCESS_RESTRICTED"),
        (SHORT, (302, {"location": "https://evil.example/login/"}, b""), "INVALID_URL"),
        (
            PLAY,
            (302, {"location": "https://unknown.douyinvod.com/example.mp4"}, b""),
            "INVALID_URL",
        ),
    ],
)
async def test_explicit_upstream_errors_do_not_fall_back(
    monkeypatch: pytest.MonkeyPatch,
    upstream: FakeUpstream,
    url: str,
    response: tuple[int, dict[str, str], bytes],
    code: str,
) -> None:
    pin_dns(monkeypatch, upstream)
    upstream.responses[url] = response
    browser = FakeBrowser()
    with pytest.raises(AppError) as caught:
        await DouyinAdapter(Settings(api_key="test"), browser).parse(SHORT, Deadline(2))
    assert caught.value.code == code
    assert not browser.calls
    assert "evil.example" not in upstream.dns and "unknown.douyinvod.com" not in upstream.dns


async def test_rejects_private_dns_before_connecting(
    monkeypatch: pytest.MonkeyPatch, upstream: FakeUpstream
) -> None:
    async def private(*_: object, **__: object) -> list[tuple]:
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("127.0.0.1", 443))]

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", private)
    browser = FakeBrowser()
    with pytest.raises(AppError) as caught:
        await DouyinAdapter(Settings(api_key="test"), browser).parse(VIDEO, Deadline(2))
    assert caught.value.code == "INVALID_URL"
    assert not upstream.requests and not browser.calls


async def test_rejects_oversized_html_without_fallback(
    monkeypatch: pytest.MonkeyPatch, upstream: FakeUpstream
) -> None:
    pin_dns(monkeypatch, upstream)
    browser = FakeBrowser()
    settings = Settings(api_key="test", max_html_bytes=100)
    with pytest.raises(AppError) as caught:
        await DouyinAdapter(settings, browser).parse(VIDEO, Deadline(2))
    assert caught.value.code == "UPSTREAM_BAD_RESPONSE"
    assert not browser.calls
