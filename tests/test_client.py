from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import ClassVar

import pytest
from curl_cffi import CurlError, CurlOpt
from curl_cffi.curl import CURL_WRITEFUNC_ERROR, Curl

from app.config import Settings
from app.errors import AppError
from app.parser.client import Deadline, XiaohongshuClient, classify_page
from app.parser.url_rules import ResolvedHop


class FakeSession:
    instances: ClassVar[list] = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.calls = []
        self.curl_options = {}
        self.__class__.instances.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        result = kwargs["content_callback"](b"<html>window.__INITIAL_STATE__={}</html>")
        if result == CURL_WRITEFUNC_ERROR:
            raise CurlError("callback aborted")
        return SimpleNamespace(
            status_code=200, headers={"content-type": "text/html; charset=utf-8"}, url=url
        )


class RedirectSession(FakeSession):
    responses: ClassVar[list[tuple[int, dict[str, str], bytes]]] = []

    async def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        status, headers, body = self.__class__.responses.pop(0)
        result = kwargs["content_callback"](body)
        if result == CURL_WRITEFUNC_ERROR:
            raise CurlError("callback aborted")
        return SimpleNamespace(status_code=status, headers=headers, url=url)


async def test_transport_pins_dns_and_disables_redirects(monkeypatch) -> None:
    async def fake_resolve(url):
        return ResolvedHop(
            url, "www.xiaohongshu.com", 443, "6ad1f8610000000018018eef", ("8.8.8.8",)
        )

    monkeypatch.setattr("app.parser.client.AsyncSession", FakeSession)
    monkeypatch.setattr("app.parser.client.resolve_url", fake_resolve)
    client = XiaohongshuClient(Settings(api_key="x", environment="test"))
    result = await client.fetch(
        "https://www.xiaohongshu.com/explore/6ad1f8610000000018018eef", Deadline(1)
    )
    session = FakeSession.instances[-1]
    assert session.kwargs["impersonate"] == "chrome136"
    assert session.kwargs["trust_env"] is False
    _, options = session.calls[0]
    assert options["allow_redirects"] is False
    assert options["verify"] is True
    assert ["www.xiaohongshu.com:443:8.8.8.8"] in session.curl_options.values()
    assert result.note_id == "6ad1f8610000000018018eef"


async def test_transport_aborts_decompressed_body_above_limit(monkeypatch) -> None:
    async def fake_resolve(url):
        return ResolvedHop(
            url,
            "www.xiaohongshu.com",
            443,
            "6ad1f8610000000018018eef",
            ("8.8.8.8",),
        )

    monkeypatch.setattr("app.parser.client.AsyncSession", FakeSession)
    monkeypatch.setattr("app.parser.client.resolve_url", fake_resolve)
    client = XiaohongshuClient(Settings(api_key="x", environment="test", max_html_bytes=5))
    with pytest.raises(AppError) as caught:
        await client.fetch(
            "https://www.xiaohongshu.com/explore/6ad1f8610000000018018eef",
            Deadline(1),
        )
    assert caught.value.code == "UPSTREAM_BAD_RESPONSE"


async def test_unsafe_redirect_is_validated_before_the_next_connection(monkeypatch) -> None:
    calls = []

    async def fake_resolve(url):
        calls.append(url)
        if "evil.example" in url:
            raise AppError("INVALID_URL", 400, detail="unsupported host")
        return ResolvedHop(url, "xhslink.com", 443, None, ("8.8.8.8",))

    RedirectSession.responses = [(302, {"location": "https://evil.example/private"}, b"")]
    monkeypatch.setattr("app.parser.client.AsyncSession", RedirectSession)
    monkeypatch.setattr("app.parser.client.resolve_url", fake_resolve)
    client = XiaohongshuClient(Settings(api_key="x", environment="test"))

    with pytest.raises(AppError) as caught:
        await client.fetch("https://xhslink.com/a", Deadline(1))
    assert caught.value.code == "INVALID_URL"
    assert calls == ["https://xhslink.com/a", "https://evil.example/private"]
    assert len(RedirectSession.instances[-1].calls) == 1


async def test_redirect_limit_stops_before_connecting_to_the_fourth_target(monkeypatch) -> None:
    resolved = []

    async def fake_resolve(url):
        resolved.append(url)
        return ResolvedHop(url, "xhslink.com", 443, None, ("8.8.8.8",))

    RedirectSession.responses = [
        (302, {"location": "/b"}, b""),
        (302, {"location": "/c"}, b""),
        (302, {"location": "/d"}, b""),
        (302, {"location": "https://evil.example/private"}, b""),
    ]
    monkeypatch.setattr("app.parser.client.AsyncSession", RedirectSession)
    monkeypatch.setattr("app.parser.client.resolve_url", fake_resolve)
    client = XiaohongshuClient(Settings(api_key="x", environment="test", max_redirects=3))

    with pytest.raises(AppError) as caught:
        await client.fetch("https://xhslink.com/a", Deadline(1))
    assert caught.value.code == "UPSTREAM_BAD_RESPONSE"
    assert len(resolved) == 4
    assert all("evil.example" not in item for item in resolved)
    assert len(RedirectSession.instances[-1].calls) == 4


async def test_dns_resolution_obeys_total_deadline(monkeypatch) -> None:
    async def slow_resolve(url):
        _ = url
        await asyncio.sleep(1)
        raise AssertionError("unreachable")

    monkeypatch.setattr("app.parser.client.AsyncSession", FakeSession)
    monkeypatch.setattr("app.parser.client.resolve_url", slow_resolve)
    client = XiaohongshuClient(Settings(api_key="x", environment="test"))

    with pytest.raises(AppError) as caught:
        await client.fetch("https://xhslink.com/a", Deadline(0.01))
    assert caught.value.code == "UPSTREAM_TIMEOUT"


async def test_unknown_response_charset_is_an_upstream_error(monkeypatch) -> None:
    class UnknownCharsetSession(FakeSession):
        async def get(self, url, **kwargs):
            self.calls.append((url, kwargs))
            kwargs["content_callback"](b"<html></html>")
            return SimpleNamespace(
                status_code=200,
                headers={"content-type": "text/html; charset=not-a-real-charset"},
                url=url,
            )

    async def fake_resolve(url):
        return ResolvedHop(
            url, "www.xiaohongshu.com", 443, "6ad1f8610000000018018eef", ("8.8.8.8",)
        )

    monkeypatch.setattr("app.parser.client.AsyncSession", UnknownCharsetSession)
    monkeypatch.setattr("app.parser.client.resolve_url", fake_resolve)
    client = XiaohongshuClient(Settings(api_key="x", environment="test"))
    with pytest.raises(AppError) as caught:
        await client.fetch(
            "https://www.xiaohongshu.com/explore/6ad1f8610000000018018eef", Deadline(1)
        )
    assert caught.value.code == "UPSTREAM_BAD_RESPONSE"


def test_pinned_curl_release_accepts_resolve_option() -> None:
    curl = Curl()
    try:
        curl.setopt(CurlOpt.RESOLVE, ["www.xiaohongshu.com:443:8.8.8.8"])
    finally:
        curl.close()


def test_page_classification(fixture_html) -> None:
    response = SimpleNamespace(status_code=200, url="https://www.xiaohongshu.com/login")
    with pytest.raises(AppError) as caught:
        classify_page(response, fixture_html("login.html"))
    assert caught.value.code == "UPSTREAM_LOGIN_REQUIRED"


def test_challenge_and_explicit_missing_page_classification(fixture_html) -> None:
    response = SimpleNamespace(
        status_code=200, url="https://www.xiaohongshu.com/explore/6ad1f8610000000018018eef"
    )
    with pytest.raises(AppError) as challenge:
        classify_page(response, fixture_html("challenge.html"))
    assert challenge.value.code == "UPSTREAM_ACCESS_RESTRICTED"

    missing = SimpleNamespace(status_code=404, url=response.url)
    with pytest.raises(AppError) as not_found:
        classify_page(missing, "<html>not found</html>")
    assert not_found.value.code == "NOTE_NOT_FOUND"
