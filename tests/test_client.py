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
from app.parser.url_rules import ResolvedHop, parse_url


class FakeSession:
    instances: ClassVar[list] = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.calls = []
        self.curl_options = {}
        self.resolve_history = []
        self.__class__.instances.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        self.resolve_history.append(self.curl_options.get(CurlOpt.RESOLVE))
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
        self.resolve_history.append(self.curl_options.get(CurlOpt.RESOLVE))
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
        return ResolvedHop(url, "xhslink.cn", 443, None, ("8.8.8.8",))

    RedirectSession.responses = [
        (302, {"location": "https://xhslink.cn.evil.example/private"}, b"")
    ]
    monkeypatch.setattr("app.parser.client.AsyncSession", RedirectSession)
    monkeypatch.setattr("app.parser.client.resolve_url", fake_resolve)
    client = XiaohongshuClient(Settings(api_key="x", environment="test"))

    with pytest.raises(AppError) as caught:
        await client.fetch("https://xhslink.cn/o/example-token", Deadline(1))
    assert caught.value.code == "INVALID_URL"
    assert calls == [
        "https://xhslink.cn/o/example-token",
        "https://xhslink.cn.evil.example/private",
    ]
    assert len(RedirectSession.instances[-1].calls) == 1


async def test_mobile_short_link_redirects_to_a_checked_detail_hop(monkeypatch) -> None:
    note_id = "6ad1f8610000000018018eef"
    detail_url = f"https://www.xiaohongshu.com/discovery/item/{note_id}?xsec_token=secret"
    resolved = []

    async def fake_resolve(url):
        resolved.append(url)
        if url.startswith("https://xhslink.cn/o/"):
            return ResolvedHop(url, "xhslink.cn", 443, None, ("8.8.8.8",))
        return ResolvedHop(url, "www.xiaohongshu.com", 443, note_id, ("1.1.1.1",))

    RedirectSession.responses = [
        (302, {"location": detail_url}, b""),
        (200, {"content-type": "text/html; charset=utf-8"}, b"<html></html>"),
    ]
    monkeypatch.setattr("app.parser.client.AsyncSession", RedirectSession)
    monkeypatch.setattr("app.parser.client.resolve_url", fake_resolve)
    client = XiaohongshuClient(Settings(api_key="x", environment="test"))

    result = await client.fetch("https://xhslink.cn/o/example-token", Deadline(1))

    assert result.note_id == note_id
    assert result.final_url == detail_url
    assert resolved == ["https://xhslink.cn/o/example-token", detail_url]
    session = RedirectSession.instances[-1]
    assert len(session.calls) == 2
    assert session.calls[0][1]["allow_redirects"] is False
    assert session.calls[1][1]["allow_redirects"] is False
    assert session.resolve_history == [
        ["xhslink.cn:443:8.8.8.8"],
        ["www.xiaohongshu.com:443:1.1.1.1"],
    ]
    assert session.curl_options == {CurlOpt.RESOLVE: ["www.xiaohongshu.com:443:1.1.1.1"]}


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


NOTE_ID = "aaaaaaaaaaaaaaaaaaaaaaaa"
DETAIL_URL = f"https://www.xiaohongshu.com/explore/{NOTE_ID}?xsec_token=synthetic&source=test"
SHORT_URL = "https://xhslink.cn/o/synthetic-token"


def install_redirect_scenario(monkeypatch, responses):
    resolved = []
    RedirectSession.instances = []
    RedirectSession.responses = list(responses)

    async def fake_resolve(url):
        parsed = parse_url(url)
        resolved.append(url)
        return ResolvedHop(
            parsed.normalized_url, parsed.host, parsed.port, parsed.note_id, ("8.8.8.8",)
        )

    monkeypatch.setattr("app.parser.client.AsyncSession", RedirectSession)
    monkeypatch.setattr("app.parser.client.resolve_url", fake_resolve)
    return resolved


async def test_safe_status_redirect_falls_back_once_with_original_query_and_session(
    monkeypatch, fixture_html
) -> None:
    resolved = install_redirect_scenario(
        monkeypatch,
        [
            (302, {"location": DETAIL_URL}, b""),
            (302, {"location": "/404?errorCode=-510001"}, b""),
            (302, {"location": DETAIL_URL}, b""),
            (200, {}, fixture_html("mobile_image_note.html").encode()),
        ],
    )
    client = XiaohongshuClient(Settings(api_key="x", environment="test"))
    result = await client.fetch(SHORT_URL, Deadline(1))
    assert result.note_id == NOTE_ID
    assert result.final_url == DETAIL_URL
    assert resolved == [SHORT_URL, DETAIL_URL, SHORT_URL, DETAIL_URL]
    sessions = RedirectSession.instances
    assert [s.kwargs["impersonate"] for s in sessions] == ["chrome136", "safari184_ios"]
    assert sessions[0] is not sessions[1]
    for session in sessions:
        assert session.kwargs["trust_env"] is False
        for _, options in session.calls:
            assert options["allow_redirects"] is False
            assert options["verify"] is True
            assert options["timeout"][1] <= 1


async def test_mobile_error_status_is_not_retried_or_reported_as_missing(monkeypatch) -> None:
    resolved = install_redirect_scenario(
        monkeypatch,
        [(302, {"location": "/404?errorCode=unknown"}, b"")] * 2,
    )
    with pytest.raises(AppError) as caught:
        await XiaohongshuClient(Settings(api_key="x", environment="test")).fetch(
            DETAIL_URL, Deadline(1)
        )
    assert caught.value.code == "UPSTREAM_BAD_RESPONSE"
    assert caught.value.retryable is False
    assert resolved == [DETAIL_URL, DETAIL_URL]
    assert len(RedirectSession.instances) == 2


@pytest.mark.parametrize(
    ("location", "code"),
    [
        ("/login?redirect=ignored", "UPSTREAM_LOGIN_REQUIRED"),
        ("/404/", "INVALID_URL"),
        ("/unknown", "INVALID_URL"),
        ("https://evil.example/404", "INVALID_URL"),
        ("https://xiaohongshu.com/404", "INVALID_URL"),
        ("https://www.xiaohongshu.com.evil.example/404", "INVALID_URL"),
        ("https://user:pass@www.xiaohongshu.com/404", "INVALID_URL"),
        ("https://www.xiaohongshu.com:444/404", "INVALID_URL"),
        ("http://www.xiaohongshu.com/404", "INVALID_URL"),
    ],
)
async def test_only_exact_safe_same_origin_error_status_is_fallback_eligible(
    monkeypatch, location, code
) -> None:
    install_redirect_scenario(monkeypatch, [(302, {"location": location}, b"")])
    with pytest.raises(AppError) as caught:
        await XiaohongshuClient(Settings(api_key="x", environment="test")).fetch(
            DETAIL_URL, Deadline(1)
        )
    assert caught.value.code == code
    assert len(RedirectSession.instances) == 1
    assert len(RedirectSession.instances[0].calls) == 1


async def test_short_link_cannot_directly_trigger_status_fallback(monkeypatch) -> None:
    install_redirect_scenario(
        monkeypatch, [(302, {"location": "https://www.xiaohongshu.com/404"}, b"")]
    )
    with pytest.raises(AppError) as caught:
        await XiaohongshuClient(Settings(api_key="x", environment="test")).fetch(
            SHORT_URL, Deadline(1)
        )
    assert caught.value.code == "INVALID_URL"
    assert len(RedirectSession.instances) == 1


async def test_regional_redirect_cannot_change_note_identity(monkeypatch) -> None:
    other_id = "bbbbbbbbbbbbbbbbbbbbbbbb"
    target = f"https://www.rednote.com/explore/{other_id}"
    resolved = install_redirect_scenario(monkeypatch, [(302, {"location": target}, b"")])
    with pytest.raises(AppError) as caught:
        await XiaohongshuClient(Settings(api_key="x", environment="test")).fetch(
            DETAIL_URL, Deadline(1)
        )
    assert caught.value.code == "UPSTREAM_BAD_RESPONSE"
    assert resolved == [DETAIL_URL, target]
    assert len(RedirectSession.instances[0].calls) == 1


async def test_regional_mobile_fallback_cannot_reset_redirect_budget(monkeypatch) -> None:
    regional_url = DETAIL_URL.replace("www.xiaohongshu.com", "www.rednote.com")
    resolved = install_redirect_scenario(
        monkeypatch,
        [
            (302, {"location": DETAIL_URL}, b""),
            (302, {"location": regional_url}, b""),
            (302, {"location": "/404"}, b""),
            (302, {"location": regional_url}, b""),
        ],
    )
    with pytest.raises(AppError) as caught:
        await XiaohongshuClient(Settings(api_key="x", environment="test")).fetch(
            SHORT_URL, Deadline(1)
        )
    assert caught.value.code == "UPSTREAM_BAD_RESPONSE"
    assert caught.value.detail == "redirect limit exceeded"
    assert resolved == [SHORT_URL, DETAIL_URL, regional_url, regional_url]
    assert [s.kwargs["impersonate"] for s in RedirectSession.instances] == [
        "chrome136",
        "safari184_ios",
    ]


async def test_fallback_cannot_reset_redirect_budget(monkeypatch) -> None:
    resolved = install_redirect_scenario(
        monkeypatch,
        [
            (302, {"location": DETAIL_URL}, b""),
            (302, {"location": "/404"}, b""),
            (302, {"location": DETAIL_URL}, b""),
        ],
    )
    with pytest.raises(AppError) as caught:
        await XiaohongshuClient(Settings(api_key="x", environment="test", max_redirects=2)).fetch(
            SHORT_URL, Deadline(1)
        )
    assert caught.value.code == "UPSTREAM_BAD_RESPONSE"
    assert caught.value.detail == "redirect limit exceeded"
    assert resolved == [SHORT_URL, DETAIL_URL, SHORT_URL]


async def test_desktop_retry_consumes_the_same_attempt_budget_as_mobile(monkeypatch) -> None:
    install_redirect_scenario(
        monkeypatch,
        [(500, {}, b""), (302, {"location": "/404"}, b"")],
    )
    with pytest.raises(AppError) as caught:
        await XiaohongshuClient(Settings(api_key="x", environment="test")).fetch(
            DETAIL_URL, Deadline(1)
        )
    assert caught.value.code == "UPSTREAM_BAD_RESPONSE"
    assert [s.kwargs["impersonate"] for s in RedirectSession.instances] == ["chrome136"] * 2


async def test_fallback_cannot_retry_its_temporary_error(monkeypatch) -> None:
    install_redirect_scenario(
        monkeypatch,
        [(302, {"location": "/404"}, b""), (500, {}, b"")],
    )
    with pytest.raises(AppError) as caught:
        await XiaohongshuClient(Settings(api_key="x", environment="test")).fetch(
            DETAIL_URL, Deadline(1)
        )
    assert caught.value.code == "UPSTREAM_BAD_RESPONSE"
    assert len(RedirectSession.instances) == 2


async def test_fallback_cannot_reset_total_deadline(monkeypatch) -> None:
    install_redirect_scenario(monkeypatch, [(302, {"location": "/404"}, b"")])
    calls = 0

    async def resolver(url):
        nonlocal calls
        calls += 1
        if calls > 1:
            await asyncio.sleep(1)
        parsed = parse_url(url)
        return ResolvedHop(url, parsed.host, parsed.port, parsed.note_id, ("8.8.8.8",))

    monkeypatch.setattr("app.parser.client.resolve_url", resolver)
    with pytest.raises(AppError) as caught:
        await XiaohongshuClient(Settings(api_key="x", environment="test")).fetch(
            DETAIL_URL, Deadline(0.02)
        )
    assert caught.value.code == "UPSTREAM_TIMEOUT"
    assert len(RedirectSession.instances) == 2
    assert RedirectSession.instances[1].calls == []


async def test_private_dns_after_fallback_is_not_retried(monkeypatch) -> None:
    install_redirect_scenario(monkeypatch, [(302, {"location": "/404"}, b"")])
    calls = 0

    async def resolver(url):
        nonlocal calls
        calls += 1
        if calls > 1:
            raise AppError("INVALID_URL", 400, detail="hostname resolved to a non-public address")
        parsed = parse_url(url)
        return ResolvedHop(url, parsed.host, parsed.port, parsed.note_id, ("8.8.8.8",))

    monkeypatch.setattr("app.parser.client.resolve_url", resolver)
    with pytest.raises(AppError) as caught:
        await XiaohongshuClient(Settings(api_key="x", environment="test")).fetch(
            DETAIL_URL, Deadline(1)
        )
    assert caught.value.code == "INVALID_URL"
    assert calls == 2
    assert RedirectSession.instances[1].calls == []


async def test_mobile_fallback_cannot_change_the_requested_note(monkeypatch) -> None:
    other_url = "https://www.xiaohongshu.com/explore/bbbbbbbbbbbbbbbbbbbbbbbb"
    resolved = install_redirect_scenario(
        monkeypatch,
        [(302, {"location": "/404"}, b""), (302, {"location": other_url}, b"")],
    )
    with pytest.raises(AppError) as caught:
        await XiaohongshuClient(Settings(api_key="x", environment="test")).fetch(
            DETAIL_URL, Deadline(1)
        )
    assert caught.value.code == "UPSTREAM_BAD_RESPONSE"
    assert resolved == [DETAIL_URL, DETAIL_URL, other_url]
    assert [len(s.calls) for s in RedirectSession.instances] == [1, 1]


async def test_cancellation_during_mobile_resolution_closes_session(monkeypatch) -> None:
    install_redirect_scenario(monkeypatch, [(302, {"location": "/404"}, b"")])
    started = asyncio.Event()
    closed = []
    original_resolve = __import__("app.parser.client", fromlist=["resolve_url"]).resolve_url

    class ClosingSession(RedirectSession):
        async def __aexit__(self, *args):
            closed.append(self.kwargs["impersonate"])

    calls = 0

    async def blocking_resolve(url):
        nonlocal calls
        calls += 1
        if calls > 1:
            started.set()
            await asyncio.Event().wait()
        return await original_resolve(url)

    monkeypatch.setattr("app.parser.client.AsyncSession", ClosingSession)
    monkeypatch.setattr("app.parser.client.resolve_url", blocking_resolve)
    task = asyncio.create_task(
        XiaohongshuClient(Settings(api_key="x", environment="test")).fetch(DETAIL_URL, Deadline(1))
    )
    await asyncio.wait_for(started.wait(), timeout=1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert closed == ["chrome136", "safari184_ios"]


@pytest.mark.parametrize(
    ("status", "body", "code"),
    [
        (200, b"<html>captcha</html>", "UPSTREAM_ACCESS_RESTRICTED"),
        (200, "<html>请先登录</html>".encode(), "UPSTREAM_LOGIN_REQUIRED"),
        (429, b"<html></html>", "UPSTREAM_RATE_LIMITED"),
        (404, b"<html></html>", "NOTE_NOT_FOUND"),
    ],
)
async def test_explicit_upstream_failures_never_trigger_mobile(
    monkeypatch, status, body, code
) -> None:
    install_redirect_scenario(monkeypatch, [(status, {}, body)])
    with pytest.raises(AppError) as caught:
        await XiaohongshuClient(Settings(api_key="x", environment="test")).fetch(
            DETAIL_URL, Deadline(1)
        )
    assert caught.value.code == code
    assert len(RedirectSession.instances) == 1


async def test_initial_unsafe_dns_never_triggers_mobile_or_transport(monkeypatch) -> None:
    install_redirect_scenario(monkeypatch, [])

    async def unsafe_resolve(url):
        raise AppError("INVALID_URL", 400, detail="hostname resolved to a non-public address")

    monkeypatch.setattr("app.parser.client.resolve_url", unsafe_resolve)
    with pytest.raises(AppError) as caught:
        await XiaohongshuClient(Settings(api_key="x", environment="test")).fetch(
            DETAIL_URL, Deadline(1)
        )
    assert caught.value.code == "INVALID_URL"
    assert len(RedirectSession.instances) == 1
    assert RedirectSession.instances[0].calls == []
