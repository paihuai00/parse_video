# Implementation Plan: Xiaohongshu media parser API

## Gate 0: Repository and contract baseline

- [ ] Confirm or initialize the intended Git repository before the final commit stage.
- [x] Create Python 3.12 project metadata, application/test packages, formatting/lint/type-check configuration, and an exact dependency lock.
- [x] Add contract-validation utilities that load `docs/openapi.json` and all checked-in examples.
- [x] Convert applicable architecture rules into backend Trellis specs; mark frontend specs not applicable rather than inventing frontend conventions.

Validation:

```sh
python3 -m json.tool docs/openapi.json >/dev/null
python3 -m compileall app tests scripts
```

## Gate 1: Models, URL policy, and parser core

- [x] Implement configuration, domain errors, internal models, and public Pydantic models.
- [x] Implement strict URL/path parsing, normalization, cache identity, public-address classification, asynchronous DNS resolution, and per-hop `ResolvedHop` plans.
- [x] Implement the `curl_cffi==0.13.0` transport with manual redirects, `CurlOpt.RESOLVE`, TLS verification, cookie continuity, cancellation, one total deadline, limited retry, and bounded callback collection.
- [x] Implement login/challenge/rate-limit/not-found classification.
- [x] Implement bounded initial-state extraction and token-safe `undefined` conversion.
- [x] Implement note lookup and image/video/cover normalization.
- [x] Build sanitized synthetic fixtures for documented successful and failure structures.
- [x] Add the opt-in probe without embedding live links or secrets.

Validation:

```sh
pytest -q tests/test_url_rules.py tests/test_client.py tests/test_state_reader.py tests/test_media.py tests/test_probe.py
```

Rollback point: parser and transport remain independently testable and are not yet exposed over HTTP.

## Gate 2: API contract

- [x] Implement the FastAPI application factory, lifespan-managed services, parse route, and health route.
- [x] Implement startup configuration validation and constant-time API-key comparison.
- [x] Add request-body/field constraints, request IDs, unified exception handlers, and secret-safe structured logging.
- [x] Verify runtime response models and checked-in OpenAPI/examples remain aligned.

Validation:

```sh
pytest -q tests/test_api.py tests/test_contract.py tests/test_logging.py
```

Rollback point: disable route registration while retaining the tested parser package.

## Gate 3: Bounded service behavior

- [x] Implement rolling-window per-key rate limiting with cleanup.
- [x] Implement success-only TTL/LRU caching and refresh bypass.
- [x] Implement same-key in-flight coalescing with independent caller metadata.
- [x] Implement bounded admission, upstream concurrency, queue timeout, total timeout, and disconnect/cancellation cleanup.
- [x] Add deterministic fake-clock/fake-upstream tests; never load-test Xiaohongshu.

Validation:

```sh
pytest -q tests/test_cache.py tests/test_rate_limit.py tests/test_admission.py tests/test_parse_service.py
```

Rollback point: service controls are composed around the API/parser and can be reverted as a unit without changing parsing semantics.

## Gate 4: Container and documentation delivery

- [x] Add `Dockerfile`, `compose.yaml`, `.dockerignore`, `.env.example`, production entrypoint, and Nginx example.
- [ ] Verify single-worker/non-root runtime, missing-key startup failure, loopback binding, health check, resource limits, and log rotation configuration.
- [x] Update README, technical design, implementation checklist, deployment guide, OpenAPI, and examples to match delivered behavior.
- [x] Keep VPS/P5 checkboxes open and state exactly which real-network checks were not run.

Validation when Docker is available:

```sh
docker compose config --quiet
docker compose build
docker compose up -d
docker compose ps
curl --fail --silent --show-error http://127.0.0.1:8000/healthz
```

Rollback point: preserve the previous tagged image/config pair; stop the candidate with Compose without deleting unrelated containers or data.

## Gate 5: Full quality review

- [x] Run formatting, lint, type checking, full offline tests, contract checks, and Compose static checks.
- [ ] Build and start the image, verify non-root runtime, and run the container health check when a Docker daemon is available.
- [x] Review cross-layer propagation from URL input through internal models to response serialization and logging.
- [x] Verify no secrets, live tokens, signed media URLs, or raw HTML were added to tracked files or test output.
- [ ] Run the opt-in real probe only if the user supplies an authorized link/environment; record a redacted result and do not convert a missing external test into an implementation failure.
- [x] Update Trellis backend specs with the implemented cross-layer contract and discovered gotchas.
- [ ] Resolve the Git repository requirement, commit the reviewed result, and complete the finish workflow.

Expected final commands (exact tool configuration may be refined in Gate 0):

```sh
ruff format --check .
ruff check .
mypy app
pytest -q
python3 ./.trellis/scripts/task.py validate 10-18-implement-xhs-media-parser-api
```

## Start Preconditions

- The user approves the final PRD/design/implementation summary in a new message.
- `implement.jsonl` and `check.jsonl` contain real context entries and validate.
- No unresolved product-scope decisions remain. Git and real-sample availability may remain explicit delivery-stage constraints.
