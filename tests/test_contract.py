from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from app.config import Settings
from app.main import create_app

ROOT = Path(__file__).parents[1]


def test_checked_in_examples_match_openapi_schemas() -> None:
    contract = json.loads((ROOT / "docs/openapi.json").read_text(encoding="utf-8"))
    contract_id = "https://local.invalid/openapi.json"
    contract["$id"] = contract_id
    registry = Registry().with_resource(
        contract_id,
        Resource.from_contents(contract, default_specification=DRAFT202012),
    )
    pairs = {
        "parse-request.json": "ParseRequest",
        "image-response.json": "ParseSuccess",
        "live-photo-response.json": "ParseSuccess",
        "video-response.json": "ParseSuccess",
        "error-response.json": "ParseError",
    }
    for filename, schema_name in pairs.items():
        instance = json.loads((ROOT / "docs/examples" / filename).read_text(encoding="utf-8"))
        schema = {"$ref": f"{contract_id}#/components/schemas/{schema_name}"}
        errors = list(Draft202012Validator(schema, registry=registry).iter_errors(instance))
        assert errors == [], f"{filename}: {errors}"


def test_contract_has_exact_public_routes() -> None:
    contract = json.loads((ROOT / "docs/openapi.json").read_text(encoding="utf-8"))
    assert set(contract["paths"]) == {
        "/healthz",
        "/api/v1/parse",
        "/api/v1/xiaohongshu/parse",
    }


def test_runtime_openapi_keeps_the_structured_optional_live_video_schema() -> None:
    runtime = create_app(Settings(api_key="test-key", environment="test")).openapi()
    image_media = runtime["components"]["schemas"]["ImageMedia"]
    assert "live_video" in image_media["properties"]
    assert "live_video" not in image_media["required"]
    assert image_media["additionalProperties"] is False


def test_checked_in_success_examples_match_the_public_schema() -> None:
    contract = json.loads((ROOT / "docs/openapi.json").read_text(encoding="utf-8"))
    contract_id = "https://local.invalid/openapi.json"
    contract["$id"] = contract_id
    registry = Registry().with_resource(
        contract_id,
        Resource.from_contents(contract, default_specification=DRAFT202012),
    )
    schema = {"$ref": f"{contract_id}#/components/schemas/ParseSuccess"}
    examples = contract["paths"]["/api/v1/xiaohongshu/parse"]["post"]["responses"]["200"][
        "content"
    ]["application/json"]["examples"]
    for name, example in examples.items():
        errors = list(Draft202012Validator(schema, registry=registry).iter_errors(example["value"]))
        assert errors == [], f"{name}: {errors}"


def test_unified_success_examples_match_decimal_id_schema() -> None:
    contract = json.loads((ROOT / "docs/openapi.json").read_text(encoding="utf-8"))
    contract_id = "https://local.invalid/openapi.json"
    contract["$id"] = contract_id
    registry = Registry().with_resource(
        contract_id,
        Resource.from_contents(contract, default_specification=DRAFT202012),
    )
    schema = {"$ref": f"{contract_id}#/components/schemas/UnifiedParseSuccess"}
    examples = contract["paths"]["/api/v1/parse"]["post"]["responses"]["200"]["content"][
        "application/json"
    ]["examples"]
    for name, example in examples.items():
        errors = list(Draft202012Validator(schema, registry=registry).iter_errors(example["value"]))
        assert errors == [], f"{name}: {errors}"
