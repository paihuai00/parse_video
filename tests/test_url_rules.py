from __future__ import annotations

import asyncio

import pytest

from app.errors import AppError
from app.parser.url_rules import ResolvedHop, cache_key, is_public_address, parse_url, resolve_url


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.example/explore/6ad1f8610000000018018eef",
        "https://user:pass@www.xiaohongshu.com/explore/6ad1f8610000000018018eef",
        "https://www.xiaohongshu.com:444/explore/6ad1f8610000000018018eef",
        "https://127.0.0.1/explore/6ad1f8610000000018018eef",
        "file:///etc/passwd",
        "https://www.xiaohongshu.com/explore/not-a-note",
        " https://xhslink.com/a",
        "https://xhslink.com/a\n",
        "https://xhslink.com/a?token=has space",
    ],
)
def test_rejects_unsafe_or_unsupported_urls(url: str) -> None:
    with pytest.raises(AppError) as caught:
        parse_url(url)
    assert caught.value.code == "INVALID_URL"


def test_preserves_share_query_and_extracts_note_id() -> None:
    value = parse_url(
        "https://www.xiaohongshu.com/discovery/item/6AD1F8610000000018018EEF?xsec_token=secret&xsec_source=pc_share"
    )
    assert value.note_id == "6ad1f8610000000018018eef"
    assert value.normalized_url.endswith("?xsec_token=secret&xsec_source=pc_share")


def test_cache_identity_includes_access_parameters_without_exposing_them() -> None:
    first = cache_key("https://xhslink.com/a?token=one")
    second = cache_key("https://xhslink.com/a?token=two")
    assert first != second
    assert "one" not in first


def test_public_address_policy() -> None:
    assert is_public_address("8.8.8.8")
    assert not is_public_address("127.0.0.1")
    assert not is_public_address("10.0.0.2")
    assert not is_public_address("::1")
    assert not is_public_address("224.0.0.1")
    assert not is_public_address("ff02::1")


def test_resolve_option_contains_only_vetted_address_set() -> None:
    hop = ResolvedHop("https://xhslink.com/a", "xhslink.com", 443, None, ("8.8.8.8", "1.1.1.1"))
    assert hop.resolve_entries == ["xhslink.com:443:8.8.8.8,1.1.1.1"]


async def test_resolution_rejects_a_host_if_any_answer_is_non_public(monkeypatch) -> None:
    async def fake_getaddrinfo(*args, **kwargs):
        _ = args, kwargs
        return [
            (2, 1, 6, "", ("8.8.8.8", 443)),
            (2, 1, 6, "", ("127.0.0.1", 443)),
        ]

    loop = asyncio.get_running_loop()
    monkeypatch.setattr(loop, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(AppError) as caught:
        await resolve_url("https://xhslink.com/a")
    assert caught.value.code == "INVALID_URL"
