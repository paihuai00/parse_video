from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

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
    assert set(contract["paths"]) == {"/healthz", "/api/v1/xiaohongshu/parse"}
