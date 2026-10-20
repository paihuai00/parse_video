# Service Contract

## Scenario: Parse one Xiaohongshu or Douyin work into temporary media direct URLs

### 1. Scope / Trigger

Use this contract whenever code changes the HTTP API, platform detection, upstream URL/transport policy, note parsing, media normalization, process-local resource controls, browser acquisition, environment wiring, or deployment proxy. These layers form one observable contract: the caller submits one work URL, the service returns JSON direct URLs, and the caller downloads from the upstream CDN.

The service never proxies, stores, bundles, transcodes, or streams media files. Xiaohongshu per-image Live Photo MP4 discovery is supported. Douyin supports normal video and complete ordered static image works; a Douyin image slot with a motion video fails as `UNSUPPORTED_CONTENT` instead of losing the motion part. Live broadcasts, unrelated mixed top-level media, login sessions, batch input, and multiple workers remain outside v1.

### 2. Signatures

```http
POST /api/v1/xiaohongshu/parse
Content-Type: application/json
X-API-Key: <configured XHS_API_KEY>

{"url":"https://www.xiaohongshu.com/explore/<24-hex-id>?xsec_token=...","refresh":false}
```

```http
POST /api/v1/parse
Content-Type: application/json
X-API-Key: <configured XHS_API_KEY>

{"url":"https://v.douyin.com/<token>/","refresh":false}
```

```http
GET /healthz
```

Python ownership signatures:

```python
async def parse_note(body: ParseRequest, api_key: str, request: Request) -> ParseSuccess: ...
async def parse_media(body: ParseRequest, api_key: str, request: Request) -> UnifiedParseSuccess: ...

class ParseService:
    async def parse(
        self,
        raw_url: str,
        refresh: bool,
        api_key: str,
        platform: Literal["xiaohongshu", "douyin"] = "xiaohongshu",
    ) -> ServiceResult: ...

class XiaohongshuClient:
    async def fetch(self, raw_url: str, deadline: Deadline) -> PageResponse: ...

class DouyinBrowser:
    async def fetch_detail(
        self, raw_url: str, deadline: Deadline
    ) -> tuple[str, dict[str, Any]]: ...

class ImageMedia(StrictModel):
    # Omitted from serialized ordinary-image items when None.
    live_video: VideoMedia | None = None
```

### 3. Contracts

Request fields:

| Field | Type | Contract |
| --- | --- | --- |
| `url` | HTTP(S) URL | At most 4096 characters; exact Xiaohongshu detail/mobile/short-link forms or exact Douyin `v.douyin.com/<token>`, `www.douyin.com/{video,note}/<18-20-digit-id>`, and `www.iesdouyin.com/share/{video,note}/<id>` forms; checked redirects preserve access-significant query values and may not switch platforms |
| `refresh` | boolean | Defaults to `false`; skips result cache but not authentication, rate, admission, concurrency, or deadline controls |

Success response invariants:

- `success=true`, `error=null`, and a fresh `meta.request_id` for every caller.
- Image note: ordered non-empty `images`, empty top-level `videos`, `cover=null`. Each image may contain one nested `live_video`; ordinary images omit the field entirely.
- Live Photo: keep the still image at its original image position and attach exactly one positively identified MP4 to that image. Select motion metadata only from the video candidate; never copy still-image width/height onto it.
- Video note: empty `images`, exactly one positively identified MP4, and an optional separate cover.
- Every media object uses `verification="not_checked"`; `url_expires_at` stays `null` unless an actual expiry is known.
- Cache expiry describes only this service's result cache and never promises CDN availability.
- The legacy route accepts only Xiaohongshu and retains the 24-hex `note_id` schema and public messages. The unified route auto-detects the platform and accepts either a 24-hex Xiaohongshu ID or an 18-20 digit Douyin ID; both routes build fresh caller metadata from the same internal result.
- A Douyin static image work preserves every upstream image slot in order, assigns one-based indexes, returns `videos=[]` and `cover=null`, and rejects a missing slot or motion-bearing slot instead of returning a partial result.
- A Douyin normal video returns one positively identified MP4 and an optional independent cover. Candidate URL, dimensions, codec, quality, duration, and size come from one selected variant; an exact, independently evidenced CDN host is required.

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
| `XHS_DOUYIN_BROWSER_CONCURRENCY` | `1`; also consumes shared service admission |
| `XHS_DOUYIN_BROWSER_MAX_REQUESTS` / `XHS_DOUYIN_BROWSER_MAX_BYTES` | `500` / `33554432` per parse |
| `XHS_DOUYIN_STATE_MAX_BYTES` | `2097152` cumulative detail/Flight state |
| `XHS_DOUYIN_BROWSER_CHANNEL` | Optional Playwright channel override; container uses bundled `chromium` |

Upstream connections use `curl_cffi==0.13.0`, explicit `chrome136`, `trust_env=False`, manual redirects, TLS verification, and a fresh anonymous session per parse. Before every hop, validate all resolved addresses as public unicast and replace the session-level `CurlOpt.RESOLVE` entry with the vetted host/port/address set.

Douyin acquisition starts a fresh Chromium process and anonymous context for one parse. Chromium uses only a loopback CONNECT proxy; the proxy accepts exact allowlisted HTTPS hosts, resolves them with a shared bounded timeout, rejects any non-public answer, and connects to the vetted IP so Chromium cannot re-resolve externally. Page routing allows only required document/script/XHR/fetch types, caps requests and tunnel bytes, blocks service workers, and uses the original 20-second `Deadline`. Detail responses are keyed by work ID so unrelated recommendations cannot win a race. React Flight scripts are read incrementally with a cumulative browser-side byte cap, including scripts appended after initial DOM load. Cancellation, timeout, browser failure, or proxy shutdown must close and await contexts, processes, tunnels, and handler tasks.

Host allowlisting is exact, never suffix-based. ASCII host case and at most one terminal DNS root dot are canonicalized; repeated trailing dots are rejected. `xhslink.cn` is accepted only for `/o/<token>` where the token is one non-empty ASCII URL-safe segment (`A-Z`, `a-z`, `0-9`, `-`, `_`). Its subdomains, lookalikes, encoded slashes or backslashes, dot traversal, extra path segments, Unicode tokens, overlong URLs, and other paths fail before connection. A short-link redirect receives the same host/path, DNS, address, port, TLS, and redirect-budget checks as the initial URL.

### 4. Validation & Error Matrix

| Condition | HTTP / code |
| --- | --- |
| Malformed JSON/body or forbidden field | `400 INVALID_REQUEST` |
| Unsupported platform/URL, credentials/IP/whitespace/control characters, unsafe DNS or redirect | `400 INVALID_URL` |
| Missing, wrong, or non-ASCII API key | `401 UNAUTHORIZED` |
| Explicit missing note evidence | `404 NOTE_NOT_FOUND` |
| Unknown route / wrong method | `404 ROUTE_NOT_FOUND` / `405 METHOD_NOT_ALLOWED` |
| Body over the HTTP input limit | `413 INPUT_TOO_LARGE` |
| Live broadcast, unsupported work type, unrelated mixed media, or Douyin motion image | `422 UNSUPPORTED_CONTENT` |
| Declared/equivalent Live Photo missing a valid still or supported MP4 | `502 MEDIA_NOT_FOUND`; never return partial static-only success |
| Per-key request window exceeded | `429 RATE_LIMITED` with `Retry-After` |
| Queue full or wait expired | `503 BUSY` with `Retry-After` |
| Login/challenge/upstream throttle | `503 UPSTREAM_LOGIN_REQUIRED`, `UPSTREAM_ACCESS_RESTRICTED`, or `UPSTREAM_RATE_LIMITED` |
| Response/charset invalid, state unreadable, supported media absent | `502 UPSTREAM_BAD_RESPONSE`, `PARSE_FAILED`, or `MEDIA_NOT_FOUND` |
| Original total deadline exhausted | `504 UPSTREAM_TIMEOUT` |
| Unhandled defect | `500 INTERNAL_ERROR` without diagnostic leakage |

Every application and framework error uses `ParseError`. Nginx-generated 413/502/503/504 responses use the same envelope shape and do not replace a more specific application response.

### 5. Good / Base / Bad Cases

- Good: either supported platform returns every ordered body image or one selected normal-video MP4; Xiaohongshu Live Photo MP4 stays nested on its owning image; a repeated call can return a cache hit with a new request ID; the same Xiaohongshu URL can share internal work across both routes without sharing caller metadata.
- Base: ordinary image items omit `live_video`; optional title, dimensions, codec, quality, duration, size, URL expiry, and normal-video cover may be `null`. `verification` remains `not_checked` because runtime parsing does not download media.
- Bad: a declared/equivalent Live Photo without positive MP4 evidence, a Douyin image slot carrying motion, an unknown CDN host, a private/multicast DNS answer, a login/challenge page with HTTP 200, an unrelated detail response, or partial image slots must fail closed.

### 6. Tests Required

- Contract: runtime OpenAPI and checked-in `docs/openapi.json` accept the request, ordinary-image, Live Photo, normal-video, error, and health examples; `ImageMedia.live_video` remains a structured optional field with `additionalProperties=false`; unexpected response fields fail.
- Unified contract: both routes use the same request and envelope; the legacy route keeps 24-hex IDs and Xiaohongshu wording; the unified route accepts decimal Douyin IDs and neutral wording; cross-route Xiaohongshu work shares cache/admission/rate budgets while platform cache identities stay isolated.
- URL/transport: rejected hosts and address classes never reach transport; exact `.cn` mobile paths succeed while `.cn` lookalikes/other paths and unsafe redirects fail before connection; each redirect installs only the current vetted `CurlOpt.RESOLVE`; environment proxies are disabled; DNS and parsing consume the original deadline; a body above 2 MiB aborts.
- Parser/media: string-contained `undefined` is preserved, value-token `undefined` becomes null, the requested note ID is selected, image order and Live Photo ownership are stable, normal and per-image streams share deterministic MP4 selection, empty streams stay ordinary, missing Live Photo MP4 and unknown CDN/mixed media fail.
- Service: success-only TTL/LRU, refresh bypass, two active leaders, four total waiters including followers, per-caller metadata, orphan cancellation/await, and cleanup on timeout/cancellation.
- Douyin browser: exact work-ID response binding, incrementally bounded Flight scripts, exact egress hosts, private/mixed DNS rejection, pinned CONNECT targets, request/tunnel/state limits, fresh contexts, browser startup failure isolation, total-deadline cancellation, handler/process cleanup, and motion-image rejection.
- API/logging: authentication variants, 404/405/validation/unexpected errors, no secret-bearing logs, and safe outcome/cache/note/capacity fields.
- Deployment: `docker compose config --quiet`; build/non-root start/health on an available daemon; real probe only with a user-authorized URL and redacted output. Header checks select at most two representative files and, when Live Photos exist, cover one still plus one nested motion MP4.

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

Wrong: accept the first `/aweme/detail` response or call `all_text_contents()` on every page script before checking size. Recommendation traffic can select the wrong work, and size validation happens after unbounded transfer.

Correct: key captured detail responses by the target work ID, ignore unrelated details, and read Flight scripts one at a time with cumulative count/byte bounds in the browser before transferring them to Python.

Wrong: flatten Live Photo clips into top-level `videos` or return only their still images. Flattening loses the owning image position; static-only success silently drops supported motion content.

Correct: keep image-note `videos=[]`, preserve the ordered still, and attach the selected clip as that image's optional `live_video`. If a marked Live Photo cannot produce both parts, return `MEDIA_NOT_FOUND`.

Wrong: annotate a Pydantic wrap serializer as returning a generic `dict` without checking generated schema. Pydantic may use that annotation as the serialization schema and FastAPI can collapse the model to a bare object.

Correct: keep the serializer's model schema intact and assert at runtime that `ImageMedia` exposes optional structured `live_video` plus `additionalProperties=false`; separately assert ordinary serialization omits the absent field.
