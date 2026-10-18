# Service Contract

## Scenario: Parse one Xiaohongshu note into temporary media direct URLs

### 1. Scope / Trigger

Use this contract whenever code changes the HTTP API, upstream URL/transport policy, note parsing, media normalization, process-local resource controls, environment wiring, or deployment proxy. These layers form one observable contract: the caller submits one note URL, the service returns JSON direct URLs, and the caller downloads from the upstream CDN.

The service never proxies, stores, bundles, transcodes, or streams media files. Live-photo/mixed content, login sessions, batch input, and multiple workers remain outside v1.

### 2. Signatures

```http
POST /api/v1/xiaohongshu/parse
Content-Type: application/json
X-API-Key: <configured XHS_API_KEY>

{"url":"https://www.xiaohongshu.com/explore/<24-hex-id>?xsec_token=...","refresh":false}
```

```http
GET /healthz
```

Python ownership signatures:

```python
async def parse_note(body: ParseRequest, api_key: str, request: Request) -> ParseSuccess: ...

class ParseService:
    async def parse(self, raw_url: str, refresh: bool, api_key: str) -> ServiceResult: ...

class XiaohongshuClient:
    async def fetch(self, raw_url: str, deadline: Deadline) -> PageResponse: ...
```

### 3. Contracts

Request fields:

| Field | Type | Contract |
| --- | --- | --- |
| `url` | HTTP(S) URL | At most 4096 characters; exact supported Xiaohongshu host/path after at most three checked redirects; preserve access-significant query values |
| `refresh` | boolean | Defaults to `false`; skips result cache but not authentication, rate, admission, concurrency, or deadline controls |

Success response invariants:

- `success=true`, `error=null`, and a fresh `meta.request_id` for every caller.
- Image note: ordered non-empty `images`, empty `videos`, `cover=null`.
- Video note: empty `images`, exactly one positively identified MP4, and an optional separate cover.
- Every media object uses `verification="not_checked"`; `url_expires_at` stays `null` unless an actual expiry is known.
- Cache expiry describes only this service's result cache and never promises CDN availability.

Environment keys:

| Key | Required/default |
| --- | --- |
| `XHS_API_KEY` | Required and non-empty when `XHS_ENV=production` |
| `XHS_ENV` | `production` |
| `XHS_IMPERSONATE` | `chrome136` |
| `XHS_REQUEST_TIMEOUT_SECONDS` | `20` total, including DNS, queue, redirects, retry, fetch, and parse |
| `XHS_CONNECT_TIMEOUT_SECONDS` | `5`, capped by remaining total time |
| `XHS_UPSTREAM_CONCURRENCY` / `XHS_QUEUE_CAPACITY` | `2` / `4`; coalesced followers consume waiter capacity too |
| `XHS_QUEUE_WAIT_SECONDS` | `2` |
| `XHS_CACHE_TTL_SECONDS` / `XHS_CACHE_MAX_ENTRIES` | `120` / `256`, successes only |
| `XHS_RATE_LIMIT_PER_MINUTE` | `20` per authenticated key, before cache lookup |
| `XHS_MAX_REDIRECTS` / `XHS_MAX_HTML_BYTES` | `3` / `2097152` decompressed bytes |

Upstream connections use `curl_cffi==0.13.0`, explicit `chrome136`, `trust_env=False`, manual redirects, TLS verification, and a fresh anonymous session per parse. Before every hop, validate all resolved addresses as public unicast and replace the session-level `CurlOpt.RESOLVE` entry with the vetted host/port/address set.

### 4. Validation & Error Matrix

| Condition | HTTP / code |
| --- | --- |
| Malformed JSON/body or forbidden field | `400 INVALID_REQUEST` |
| Unsupported URL, credentials/IP/control characters, unsafe DNS or redirect | `400 INVALID_URL` |
| Missing, wrong, or non-ASCII API key | `401 UNAUTHORIZED` |
| Explicit missing note evidence | `404 NOTE_NOT_FOUND` |
| Unknown route / wrong method | `404 ROUTE_NOT_FOUND` / `405 METHOD_NOT_ALLOWED` |
| Body over the HTTP input limit | `413 INPUT_TOO_LARGE` |
| Live-photo or mixed media | `422 UNSUPPORTED_CONTENT` |
| Per-key request window exceeded | `429 RATE_LIMITED` with `Retry-After` |
| Queue full or wait expired | `503 BUSY` with `Retry-After` |
| Login/challenge/upstream throttle | `503 UPSTREAM_LOGIN_REQUIRED`, `UPSTREAM_ACCESS_RESTRICTED`, or `UPSTREAM_RATE_LIMITED` |
| Response/charset invalid, state unreadable, supported media absent | `502 UPSTREAM_BAD_RESPONSE`, `PARSE_FAILED`, or `MEDIA_NOT_FOUND` |
| Original total deadline exhausted | `504 UPSTREAM_TIMEOUT` |
| Unhandled defect | `500 INTERNAL_ERROR` without diagnostic leakage |

Every application and framework error uses `ParseError`. Nginx-generated 413/502/503/504 responses use the same envelope shape and do not replace a more specific application response.

### 5. Good / Base / Bad Cases

- Good: a valid image note returns every ordered body image; a valid video note returns one selected MP4 and a separate cover; a repeated call can return a cache hit with a new request ID.
- Base: optional title, dimensions, codec, quality, duration, size, and URL expiry may be `null`; a video cover may be absent.
- Bad: an ambiguous stream without positive MP4 evidence, an unknown CDN host, a private/multicast DNS answer, a login page with HTTP 200, or a mixed image/video payload must fail closed.

### 6. Tests Required

- Contract: runtime OpenAPI and checked-in `docs/openapi.json` accept the request, success, error, and health examples; unexpected response fields fail.
- URL/transport: rejected hosts and address classes never reach transport; each redirect installs only the current vetted `CurlOpt.RESOLVE`; environment proxies are disabled; DNS and parsing consume the original deadline; a body above 2 MiB aborts.
- Parser/media: string-contained `undefined` is preserved, value-token `undefined` becomes null, the requested note ID is selected, image order is stable, MP4 selection is deterministic, unknown CDN/mixed media fail.
- Service: success-only TTL/LRU, refresh bypass, two active leaders, four total waiters including followers, per-caller metadata, orphan cancellation/await, and cleanup on timeout/cancellation.
- API/logging: authentication variants, 404/405/validation/unexpected errors, no secret-bearing logs, and safe outcome/cache/note/capacity fields.
- Deployment: `docker compose config --quiet`; build/non-root start/health on an available daemon; real probe only with a user-authorized URL and redacted output.

### 7. Wrong vs Correct

Wrong: validate the initial host and let the HTTP client follow redirects or resolve again internally.

```python
await session.get(url, allow_redirects=True)
```

Correct: validate and resolve each hop, bind that result on the same anonymous parse session, and keep redirects disabled.

```python
session.curl_options[CurlOpt.RESOLVE] = resolved_hop.curl_resolve_entries
response = await session.get(
    resolved_hop.url,
    allow_redirects=False,
    content_callback=collector,
)
```

Wrong: let same-key followers join shared work without counting them against admission capacity.

Correct: every waiting caller acquires the shared four-place waiter budget; only the upstream leader consumes one of the two active parse slots. When the final waiter leaves, cancel and await orphaned shared work so permits and in-flight entries are released.
