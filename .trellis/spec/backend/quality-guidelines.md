# Quality Guidelines

The supported runtime is Python 3.12. Runtime and development dependencies are exact in `requirements.lock` and `requirements-dev.lock`.

```sh
ruff format --check app tests scripts
ruff check app tests scripts
mypy app
pytest -q
python -m compileall app tests scripts
python -m json.tool docs/openapi.json >/dev/null
```

Tests use sanitized offline fixtures and fakes. Routine tests never call Xiaohongshu or Douyin. URL tests stop rejected targets before transport, concurrency tests use fake adapters, and checked-in examples are validated against OpenAPI. A real probe requires a user-supplied authorized URL and outputs only a redacted summary. Real Douyin acceptance uses a fresh anonymous browser context and separately checks representative media with an anonymous, bounded client; short-link tokens, real work IDs, cookies, and signed media URLs are never committed.

Forbidden patterns include automatic redirects in the HTTP client; executing page JavaScript outside the controlled Douyin browser acquisition boundary; unbounded browser requests, script state, proxy tunnels, response/cache/queue/retry behavior; committed live secrets or sample identifiers; and multiple workers without redesigning process-local coordination. The controlled browser must use exact egress hosts, public-address DNS validation with pinned connections, a fresh context, the original request deadline, and deterministic cancellation/cleanup tests.
