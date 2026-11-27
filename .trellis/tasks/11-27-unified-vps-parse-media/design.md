# Unified VPS parsing and media delivery design

## Status and ownership

Final planning artifact; not implemented or deployed. This repository owns provider HTTP calls, provider adaptation, parse dispatch, media publication and streaming. The paired client task owns the single-request UI integration and saving lifecycle. No Git writes are authorized.

## Routing

One client-facing parse route remains `POST /api/v1/parse`, authenticated using the existing configured key contract. Keep the existing `{url, refresh}` request: clients extract a URL from share text; the server independently validates it. Do not add client-selected provider IDs.

| Platform | Server strategy |
| --- | --- |
| XHS | Existing bounded anonymous XHS acquisition and layout normalization |
| Douyin | Fixed providers: bugpk `/douyin`, bugpk `/dyjx`, ifphp `/svparse`, bugpk `/short_videos` |
| Bilibili | Fixed bugpk `/bilibili`, then bugpk `/short_videos` |
| Generic | Fixed bugpk `/short_videos`, preserving current generic behavior without promising additional platforms |

Provider endpoint origins are configured/fixed by the server, never caller-controlled. Platform source validation, provider-service destination validation and returned-media destination validation are separate boundaries. For generic inputs, accept only bounded valid public HTTP(S) URLs with no credentials/private targets; forward the input to the fixed provider instead of fetching arbitrary pages directly. Preserve strict native XHS rules.

The native Douyin adapter remains isolated code, not an unapproved fallback. The new route uses migrated third-party Douyin acquisition. Do not silently change watermark behavior or label upstream output watermark-free.

## Provider normalization and scheduling

Reuse `ParseService` admission, rate limiting, success cache and request coalescing. Extend platform keys to include Bilibili/generic, and namespace cache identities by platform and strategy version so native/third-party results cannot collide.

Introduce fixed provider clients and source-specific normalizers under `app/parser/providers/` (or the narrowest existing equivalent). Port JSON/status validation from current client and ifphp service; do not copy browser-native Douyin restrictions onto third-party results.

- Each provider returns one immutable normalized result, not its original JSON.
- Keep image slot order and aligned motion videos. Inspect dynamic metadata before using a generic source; never silently publish a motion-bearing item as still-only because an adapter ignored a field.
- Optional dimensions/codec/size remain unknown unless supported by the chosen rendition. An ambiguous URL must not be falsely labeled MP4; use positive metadata/path evidence or a bounded, validated media-header check.
- Preserve title/description/author-name metadata where present. Avatar image URLs, if exposed, use the same media proxy. Do not expose raw provider JSON or leak its original CDN URLs through nested data.
- Existing real work IDs are preserved and identity mismatches rejected. Do not fabricate an upstream ID from a short token or random value. For unified third-party/generic results without a verifiable ID, make `note_id` explicitly nullable in the new unified contract and keep cache identity separate. The legacy XHS contract keeps its required 24-hex ID. Inspect ID-dependent callers before changing internal typing.
- Add explicit `data.platform` for unified results, mapped to existing client names `xhs`, `douyin`, `bilibili`, `unknown`; do not infer all unified results to be XHS.
- Any retained optional metadata must be documented in the unified schema; do not introduce audio fetching/transcoding as a side effect of music metadata.

Use one monotonic total deadline for admission, provider calls, retries and response checks. Preserve default provider order. Do not blindly reproduce the client's two attempts per provider inside another client retry loop. Retry only eligible transient failures within remaining budget; bounded provider fallback handles source-specific failures. Authentication/input/security failures are terminal. Media publication failure occurs after parsing and does not restart provider selection. Exhaustion returns stable generic server error semantics without upstream bodies or secrets.

## Response publication

Keep original media addresses in cached internal results. On every response, register all image/video/motion/cover/avatar URLs atomically and use their VPS URLs when constructing the public response. Keep response mapping pure: a service supplies published URLs; data models do not own global network state.

The normal workflow has no separate client ticket-creation call. Legacy/raw history is refreshed by calling the same parse route with its stored share URL.

Use a validated configured HTTPS public origin, never request Host. Every exposed image/video URL must match it exactly. Credential records store the complete upstream URL, type, platform, expiry and associated identity. Preserve path/query strings, percent escapes, plus signs, duplicate keys and order.

Use unguessable resource IDs and server-side signing. Bind signatures to ID/expiry and record identity; verify in constant time. Credentials are reusable until expiry, scoped to registered media and unsuitable for arbitrary caller URLs. Keep count and total metadata bytes bounded; remove expired entries only. Reject new issuance with `503 MEDIA_TICKET_CAPACITY` rather than evicting unexpired entries. Batch registration either commits all records or none. Release cancelled/unpublished batches so failed response construction cannot leak capacity.

Set `url_expires_at` to the actual credential expiry. Keep `verification=not_checked`. Parse-cache expiry, credential expiry and unknown upstream expiry are different. Restart/key rotation may invalidate credentials and trigger bounded reparse. Single worker is required by process-local state.

## Media retrieval and transport

Add `GET` and `HEAD /api/v1/media/{resource_id}?exp=...&sig=...`. URL credentials authorize image components and previews without custom headers. Do not implement a public arbitrary-URL proxy or a normal-path ticket POST.

Transport requirements:

1. Validate scheme, host, media type, port, credentials and all DNS answers. Use evidenced exact hosts/narrow namespaces; do not broaden page allowlists or trust suffix-containing names.
2. Connect to vetted public IPs while preserving original TLS SNI/certificate checks. Apply the same controls on every bounded manual redirect.
3. Keep the original source URL representation. No arbitrary forwarded client Cookie/Authorization/Host/Referer headers; configure only evidenced platform needs.
4. Before starting a response, validate upstream status, content type, limited file-header evidence and length limits. HTML challenges are not images/videos.
5. Stream raw bytes with bounded buffering and backpressure. Never read complete media into memory/disk. Close upstream responses and release admission on normal completion, cancellation, timeout and partial failure.
6. Use separate download connection/concurrency/queue/time/byte budgets. Do not consume page-parse admission for an entire video transfer.
7. Send trusted Content-Type and byte-correct Content-Length only. Avoid transparent decoding/length mismatch. Do not pass upstream cookies or redirects to clients.
8. GET initially guarantees full-file 200. Ignore client Range explicitly and return a complete 200, never a partial 206 as a complete save. HEAD returns no body and does not make up length. If device preview requires Range, full 206/416 correctness becomes a release gate.

The first implementation checkpoint proves a chosen transport has pinned connections, signature preservation, backpressure and deterministic cancellation. Prefer existing primitives; if HTTPX is selected, promote its exact dependency to runtime and implement the required safe connection layer. Default library behavior alone is not the safety proof. Existing curl streaming must not be assumed memory-bounded without evidence.

## Errors and observability

Before streaming, use stable HTTP status plus `X-Media-Error-Code` and `X-Request-ID`; include the existing JSON envelope as auxiliary detail. Client recovery must not require reading JSON saved as a temporary download file.

| Status | Code family | Meaning |
| --- | --- | --- |
| 400/403 | MEDIA_SOURCE_INVALID / MEDIA_SOURCE_FORBIDDEN / MEDIA_TICKET_INVALID | Terminal validation/security error |
| 410 | MEDIA_TICKET_EXPIRED / MEDIA_TICKET_GONE | Eligible for one parse refresh |
| 429 | MEDIA_RATE_LIMITED | Bounded wait with Retry-After |
| 502 | MEDIA_UPSTREAM_REJECTED / MEDIA_UPSTREAM_BAD_RESPONSE | Upstream failure; only explicit recoverable classification permits refresh |
| 503 | MEDIA_BUSY / MEDIA_TICKET_CAPACITY | Admission/issuance overload; not a provider-switch signal |
| 504 | MEDIA_UPSTREAM_TIMEOUT | Bounded retry/failure |

After response bytes start, errors interrupt the stream; do not append JSON. Record actual transfer completion, bytes, request ID and cancellation/failure code independently of header-ready timing. Redact IDs used as capabilities, full source/proxy URLs, signatures, credentials and upstream bodies across application, Nginx and client logs.

## Deployment and compatibility

Update `main.py`, `config.py`, `.env.example`, runtime locks if needed, Nginx examples, compose environment wiring if required, API examples, OpenAPI, README and service-contract specs. Download routes disable proxy buffering/cache/temp-file spill and propagate disconnects. Provider and media route errors use generic wording, not XHS-only errors. Preserve unrelated Node reporting/email services; migrate ifphp acquisition to Python using its server-side environment key, and retire only its parsing route after compatibility review.

Use a staged media-publication switch for rollout: deploy new server routes first, verify candidate behavior, release the single-endpoint client, then enable direct proxy URL publication. The transitional client must reject/raw-refresh any CDN output before saving; it must never direct-download it. Keep already-issued media routes available during rollback. Do not roll back to a server version incapable of serving new clients without a compatible stop/maintenance strategy. Deployment and release remain separately authorized.

## Evidence and deferred work

Offline source/fixture evidence establishes the current call chains; no actual VPS reachability or complete media transfer has been verified. Provider/CDN samples, complete-file checks and domain-enabled real-device checks are release gates. No persistent cache, database, Redis, transcoding, native Live Photo creation, independent provider-learning system or default native-Douyin fallback is included.
