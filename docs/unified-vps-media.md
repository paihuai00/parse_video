# Unified VPS parsing and media delivery

## Current implementation and evidence

`POST /api/v1/parse` accepts `{url, refresh}` with `X-API-Key`. Dispatch is server-owned:
XHS self-acquisition; Douyin bugpk `/douyin` → `/dyjx` → ifphp `/svparse` → bugpk
`/short_videos`; Bilibili bugpk `/bilibili` → `/short_videos`; unknown public HTTP(S)
share URLs go only to fixed bugpk `/short_videos`. Generic dispatch is not a promise
of additional platform coverage. The native Douyin adapter remains isolated and
is not a new fallback. XHS page allowlists are unchanged.

There is no client provider preference, shared provider-learning system or ticket
POST. Only eligible transient provider failures retry (at most two attempts each),
within the original parse deadline/admission budget. Missing `IFPHP_API_KEY` skips
that provider. Media publication errors never restart the provider chain.

This is offline-tested code, not a deployment/reachability or success-rate claim.
Prior native-Douyin sample evidence does not verify the migrated third-party chain.

## Public data and publication

Unified `data.platform` is `xhs|douyin|bilibili|unknown`. The image/video union stays;
`note_id` is nullable when no explicit provider identity is available (no fabricated
IDs). Legacy XHS IDs remain required 24-hex strings. Preserve title, description
and author name. Avatars from the existing platform image policy are included in the
same atomic media publication; unknown/invalid optional avatars are omitted without
failing the work. No raw provider payload, music URL or nested CDN URL is exposed;
audio retrieval is outside this implementation.
Optional rendition dimensions, codec and duration stay unknown unless evidenced.

When `MEDIA_PUBLICATION_ENABLED=true`, both parse routes directly rewrite
`images[].url`, `images[].live_video.url`, `videos[].url` and `cover.url` onto configured
`MEDIA_PUBLIC_ORIGIN`. Image/motion slots stay paired. Ambiguous video URLs require
a bounded MP4 header check; unknown motion layouts fail rather than lose motion.

Original signed CDN strings remain in immutable `InternalNote`/the parse cache.
Every response, including a cache hit, atomically registers a new work-sized batch.
No awaits occur inside the capacity check/commit. Counts and metadata bytes are
bounded; only expired records are reclaimed, never unexpired ones. Capacity exhaustion
returns `503 MEDIA_TICKET_CAPACITY`; partially constructed/unpublished batches are
revoked. The media map outlives parse cache entries independently.

`url_expires_at` is the credential expiry; `meta.cache.expires_at` is parse-cache
expiry. Neither extends the unknown CDN expiry. `verification=not_checked` remains.
Credentials can be reused for thumbnails, previews and saving. Restart/key rotation
invalidates old links. Reparse once with saved share URL and `refresh:true`; do not
send the old proxy URL or its CDN source to the parse endpoint.

## Retrieval and error contract

`GET|HEAD /api/v1/media/{resource_id}?exp=...&sig=...` requires URL credentials, not
an API Key. HMAC binds the unguessable ID, expiry, source identity, platform and type.
Responses never redirect the client to CDN. Each upstream hop validates the URL,
media-host/type policy and all DNS answers. A fresh httpcore pool connects to those
vetted public numeric IPs while preserving original Host/TLS SNI/certificate checks.
Other vetted addresses are attempted within the same connect budget. Environment
proxies, automatic redirects and caller-supplied upstream headers are disabled.

httpcore's original request target preserves signatures (path, percent escapes,
plus signs, duplicate queries, empty queries). Relative redirects retain explicit
empty query semantics. The original source is never reconstructed from the public
resource path. httpcore 1.0.8 is pinned as a runtime dependency.

GET returns a complete `200` file. Client Range is deliberately ignored; no partial
206 is saved as complete. HEAD requests the same upstream metadata with no body and
does not invent Content-Length. Upstream HEAD rejection fails explicitly; actual
device preview may require a future correct Range/206/416 implementation before release.

Raw pull-based HTTP/1 reads have no background producer/queue or full-file buffer.
Preflight checks status, identity encoding, declared type/length and limited file
magic. AVIF/HEIF are not MP4. Chunked JPEG/PNG/GIF/WebP and MP4 are supported;
other image/video formats fail explicitly. Length is only passed when byte-correct.
Oversized/truncated/failed transfers abort, never append JSON to a media body.

Downloads have separate admission, queue, rate, idle/total-time and byte budgets.
A single disconnect watcher covers queueing, DNS/connect, header/magic preflight and
the complete transfer. Disconnect/timeout cancels and awaits cleanup before releasing
the slot. Credentials are checked when the request is admitted, not on every chunk.

Before media headers start, failures use the normal JSON envelope plus
`X-Media-Error-Code`, `X-Request-ID` and, when relevant, `Retry-After`:

| Status | Codes / client action |
| --- | --- |
| 400 | `MEDIA_SOURCE_INVALID`: stop |
| 403 | `MEDIA_SOURCE_FORBIDDEN`, `MEDIA_TICKET_INVALID`: stop |
| 410 | `MEDIA_TICKET_EXPIRED`, `MEDIA_TICKET_GONE`: at most one reparse |
| 429 | `MEDIA_RATE_LIMITED`: bounded wait |
| 502 | `MEDIA_UPSTREAM_REJECTED`, `MEDIA_UPSTREAM_BAD_RESPONSE`: stop; no automatic reparse classification |
| 503 | `MEDIA_BUSY`, `MEDIA_TICKET_CAPACITY`: bounded wait; never provider fallback |
| 504 | `MEDIA_UPSTREAM_TIMEOUT`: bounded retry/failure |

DNS transient failure is 502, unsafe DNS is 403. `wx.downloadFile` callers use the
status plus `onHeadersReceived`, not JSON saved in a temporary file. Streaming
completion logs record request ID, sent bytes and outcome, without capability ID,
URL, source signature, credentials or provider response. Nginx's safe access format
omits URI/query entirely and its media error log is suppressed (it can contain URLs).

## Configuration and rollout (separate authorization)

`.env.example` lists application defaults, not WeChat platform constraints:
publication off; 30-minute tickets; 2048 records/2 MiB metadata; two active downloads,
four waiters/two-second queue; 480-second total and 30-second idle download limit;
200 MiB application byte ceiling; 120 media requests per minute per observed client IP;
1 MiB provider JSON. Tune only through validated configuration and release evidence.
Use a separate random server-only `MEDIA_SIGNING_KEY` of at least 32 bytes and a
trusted HTTPS origin. Do not use the public client API key as signing secret.

Keep one worker. Compose's existing env_file injects the new variables; no Redis,
database, writable media directory, permanent cache or transcoding is required.
Retain existing container sandbox/root restrictions; do not upgrade worker count.

1. Deploy new routes with publication off; verify candidate response bytes and error
   headers using authorized samples. No deployment was executed by implementation.
2. Add the Nginx media location, no buffering/cache/temp spill, disconnect propagation
   and safe logs. Set timeouts consistently; read timeout is idle, not total duration.
   Trust forwarded client IPs only from the controlled ingress; otherwise media rate
   limits may be shared by all clients. Inspect all outer proxy/CDN logs too.
3. Configure WeChat request and downloadFile legal domains for the configured origin.
4. Use an experience/test client against the candidate environment to verify all four
   platform flows with publication enabled: still/motion pairing, safe avatars/covers,
   image preview, complete video saves, cancellations and parsing under download traffic.
5. Before formally releasing the new client, configure the production origin/signing key,
   enable publication there, and pass authorized media/domain acceptance checks. Only
   then release the single-endpoint client. Never publish it against a production API
   that still returns CDN URLs: the new client correctly refuses those URLs. Experience
   builds may precede production enablement, but are not a formal-client rollout.

Rollback first disables *new* publication while preserving existing media routes,
signing key and records until expiry. Do not revert to a version missing media routes
or enable client direct-CDN fallback. Restart loses mappings and requires one reparse.
The Node error-report/mail service remains untouched; retire its old ifphp parse
route only after old-client compatibility review.

Media namespaces are intentionally bounded: existing XHS host/type rules; Douyin
numbered signed-image/CDN-video namespaces plus exact playback entrypoints; Bilibili
video CDN subdomains and exact `i0/i1/i2.hdslb.com` image hosts. These are controlled
compatibility rules, not evidence every hostname/rendition is reachable from the VPS.
Unsupported CDN families fail closed and require evidenced additions, not arbitrary
domain suffix expansion.
