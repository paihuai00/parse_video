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

Tests use sanitized offline fixtures and fakes. Routine tests never call Xiaohongshu. URL tests stop rejected targets before transport, concurrency tests use fake clients, and checked-in examples are validated against OpenAPI. A real probe requires a user-supplied authorized URL and outputs only a redacted summary.

Forbidden patterns include automatic redirects, executing page JavaScript, unbounded response/cache/queue/retry behavior, committed live secrets, and multiple workers without redesigning process-local coordination.
