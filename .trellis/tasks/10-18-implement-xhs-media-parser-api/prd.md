# Implement Xiaohongshu media parser API

## Goal

Turn the existing design package into a runnable, locally verifiable, and Docker-deliverable v1 service. The service accepts one supported Xiaohongshu share URL and returns structured JSON containing ordered image URLs with an optional paired Live Photo MP4 per image, or one selected main-video MP4 plus its cover. Implementation and project documentation must remain synchronized so the repository describes behavior that actually exists.

## Background and Confirmed Facts

- The repository currently contains design documents, an OpenAPI 3.1 contract, examples, and a redacted anonymous-access evidence record. It contains no application source, tests, dependency lock, or container files.
- `docs/implementation-plan.md` marks P0 complete and P1-P5 unimplemented.
- Anonymous page access was previously demonstrated with Python 3.12, `curl_cffi==0.13.0`, explicit `chrome136` impersonation, a fresh anonymous session, same-site Referer, and TLS verification.
- The v1 runtime is one FastAPI/Uvicorn worker with bounded in-memory state. It does not require a database, Redis, a browser process, or a task queue.
- The repository does not contain sanitized HTML fixtures or usable share tokens. Real-page and VPS verification therefore require deployment-time inputs and must not be claimed from offline tests.
- The workspace is the root of the intended Git repository and tracks `origin/main`. The task changes remain uncommitted, and the commit/finish phase must wait for the remaining acceptance work.
- The user confirmed that v1 returns temporary media direct URLs in JSON and the caller downloads them from the upstream CDN. The API does not proxy, persist, bundle, or stream media files.

## Requirements

### R1. Documentation is an implementation contract

- Treat `README.md`, `docs/technical-design.md`, `docs/openapi.json`, `docs/examples/`, `docs/implementation-plan.md`, and `docs/deployment.md` as the starting contract.
- Update those documents when implementation reveals a necessary change; do not leave planned behavior described as implemented or implemented behavior undocumented.
- Keep evidence and examples free of usable share tokens, API keys, cookies, signed media URLs, and full upstream page bodies.

### R2. Safe URL handling and upstream fetching

- Accept one HTTP(S) URL on exactly `www.xiaohongshu.com`, `xiaohongshu.com`, `xhslink.com`, or the observed mobile-copy host `xhslink.cn`. On `xhslink.cn`, accept only `/o/<non-empty URL-safe token>`; still require a supported exact detail host/path after short-link resolution.
- Reject credentials in URLs, IP literals, unexpected ports, private or otherwise non-public address targets, malformed URLs, unsupported hosts, and unsupported paths before making an upstream request.
- Handle at most three redirects manually. Validate and resolve every hop, pin the validated address set to the actual connection, preserve the required share query parameters, and keep TLS hostname verification enabled.
- Use a new anonymous cookie session for each upstream parse, `curl_cffi==0.13.0`, explicit `chrome136`, the documented headers, cancellation support, a five-second connect limit, and a twenty-second end-to-end budget.
- Stop reading decompressed HTML after 2 MiB. Retry at most once and only for the documented temporary transport/upstream failures within the original total deadline.

### R3. Structured page and media parsing

- Extract the bounded `window.__INITIAL_STATE__` assignment without executing JavaScript. Convert only value-token `undefined` outside strings to JSON `null`.
- Select `note.noteDetailMap[requested_note_id].note`; never substitute the first or last map entry.
- Distinguish normal notes from login pages, verification challenges, platform throttling, clearly missing notes, unsupported live broadcasts/unknown mixed content, and unknown page structures.
- Preserve image order and follow the documented image candidate preference. For each Live Photo image, preserve the still image and attach exactly one selected motion MP4 to that same image item. Keep a normal video note's cover separate from body images.
- Select playable MP4s using the documented codec, resolution, and bitrate ordering. Fail closed instead of returning a partial static-only result when a declared Live Photo has no supported MP4, and fail when a normal video note has no supported main video.
- Preserve media URL query strings, validate media URL format and allowed CDN hosts, and return unknown metadata as `null` rather than guessing.

### R4. JSON API and error contract

- Implement `POST /api/v1/xiaohongshu/parse` and unauthenticated `GET /healthz`.
- Require non-empty `XHS_API_KEY` at production startup and validate `X-API-Key` on parse requests.
- Reject unknown request fields and any attempt to pass account cookies through the API.
- Validate input and output with Pydantic and keep generated behavior compatible with `docs/openapi.json` and the checked-in examples.
- Keep the existing top-level image/video note shape: image notes retain ordered `images` and `videos=[]`, while an image entry may add an optional nullable `live_video`. Ordinary image responses should omit that new field when it is absent; top-level `videos` remains reserved for a normal video note's single main MP4.
- Return the documented JSON envelope for success, application errors, validation errors, framework 404/405, and unexpected exceptions.
- Generate a fresh request ID for every caller. Do not expose stack traces, credentials, share tokens, signed media URLs, or page bodies in responses or logs.
- Keep `verification=not_checked`; cache expiry must never be presented as media URL expiry.

### R5. Bounded single-process operation

- Apply API-key rate limiting before cache lookup: at most 20 requests per rolling 60 seconds per key.
- Cache only successful parsed results for 120 seconds with a maximum of 256 entries. The cache key must include a digest of access-significant URL parameters.
- `refresh=true` bypasses cached results but still obeys authentication, rate, queue, concurrency, and deadline limits.
- Coalesce concurrent requests for the same cache key while keeping each caller's request metadata independent.
- Permit two active upstream parses and four admitted waiters. Wait at most two seconds for upstream capacity and return documented `429`/`503` responses with suitable `Retry-After` values.
- Release permits, waiters, sessions, and in-flight entries correctly after completion, timeout, cancellation, or client disconnect. Bound and clean every in-memory table.

### R6. Tests, probe, and container delivery

- Provide deterministic offline fixtures and tests for supported image/Live Photo/video structures, login/challenge/missing/unknown pages, invalid URLs, redirect checks, media selection, API envelopes, authentication, caching, coalescing, limits, timeouts, and cancellation.
- Provide an explicit opt-in probe script for one or two real URLs. It must redact secrets and separate page parsing, representative file-header checks, and full media playback/download verification.
- Deliver a locked Python dependency set, Python 3.12 slim Docker image, non-root UID/GID 10001, one Uvicorn worker, Compose configuration, `.env.example`, health check, log rotation, and loopback-only default port binding.
- Deliver an Nginx example that preserves application JSON and maps proxy-generated 413/502/503/504 responses to the same envelope without overwriting existing sites.
- Keep README, implementation status, and deployment commands accurate after local verification.

## Acceptance Criteria

- [x] AC1: A clean local environment can install the locked dependencies and run the full offline test suite successfully.
- [x] AC2: Offline fixtures produce an ordinary image result with unchanged ordered body images, a mixed image/Live Photo result whose motion MP4s remain paired with their owning image positions, and a normal video result with exactly one main MP4 plus a separate cover. A declared Live Photo or normal video missing a supported MP4, unsupported live broadcasts/unknown mixed content, and unknown structures return their documented failures without partial success.
- [x] AC3: URL and redirect tests prove unsupported hosts, credentials, IP literals, private/non-public resolutions, unsafe redirects, and more than three redirects make no connection to an unapproved target.
- [x] AC4: The upstream client uses the pinned `curl_cffi`/`chrome136` baseline, manually checks each redirect, binds vetted DNS results, enforces TLS verification, stops above 2 MiB, and respects cancellation plus the single twenty-second deadline.
- [x] AC5: Parse, health, authentication, validation, framework errors, and unexpected failures match the checked-in JSON contract, including optional per-image `live_video`, without leaking sensitive values.
- [x] AC6: Deterministic concurrency tests demonstrate 120-second/256-entry success caching, refresh bypass, same-key coalescing, two active parses, four waiters, two-second queue timeout, 20-per-minute rate limiting, and cleanup after cancellation.
- [x] AC7: `docker compose config`, image build, non-root startup, production-key startup failure, loopback binding, and local `/healthz` checks pass on an available Docker host.
- [x] AC8: README, OpenAPI, examples, technical design, implementation checklist, and deployment guide describe the delivered Live Photo behavior and clearly label all unexecuted VPS/real-network checks.
- [x] AC9: The opt-in probe can accept a user-supplied real share URL without persisting secrets or media URLs, reports the Live Photo count in its redacted result, and keeps static-file and motion-MP4 checks bounded.
- [x] AC10: A user-authorized mobile-copy `xhslink.cn/o/<token>` resolves through the existing manually checked redirect flow to a supported detail page; exact-path/cache tests pass, while `.cn` lookalikes, subdomains, other paths, unsafe targets, and redirect-budget overflow remain fail-closed.

## Out of Scope

- Account login, caller-supplied Xiaohongshu cookies, browser automation, CAPTCHA bypass, or claims that anonymous access will always work.
- Share-text extraction, batch parsing, author/comment collection, live-broadcast support, transcoding, watermark removal, media proxying, object storage, or permanent URLs.
- Frontend or public browser use of the API key.
- Multiple workers, multiple replicas, distributed cache/rate limits, or a managed production rollout.
- Claiming VPS, CDN, Referer, target architecture, or real caller-network acceptance before those checks are actually run with user-provided infrastructure and samples.

## Deferred External Validation

- The five earlier sample pages cannot be replayed because the repository intentionally omits usable tokens and raw HTML. Synthetic/sanitized fixtures can establish parser semantics, but current upstream compatibility needs new real URLs.
- Native `linux/amd64` or `linux/arm64` dependency and network verification depends on the target VPS architecture.
- HTTPS integration, real caller media access, full playback, and rollback rehearsal remain deployment-stage checks owned jointly with the deployer.
- The intended Git repository has been identified; creating the task commit and running the finish workflow remain deferred.
- A user-supplied real sample established the Live Photo field shape without being persisted: 18 ordered image items, with items 10 and 13 marked `livePhoto=true`; each exposed an H.264-group MP4 master plus one backup on the already allowed video CDN host. The page did not expose trustworthy motion width, height, duration, or explicit codec values, so implementation must not infer them from the still image.
- A second user-authorized sample established the mobile-copy short-link shape without persisting its token, query values, note ID, request ID, page, or media URLs: exact `xhslink.cn/o/<token>` redirected once to exact `www.xiaohongshu.com/discovery/item/<note_id>` with the access-significant share query. The rebuilt API parsed 7 ordered images with 7 paired Live Photo MP4s and empty top-level videos. No suffix-based host or broader `.cn` path allowance is required.
