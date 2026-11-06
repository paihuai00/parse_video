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

def decode_initial_state(html: str) -> dict[str, Any]: ...
def normalize_media_url(value: Any, *, kind: Literal["image", "video"] = "image") -> str | None: ...
def select_note_layout(state: dict[str, Any], note_id: str) -> SelectedNote: ...
def normalize_mobile_note(note_id: str, note: dict[str, Any]) -> InternalNote: ...

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
- Observed Live Photo delivery also uses exact `sns-video-v4.xhscdn.com`, `sns-bak-v1.xhscdn.com`, and `sns-bak-v6.xhscdn.com`. These are individual additions to the shared media allowlist, not permission for arbitrary numbered video/backup shards. Preserve the master/backup query and require the same positive MP4 evidence; unknown hosts remain rejected. Sanitized acquisition and header evidence is recorded in `docs/live-photo-cdn-fix-2026-11-06.md`.
- Video note: empty `images`, exactly one positively identified MP4, and an optional separate cover.
- Every media object uses `verification="not_checked"`; `url_expires_at` stays `null` unless an actual expiry is known.
- Cache expiry describes only this service's result cache and never promises CDN availability.
- The legacy route accepts only Xiaohongshu and retains the 24-hex `note_id` schema and public messages. The unified route auto-detects the platform and accepts either a 24-hex Xiaohongshu ID or an 18-20 digit Douyin ID; both routes build fresh caller metadata from the same internal result.
- A Douyin static image work preserves every upstream image slot in order, assigns one-based indexes, returns `videos=[]` and `cover=null`, and rejects a missing slot or motion-bearing slot instead of returning a partial result.
- A Douyin normal video returns one positively identified MP4 and an optional independent cover. Candidate URL, dimensions, codec, quality, duration, and size come from one selected variant; an exact, independently evidenced CDN host is required.
- A Xiaohongshu mobile image note requires exact `noteData.data.noteData` with outer `hasError is False` and matching `noteId`. `SelectedNote(payload, mobile)` keeps the source layout through adapter normalization; the compatibility `select_note()` still returns the payload. Malformed desktop state cannot be rescued by unrelated shadow mobile data.
- Mobile normalization accepts only positively complete `type="normal"` image slots in original order. Prefer `H5_DTL`, then a direct image URL that is not a known `H5_PRV` preview. Reject missing/malformed slots and preview-only results instead of returning a partial list. A motion-bearing slot must additionally supply a supported MP4 selected with the shared desktop master/backup and metadata rules; attach it as that image's `live_video`, never as a top-level video or a static-only success. Motion without a supported pair remains `UNSUPPORTED_CONTENT`. Mobile normal video remains unsupported; desktop behavior is unchanged.

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

Upstream connections use `curl_cffi==0.13.0`, desktop `chrome136` by default, `trust_env=False`, manual redirects, TLS verification, and independent anonymous sessions per strategy. A validated note response redirecting to exact same-origin `/404` is eligible for one `safari184_ios` fallback on the original full input URL (except the regional URL rule below). A separate typed outcome permits the same bounded fallback when a checked detail returns HTTP 200 with exactly zero body bytes: retry that full validated detail URL, rechecking DNS and binding the established note ID. Do not infer emptiness from Content-Length alone, apply this rule to short-link responses, or treat a nonempty unparseable page as empty. Repeated mobile emptiness is retryable `UPSTREAM_BAD_RESPONSE`, never `PARSE_FAILED` or an empty success. The internal status error remains public `UPSTREAM_BAD_RESPONSE` if no fallback remains; neither `/404` nor unknown `errorCode` proves deletion. Exact same-origin `/login` maps to `UPSTREAM_LOGIN_REQUIRED` without fetching it. Caller URL parsing remains strict and does not accept either status path.

All desktop retries and mobile fallback share two total attempts, the original `Deadline`, admission state and the parse-wide configured redirect limit (default three). The mobile strategy binds to the note ID established by the original long URL or desktop-resolved short link; a mobile redirect cannot substitute another note. Arbitrary paths, credentials, changed status origin, unsafe DNS/redirects, explicit login/challenge/throttle, timeout and generic parse errors do not trigger fallback. Before every connection, validate all resolved addresses as public unicast and replace session-level `CurlOpt.RESOLVE` with the vetted host/port/address set. Do not broaden URL or media hosts to make fallback succeed.

The observed regional detail host `www.rednote.com` is explicitly supported with the same detail-path and per-hop transport checks. A safe same-origin `/404` from that host retries the already validated full regional detail URL in the fresh mobile session, preserving query values and note identity; replaying the short link would exhaust the shared three-redirect budget. Other hosts retain the original-input fallback. Desktop detail redirects also bind to the first established note identity. The regional static-image CDN rotates between observed `sns-i11.rednotecdn.com` and `sns-i27.rednotecdn.com`; accept only its `sns-i<ASCII digits>.rednotecdn.com` shard namespace. Arbitrary subdomains and lookalikes remain rejected. These additions do not enable arbitrary URL fetching or increase attempts, redirects, or time limits.

Douyin acquisition starts a fresh Chromium process and anonymous context for one parse. Chromium uses only a loopback CONNECT proxy; the proxy accepts exact allowlisted HTTPS hosts, resolves them with a shared bounded timeout, rejects any non-public answer, and connects to the vetted IP so Chromium cannot re-resolve externally. Page routing allows only required document/script/XHR/fetch types, caps requests and tunnel bytes, blocks service workers, and uses the original 20-second `Deadline`. Detail responses are keyed by work ID so unrelated recommendations cannot win a race. React Flight scripts are read incrementally with a cumulative browser-side byte cap, including scripts appended after initial DOM load. Cancellation, timeout, browser failure, or proxy shutdown must close and await contexts, processes, tunnels, and handler tasks.

Host allowlisting is exact, never suffix-based. ASCII host case and at most one terminal DNS root dot are canonicalized; repeated trailing dots are rejected. `xhslink.cn` is accepted only for `/o/<token>` where the token is one non-empty ASCII URL-safe segment (`A-Z`, `a-z`, `0-9`, `-`, `_`). Its subdomains, lookalikes, encoded slashes or backslashes, dot traversal, extra path segments, Unicode tokens, overlong URLs, and other paths fail before connection. A short-link redirect receives the same host/path, DNS, address, port, TLS, and redirect-budget checks as the initial URL.

Initial-state extraction balances objects/arrays while respecting double-quoted strings and escapes. Its original source span is at most 2 Mi characters (inclusive), with at most 80 nested containers. Before JSON decoding, a string-aware value scanner converts only value-token `undefined` to null and exact `new Set(array)` to an array, requiring one literal array argument and the closing parenthesis. Constructor tokens permit ASCII JSON whitespace. Preserve array order, values and duplicates: this is data normalization, not execution or Set semantics. Do not change quoted keys/values, support arbitrary constructors/expressions, or globally replace text. Nested supported Set arrays consume the same container-depth budget; decoded values still obey the 200,000-node cap. Unsupported/malformed serialization remains `PARSE_FAILED` without mobile fallback. See the explicitly synthetic fixtures and VPS verification in `docs/rednote-set-state-fix-2026-11-06.md`.

The separately evidenced exact `sns-web-i10.rednotecdn.com` is an additional image-only host. Do not expand this into a numbered `sns-web-i` pattern or a rednotecdn suffix rule. Image URL normalization (the default context) accepts it with the existing HTTP-to-HTTPS, query, credentials, port and scheme rules. All MP4 master/backup candidates explicitly use `kind="video"`, excluding this addition for both normal videos and per-image motion. Legacy shared hosts and the existing `sns-i<ASCII digits>` namespace retain their previous behavior. Synthetic desktop tests combine Set/undefined syntax, requested-ID selection and both `urlDefault`/`WB_DFT` paths through both API routes. Host acceptance does not prove real image readability or establish the VPS Live Photo sample's actual hosts; evidence boundaries are recorded in `docs/rednote-web-image-host-fix-2026-11-06.md`.

The observed regional Live Photo motion hosts `sns-v28.rednotecdn.com`,
`sns-v11.rednotecdn.com`, and `sns-v27.rednotecdn.com` are exact **video-only**
additions. They do not enable images, arbitrary `sns-v` shards, or suffix matching.
Preserve positive MP4 evidence, master/backup priority, HTTPS/query normalization,
and complete per-slot pairing. Regression coverage must combine regional still
and regional motion hosts through both API routes, desktop acquisition and bounded
mobile fallback; a regional page fixture using only domestic motion hosts is
insufficient. A missing fourth motion slot must fail the entire four-image result.
Source-network-dependent regional redirects can persist when DNS addresses are
exchanged and sessions are fresh. Do not turn this compatibility failure into a
global mobile switch, DNS override, generic parse retry or static-only result.
Sanitized diagnosis and release scope are recorded in
`docs/rednote-video-host-fix-2026-11-06.md`.

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
| Mobile Xiaohongshu video or motion without a supported paired MP4 | `422 UNSUPPORTED_CONTENT`; never return a still-only result |
| Mobile missing/malformed image slot or no supported detail image | `502 MEDIA_NOT_FOUND`; never skip the slot |
| Desktop declared/equivalent Live Photo missing a valid still or supported MP4 | `502 MEDIA_NOT_FOUND`; never return partial static-only success |
| Validated detail returns 200 with zero body bytes | One typed mobile fallback within shared budgets; exhausted/mobile emptiness → retryable `502 UPSTREAM_BAD_RESPONSE` |
| Per-key request window exceeded | `429 RATE_LIMITED` with `Retry-After` |
| Queue full or wait expired | `503 BUSY` with `Retry-After` |
| Login/challenge/upstream throttle | `503 UPSTREAM_LOGIN_REQUIRED`, `UPSTREAM_ACCESS_RESTRICTED`, or `UPSTREAM_RATE_LIMITED` |
| Response/charset invalid, state unreadable, supported media absent | `502 UPSTREAM_BAD_RESPONSE`, `PARSE_FAILED`, or `MEDIA_NOT_FOUND` |
| Exact safe note-to-`/404` redirect with no remaining fallback, including unknown upstream error codes | `502 UPSTREAM_BAD_RESPONSE`, not evidence of `NOTE_NOT_FOUND` |
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
- Mobile acquisition: test full short-link→detail→same-origin `/404`→fresh iOS strategy→matched mobile note; exact status origin/credentials/ports/paths, no fetch of status pages, no fallback on unsafe inputs, and conservative repeated-status errors. Two-attempt and redirect limits span both strategies and retries; verify remaining deadline, mobile target-ID binding and cancellation cleanup.
- Mobile media: explicit `hasError=false`, ID mismatch and layout ambiguity, all image slots/types/order/dimensions, `H5_DTL` priority, normalized preview equivalence, unknown hosts, malformed/nonempty streams and motion markers. Verify full ParseService/API flows for both routes, shared cache with fresh caller metadata and failure without partial images. Use synthetic fixtures; live identity/media evidence stays redacted.
- Parser/media: string-contained `undefined` is preserved, value-token `undefined` becomes null, the requested note ID is selected, image order and Live Photo ownership are stable, normal and per-image streams share deterministic MP4 selection, empty streams stay ordinary, missing Live Photo MP4 and unknown CDN/mixed media fail.
- Service: success-only TTL/LRU, refresh bypass, two active leaders, four total waiters including followers, per-caller metadata, orphan cancellation/await, and cleanup on timeout/cancellation.
- Douyin browser: exact work-ID response binding, incrementally bounded Flight scripts, exact egress hosts, private/mixed DNS rejection, pinned CONNECT targets, request/tunnel/state limits, fresh contexts, browser startup failure isolation, total-deadline cancellation, handler/process cleanup, and motion-image rejection.
- API/logging: authentication variants, 404/405/validation/unexpected errors, no secret-bearing logs, and safe outcome/cache/note/capacity fields.
- Deployment: `docker compose config --quiet`; build/non-root start/health on an available daemon; a read-only root must pair bounded writable `/tmp` and `/home/app` tmpfs mounts with the image's HOME/XDG paths, and `/home/app` remains owned by runtime UID/GID 10001 with mode 0700. Real probes use only user-authorized URLs and redacted output. Header checks select at most two representative files and, when Live Photos exist, cover one still plus one nested motion MP4.

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

Wrong: pass a mobile payload through desktop normalization or catch every `INVALID_URL`/`PARSE_FAILED` to try another client. This can skip image slots, use previews, retry unsafe destinations or hide unrelated failures.

Correct: retain exact layout and normalize through its validated branch; only typed safe note-status redirects and checked 200 zero-byte detail responses can select the mobile strategy. Generic parse errors never select it.

```python
selected = select_note_layout(state, page.note_id)
normalize = normalize_mobile_note if selected.mobile else normalize_note
note = normalize(page.note_id, selected.payload)
```

Wrong: annotate a Pydantic wrap serializer as returning a generic `dict` without checking generated schema. Pydantic may use that annotation as the serialization schema and FastAPI can collapse the model to a bare object.

Correct: keep the serializer's model schema intact and assert at runtime that `ImageMedia` exposes optional structured `live_video` plus `additionalProperties=false`; separately assert ordinary serialization omits the absent field.
