from __future__ import annotations

import logging

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_access_log_does_not_include_query_or_api_key(caplog) -> None:
    caplog.set_level(logging.INFO, logger="parser_video")
    app = create_app(Settings(api_key="super-secret-key", environment="test"))
    client = TestClient(app)
    client.get("/healthz?xsec_token=share-secret", headers={"X-API-Key": "super-secret-key"})
    output = "\n".join(record.getMessage() for record in caplog.records)
    assert "share-secret" not in output
    assert "super-secret-key" not in output
    assert '"path":"/healthz"' in output


def test_early_body_rejection_is_logged_with_safe_outcome(caplog) -> None:
    caplog.set_level(logging.INFO, logger="parser_video")
    app = create_app(Settings(api_key="super-secret-key", environment="test"))
    client = TestClient(app)
    response = client.post(
        "/api/v1/xiaohongshu/parse",
        content=b"x" * 9000,
        headers={"X-API-Key": "super-secret-key"},
    )
    output = "\n".join(record.getMessage() for record in caplog.records)
    assert response.status_code == 413
    assert '"outcome_code":"INPUT_TOO_LARGE"' in output
    assert "super-secret-key" not in output
