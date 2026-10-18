# Technical Design: Xiaohongshu media parser API

## Architecture

The service is a single Python 3.12 application with explicit boundaries:

```text
HTTP routes/auth/error handlers
        -> parse service (deadline, rate, cache, coalescing, admission)
        -> URL policy + pinned upstream transport
        -> initial-state reader + media normalizer
        -> contract models
```

Planned modules follow the existing implementation document:

```text
app/
  main.py
  config.py
  errors.py
  models.py
  api/{routes,auth,error_handlers}.py
  parser/{url_rules,client,state_reader,media}.py
  services/{parse_service,cache,admission,rate_limit}.py
scripts/probe.py
tests/{fixtures,...}
```

No frontend or persistence layer is introduced.

## Data Flow

1. FastAPI creates a request ID and validates body size, JSON shape, API key, URL length, and rate limit.
2. The service derives a secret-safe cache-key digest. A fresh cache hit returns a new response envelope immediately unless `refresh=true`.
3. Same-key callers join an in-flight operation after admission. Each waiter retains its own request ID and cancellation state.
4. The admitted leader enters the global upstream semaphore under the original request deadline.
5. The URL policy parses the current hop, resolves all addresses, rejects any non-global address, and creates a connection plan.
6. The transport performs one request with redirects disabled and `CurlOpt.RESOLVE` populated from the vetted addresses. Redirect targets repeat step 5, with a maximum of three hops.
7. A native content callback accumulates decompressed bytes up to 2 MiB and aborts beyond the limit. Cookies issued during the anonymous flow are carried only across allowed Xiaohongshu hops.
8. The reader extracts and decodes the requested note state. The media normalizer produces an immutable internal result.
9. Successful internal results enter the TTL/LRU cache. The route creates caller-specific metadata and validates the final response model.

## Core Contracts

### URL and connection plan

`UrlPolicy` returns a `ResolvedHop` containing the normalized URL, host, port, supported-path state, requested note ID when available, and vetted IPv4/IPv6 addresses. The transport consumes this object rather than accepting an unchecked string URL.

Every redirect is handled in application code with `allow_redirects=False`. `CurlOpt.RESOLVE` supplies `host:port:address[,address]` entries so the TLS request keeps the original hostname while the actual connection uses the vetted IP set. This follows libcurl's documented resolver override. A unit/integration transport test must confirm the pinned option is passed by `curl_cffi==0.13.0`; failure to pin is fail-closed.

### Bounded body collection

Use `content_callback` rather than queue-backed streaming. The callback counts delivered decompressed bytes, appends while within the configured maximum, and aborts immediately on overflow. The client maps callback abort caused by the limit to `UPSTREAM_BAD_RESPONSE`, while preserving cancellation and deadline errors separately.

### Parsing

The state reader performs a character-level bounded scan for the exact assignment and balances object/array delimiters while respecting JSON strings and escapes. A token-aware normalization pass replaces `undefined` only where a JSON value can appear. Parsed objects are then navigated by requested note ID with explicit type checks and size/depth guards.

The normalizer converts raw dictionaries into internal typed image, video, cover, and note records. API models are constructed only after normalization, keeping upstream shape handling out of routes.

### Errors and logging

Domain exceptions carry business code, HTTP status, retryability, and an internal safe diagnostic. A single error handler builds the public envelope. Framework 404/405 and validation errors are translated into the same model.

Structured logs contain request ID, note ID when known, duration, cache result, outcome code, and bounded queue/concurrency counters. URL query values, API keys, cookies, media URLs, response bodies, and stack traces are never serialized into normal logs. Unexpected exceptions may include a server-side traceback only when the logging formatter is proven to redact request values.

## In-Memory Coordination

- Rate limit: a monotonic-time sliding-window deque per configured API key; stale timestamps and inactive entries are removed.
- Cache: `OrderedDict`-style TTL/LRU of immutable parse results, capped at 256.
- In-flight map: cache-key to a shared task plus waiter count. Cancelling one waiter must shield the shared leader while other waiters remain; the final waiter may cancel orphaned work.
- Admission: a bounded waiter counter combined with an upstream semaphore. Admission and release are exception-safe and use monotonic deadlines.
- Total deadline: one deadline object is created before queueing and its remaining duration is passed through every wait, redirect, retry, fetch, and parse operation.

## API and Configuration

Pydantic settings validate environment configuration at startup. Production mode rejects a missing/empty `XHS_API_KEY`. Defaults match the documented initial values, while limits remain configurable through the `XHS_*` variables already listed in `docs/deployment.md`.

The checked-in OpenAPI file remains the public contract. Tests validate examples against both checked-in schemas and runtime responses; any intentional difference updates the contract and examples in the same change.

## Container and Operations

The image uses Python 3.12 slim, installs locked dependencies in a builder stage when useful, creates UID/GID 10001, writes no runtime data under the application directory, and starts one Uvicorn worker. Compose binds `127.0.0.1:8000`, caps logs and memory, and checks only `/healthz`.

The Nginx example is an additive site/location fragment. It defines JSON responses for proxy-generated errors, passes through application bodies, does not log secrets, and does not proxy media.

## Compatibility, Rollback, and Documentation

- `curl_cffi==0.13.0` and `chrome136` are compatibility baselines and require explicit regression work before changes.
- Runtime state is intentionally ephemeral; process/container restart is the rollback boundary for cache, limits, and in-flight work.
- Deployment uses traceable image tags and preserves the prior image/config pair.
- `docs/implementation-plan.md` checkboxes are updated only for work actually verified. VPS/P5 items stay open until user-run evidence exists.

## Feasibility and Risks

The design is implementable with the selected stack. Official curl/libcurl material confirms native callback streaming and hostname-to-address overrides are available. The main risks are upstream HTML drift, anonymous-access restrictions, callback-abort behavior differences in the pinned release, and missing real fixtures. Transport behavior will therefore be isolated behind tests, and real probing remains opt-in.

The current absence of Git affects release traceability and Trellis commit/archive workflow, not application construction. It must be resolved before final completion.
