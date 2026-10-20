from __future__ import annotations

import pytest

from app.errors import AppError
from app.parser.douyin.url_rules import douyin_cache_key, parse_douyin_url


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.example/video/7000000000000000001",
        "https://v.douyin.com.evil.example/token/",
        "https://user:pass@v.douyin.com/token/",
        "https://v.douyin.com:444/token/",
        "https://v.douyin.com/token/extra",
        "https://v.douyin.com/a%2Fb",
        "https://v.douyin.com/短链",
        "https://v.douyin.com/token/?source=has space",
        "https://v.douyin.com/token/?source=has\u007fcontrol",
        "https://www.douyin.com/user/7000000000000000001",
        "https://www.douyin.com/video/not-an-id",
        "https://www.iesdouyin.com/share/note/7000000000000000001/extra",
        "http://www.douyin.com/video/7000000000000000001",
    ],
)
def test_rejects_unsafe_or_unsupported_douyin_urls(url: str) -> None:
    with pytest.raises(AppError) as caught:
        parse_douyin_url(url)
    assert caught.value.code == "INVALID_URL"


def test_accepts_short_detail_and_share_urls_without_dropping_query() -> None:
    short = parse_douyin_url("https://V.DOUYIN.COM./Abc_123-xyz/?source=keep")
    detail = parse_douyin_url(
        "https://www.douyin.com/video/7000000000000000001?previous_page=web_code_link"
    )
    share = parse_douyin_url("https://www.iesdouyin.com/share/note/7000000000000000002/")
    assert short.is_short_link and short.item_id is None
    assert short.normalized_url.endswith("/?source=keep")
    assert detail.item_id == "7000000000000000001" and detail.kind == "video"
    assert share.item_id == "7000000000000000002" and share.kind == "note"


def test_cache_identity_is_namespaced_and_hides_access_values() -> None:
    first = douyin_cache_key("https://v.douyin.com/token/?source=one")
    second = douyin_cache_key("https://v.douyin.com/token/?source=two")
    assert first.startswith("douyin:")
    assert first != second
    assert "token" not in first and "one" not in first
