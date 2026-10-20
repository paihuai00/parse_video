from __future__ import annotations

import asyncio

import pytest

from app.config import Settings
from app.errors import AppError
from app.parser.client import Deadline
from app.parser.douyin.browser import (
    MAX_SCRIPT_ELEMENTS,
    DouyinBrowser,
    _blocked_document_error,
    _bounded_script_texts,
    _item_id_from_detail_url,
    _wait_for_target_detail,
)


class FakeScriptElement:
    def __init__(self, text: str) -> None:
        self.text = text

    async def evaluate(self, expression: str, limit: int) -> str | None:
        _ = expression
        return self.text if len(self.text.encode("utf-8")) <= limit else None


class FakeScriptLocator:
    def __init__(self, scripts: list[str], count: int | None = None) -> None:
        self.scripts = scripts
        self.declared_count = len(scripts) if count is None else count

    async def count(self) -> int:
        return self.declared_count

    def nth(self, index: int) -> FakeScriptElement:
        return FakeScriptElement(self.scripts[index])


class GrowingScriptLocator(FakeScriptLocator):
    def __init__(self, scripts: list[str]) -> None:
        super().__init__(scripts)
        self.count_calls = 0

    async def count(self) -> int:
        self.count_calls += 1
        return 1 if self.count_calls == 1 else len(self.scripts)


class FakePage:
    def __init__(self, locator: FakeScriptLocator) -> None:
        self.script_locator = locator

    def locator(self, selector: str) -> FakeScriptLocator:
        assert selector == "script"
        return self.script_locator


async def test_browser_reads_page_state_with_a_cumulative_byte_limit() -> None:
    page = FakePage(FakeScriptLocator(["一", "ab"]))
    assert await _bounded_script_texts(page, 5) == ["一", "ab"]

    with pytest.raises(AppError) as caught:
        await _bounded_script_texts(page, 4)
    assert caught.value.code == "UPSTREAM_BAD_RESPONSE"


async def test_browser_rejects_an_unbounded_number_of_script_elements() -> None:
    page = FakePage(FakeScriptLocator([], count=MAX_SCRIPT_ELEMENTS + 1))
    with pytest.raises(AppError) as caught:
        await _bounded_script_texts(page, 1024)
    assert caught.value.code == "UPSTREAM_BAD_RESPONSE"


async def test_browser_includes_scripts_appended_during_the_bounded_read() -> None:
    page = FakePage(GrowingScriptLocator(["bootstrap", "late-target-state"]))
    assert await _bounded_script_texts(page, 100) == ["bootstrap", "late-target-state"]


async def test_detail_waiter_ignores_other_work_ids_until_the_target_arrives() -> None:
    target = "7000000000000000001"
    captured: dict[str, dict] = {}
    event = asyncio.Event()
    waiter = asyncio.create_task(_wait_for_target_detail(captured, event, target, 1))

    captured["7000000000000000002"] = {"aweme_id": "7000000000000000002"}
    event.set()
    await asyncio.sleep(0)
    assert not waiter.done()

    expected = {"aweme_id": target, "video": {}}
    captured[target] = expected
    event.set()
    assert await waiter == expected


def test_detail_response_id_is_strictly_read_from_the_aweme_id_query() -> None:
    target = "7000000000000000001"
    assert (
        _item_id_from_detail_url(
            f"https://www.douyin.com/aweme/v1/web/aweme/detail/?aweme_id={target}"
        )
        == target
    )
    assert (
        _item_id_from_detail_url(
            f"https://www.douyin.com/aweme/v1/web/aweme/detail/?item_id={target}"
        )
        is None
    )


async def test_browser_transport_start_failure_uses_a_domain_error(monkeypatch) -> None:
    browser = DouyinBrowser(Settings(api_key="test-key", environment="test"))

    async def fail(*args, **kwargs):
        _ = args, kwargs
        raise OSError("loopback proxy unavailable")

    monkeypatch.setattr(browser, "_fetch_once", fail)
    with pytest.raises(AppError) as caught:
        await browser.fetch_detail("https://v.douyin.com/exampleToken/", Deadline(1))
    assert caught.value.code == "UPSTREAM_BAD_RESPONSE"
    assert caught.value.retryable is True


@pytest.mark.parametrize(
    ("url", "code"),
    [
        ("https://www.douyin.com/login/", "UPSTREAM_LOGIN_REQUIRED"),
        ("https://www.douyin.com/verify-page/", "UPSTREAM_ACCESS_RESTRICTED"),
        ("https://www.douyin.com/user/anything", "INVALID_URL"),
    ],
)
def test_blocked_document_redirects_keep_specific_failure_evidence(url: str, code: str) -> None:
    assert _blocked_document_error(url).code == code
