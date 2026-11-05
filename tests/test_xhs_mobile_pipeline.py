from __future__ import annotations

import json
from types import SimpleNamespace
from typing import ClassVar

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.parser.url_rules import ResolvedHop, parse_url

NOTE_ID = "aaaaaaaaaaaaaaaaaaaaaaaa"
SHORT_URL = "https://xhslink.cn/o/synthetic-token"
DETAIL_URL = f"https://www.xiaohongshu.com/discovery/item/{NOTE_ID}?xsec_token=synthetic"


class PipelineSession:
    responses: ClassVar[list] = []
    calls: ClassVar[list] = []

    def __init__(self, **kwargs):
        self.profile = kwargs["impersonate"]
        self.curl_options = {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def get(self, url, **kwargs):
        self.calls.append((self.profile, url))
        status, headers, body = self.responses.pop(0)
        kwargs["content_callback"](body)
        return SimpleNamespace(status_code=status, headers=headers, url=url)


def mobile_pipeline(monkeypatch, html):
    PipelineSession.calls = []
    PipelineSession.responses = [
        (302, {"location": DETAIL_URL}, b""),
        (302, {"location": "/404?errorCode=-510001"}, b""),
        (302, {"location": DETAIL_URL}, b""),
        (200, {}, html.encode()),
    ]

    async def fake_resolve(url):
        parsed = parse_url(url)
        return ResolvedHop(url, parsed.host, parsed.port, parsed.note_id, ("8.8.8.8",))

    monkeypatch.setattr("app.parser.client.AsyncSession", PipelineSession)
    monkeypatch.setattr("app.parser.client.resolve_url", fake_resolve)
    return TestClient(create_app(Settings(api_key="test-key", environment="test")))


@pytest.mark.parametrize("route", ["/api/v1/xiaohongshu/parse", "/api/v1/parse"])
def test_real_parse_pipeline_returns_complete_mobile_images_and_shares_cache(
    monkeypatch, fixture_html, route
) -> None:
    http = mobile_pipeline(monkeypatch, fixture_html("mobile_image_note.html"))
    headers = {"X-API-Key": "test-key"}
    with http:
        response = http.post(route, headers=headers, json={"url": SHORT_URL, "refresh": True})
        assert response.status_code == 200
        payload = response.json()
        assert payload["error"] is None
        assert payload["data"]["note_id"] == NOTE_ID
        assert payload["data"]["type"] == "image"
        images = payload["data"]["images"]
        assert len(images) == 2
        assert [x["index"] for x in images] == [1, 2]
        assert images[0]["url"] == ("https://sns-webpic-qc.xhscdn.com/detail-one.jpg?sig=synthetic")
        assert all(x["verification"] == "not_checked" and "live_video" not in x for x in images)
        assert payload["data"]["videos"] == []
        assert payload["data"]["cover"] is None
        cached = http.post("/api/v1/parse", headers=headers, json={"url": SHORT_URL})
        assert cached.status_code == 200
        assert cached.json()["meta"]["cache"]["hit"] is True
        assert cached.json()["meta"]["request_id"] != payload["meta"]["request_id"]
    assert PipelineSession.calls == [
        ("chrome136", SHORT_URL),
        ("chrome136", DETAIL_URL),
        ("safari184_ios", SHORT_URL),
        ("safari184_ios", DETAIL_URL),
    ]


def test_mobile_pipeline_rejects_partial_images_instead_of_returning_success(monkeypatch) -> None:
    state = {
        "noteData": {
            "hasError": False,
            "data": {
                "noteData": {
                    "noteId": NOTE_ID,
                    "type": "normal",
                    "imageList": [
                        {"url": "https://sns-webpic-qc.xhscdn.com/one.jpg"},
                        {"url": "https://evil.example/two.jpg"},
                    ],
                }
            },
        }
    }
    http = mobile_pipeline(monkeypatch, "window.__INITIAL_STATE__=" + json.dumps(state))
    with http:
        result = http.post(
            "/api/v1/xiaohongshu/parse",
            headers={"X-API-Key": "test-key"},
            json={"url": SHORT_URL},
        )
    assert result.status_code == 502
    assert result.json()["success"] is False
    assert result.json()["data"] is None
    assert result.json()["error"]["code"] == "MEDIA_NOT_FOUND"
    assert result.json()["meta"]["cache"] is None
