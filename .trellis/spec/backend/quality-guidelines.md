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

Tests use sanitized offline fixtures and fakes. Routine tests never call Xiaohongshu or Douyin. URL tests stop rejected targets before transport, concurrency tests use fake adapters, and checked-in examples are validated against OpenAPI. A real probe requires a user-supplied authorized URL and outputs only a redacted summary. Verify the Douyin HTTP path with a fresh guest session and force the browser branch to fail in the test that proves HTTP acquisition. For a real video acceptance sample, perform an independent GET of the returned URL and verify the complete MP4. Keep short-link tokens, real work IDs, cookies, and signed media URLs out of version control.

Forbidden patterns include automatic redirects in the HTTP client; executing page JavaScript outside the controlled Douyin browser acquisition boundary; unbounded browser requests, script state, proxy tunnels, response/cache/queue/retry behavior; committed live secrets or sample identifiers; and multiple workers without redesigning process-local coordination. The controlled browser must use exact egress hosts, public-address DNS validation with pinned connections, a fresh context, the original request deadline, and deterministic cancellation/cleanup tests.

Unified media changes also require offline wire proofs of signed-target preservation, vetted-IP TCP with original TLS identity, pull backpressure and deterministic cancellation, including disconnect before response headers. Cover credential capacity atomicity/non-eviction, image/motion pairing across providers, AVIF/HEIF rejection as MP4, explicit empty redirect queries, transient vs unsafe DNS, source failure after headers, and no provider retry after publication errors. Checked-in schemas/examples must match runtime. Do not interpret synthetic fixtures as live provider/CDN evidence.
