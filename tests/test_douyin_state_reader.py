from __future__ import annotations

import json

import pytest

from app.errors import AppError
from app.parser.douyin.state_reader import decode_detail_response, decode_flight_detail


def flight_script(value: object, key: str = "7") -> str:
    encoded = json.dumps([1, f"{key}:{json.dumps(value, separators=(',', ':'))}"])
    return f"self.__pace_f.push({encoded})"


def test_flight_reader_selects_the_target_work_instead_of_a_recommendation() -> None:
    target = "7000000000000000002"
    recommendation = {
        "awemeId": "7000000000000000001",
        "desc": "推荐作品",
        "images": [{"urlList": ["https://p3-pc-sign.douyinpic.com/recommend.webp"]}],
    }
    expected = {
        "awemeId": target,
        "desc": "目标作品",
        "images": [{"urlList": ["https://p3-pc-sign.douyinpic.com/target.webp"]}],
    }
    scripts = [flight_script([recommendation, {"aweme": {"detail": expected}}])]
    assert decode_flight_detail(scripts, target, 100_000) == expected


def test_detail_response_requires_the_requested_id() -> None:
    target = "7000000000000000001"
    payload = json.dumps({"aweme_detail": {"aweme_id": target, "video": {}}}).encode()
    assert decode_detail_response(payload, target, 100_000) is not None
    with pytest.raises(AppError) as caught:
        decode_detail_response(payload, "7000000000000000004", 100_000)
    assert caught.value.code == "PARSE_FAILED"


def test_page_state_size_is_bounded() -> None:
    with pytest.raises(AppError) as caught:
        decode_flight_detail(["x" * 101], "7000000000000000002", 100)
    assert caught.value.code == "UPSTREAM_BAD_RESPONSE"
