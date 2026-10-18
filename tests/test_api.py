from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from app.config import Settings
from app.errors import AppError
from app.main import create_app
from app.models import InternalImage, InternalNote
from app.services.parse_service import ServiceResult

ROOT = Path(__file__).parents[1]


def assert_contract(schema_name: str, instance: dict) -> None:
    contract = json.loads((ROOT / "docs/openapi.json").read_text(encoding="utf-8"))
    contract_id = "https://local.invalid/openapi.json"
    contract["$id"] = contract_id
    registry = Registry().with_resource(
        contract_id,
        Resource.from_contents(contract, default_specification=DRAFT202012),
    )
    validator = Draft202012Validator(
        {"$ref": f"{contract_id}#/components/schemas/{schema_name}"},
        registry=registry,
        format_checker=FormatChecker(),
    )
    assert list(validator.iter_errors(instance)) == []


class FakeService:
    def __init__(self) -> None:
        self.error = None

    async def parse(self, raw_url: str, refresh: bool, api_key: str) -> ServiceResult:
        _ = raw_url, refresh, api_key
        if self.error:
            raise self.error
        now = datetime.now(UTC)
        note = InternalNote(
            "6ad2355f000000001a027848",
            "示例",
            "image",
            (InternalImage("https://sns-webpic-qc.xhscdn.com/a.webp?sig=x", 10, 20, 1),),
            (),
            None,
        )
        return ServiceResult(note, now, now + timedelta(seconds=120), False)


def client(*, raise_server_exceptions: bool = True) -> tuple[TestClient, FakeService]:
    service = FakeService()
    app = create_app(Settings(api_key="test-key", environment="test"), service)
    return TestClient(app, raise_server_exceptions=raise_server_exceptions), service


def test_health_does_not_require_auth() -> None:
    http, _ = client()
    assert http.get("/healthz").json() == {"status": "ok"}


def test_production_startup_requires_api_key(monkeypatch) -> None:
    monkeypatch.setenv("XHS_ENV", "production")
    monkeypatch.delenv("XHS_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="XHS_API_KEY"):
        create_app()


def test_success_and_fresh_request_id() -> None:
    http, _ = client()
    body = {"url": "https://www.xiaohongshu.com/explore/6ad2355f000000001a027848"}
    first = http.post("/api/v1/xiaohongshu/parse", json=body, headers={"X-API-Key": "test-key"})
    second = http.post("/api/v1/xiaohongshu/parse", json=body, headers={"X-API-Key": "test-key"})
    assert first.status_code == 200
    assert first.json()["data"]["images"][0]["verification"] == "not_checked"
    assert first.json()["meta"]["request_id"] != second.json()["meta"]["request_id"]
    assert first.headers["x-request-id"] == first.json()["meta"]["request_id"]
    assert_contract("ParseSuccess", first.json())


def test_auth_validation_and_framework_errors_use_envelope() -> None:
    http, _ = client()
    url = "/api/v1/xiaohongshu/parse"
    missing = http.post(url, json={"url": "https://xhslink.com/a"})
    unknown = http.post(
        url,
        json={"url": "https://xhslink.com/a", "cookie": "secret"},
        headers={"X-API-Key": "test-key"},
    )
    route = http.get("/missing")
    method = http.get(url)
    assert missing.status_code == 401 and missing.json()["error"]["code"] == "UNAUTHORIZED"
    assert unknown.status_code == 400 and unknown.json()["error"]["code"] == "INVALID_REQUEST"
    assert route.json()["error"]["code"] == "ROUTE_NOT_FOUND"
    assert method.json()["error"]["code"] == "METHOD_NOT_ALLOWED"
    for response in (missing, unknown, route, method):
        assert response.headers["x-request-id"] == response.json()["meta"]["request_id"]
        assert_contract("ParseError", response.json())


def test_non_ascii_api_key_octet_is_rejected_instead_of_raising() -> None:
    http, _ = client()
    response = http.post(
        "/api/v1/xiaohongshu/parse",
        json={"url": "https://xhslink.com/a"},
        headers={"X-API-Key": b"\xff"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_domain_error_and_retry_after() -> None:
    http, service = client()
    service.error = AppError("RATE_LIMITED", 429, True, "test", 12)
    response = http.post(
        "/api/v1/xiaohongshu/parse",
        json={"url": "https://xhslink.com/a"},
        headers={"X-API-Key": "test-key"},
    )
    assert response.status_code == 429
    assert response.headers["retry-after"] == "12"
    assert response.json()["error"]["retryable"] is True


def test_body_size_limit() -> None:
    http, _ = client()
    response = http.post(
        "/api/v1/xiaohongshu/parse",
        content=b"x" * 9000,
        headers={"Content-Type": "application/json", "X-API-Key": "test-key"},
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "INPUT_TOO_LARGE"


def test_unexpected_error_uses_safe_contract_envelope() -> None:
    http, service = client(raise_server_exceptions=False)
    service.error = RuntimeError("must-not-leak")
    response = http.post(
        "/api/v1/xiaohongshu/parse",
        json={"url": "https://xhslink.com/a"},
        headers={"X-API-Key": "test-key"},
    )
    assert response.status_code == 500
    assert response.json()["error"] == {
        "code": "INTERNAL_ERROR",
        "message": "服务发生未预期错误。",
        "retryable": False,
    }
    assert "must-not-leak" not in response.text
    assert_contract("ParseError", response.json())
