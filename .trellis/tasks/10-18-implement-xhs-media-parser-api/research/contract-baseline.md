# Contract and Feasibility Baseline

## Source documents

- `README.md`: current project status and public scope.
- `docs/technical-design.md`: authoritative parsing rules, request chain, resource limits, error taxonomy, and verified anonymous-access baseline.
- `docs/openapi.json`: public endpoint and schema contract.
- `docs/examples/*.json`: contract examples.
- `docs/implementation-plan.md`: P0-P5 dependencies, planned modules, and acceptance requirements.
- `docs/deployment.md`: environment, Docker, Nginx, rollout, and rollback requirements.
- `docs/evidence/anonymous-probe-2026-10-17.json`: redacted empirical note/media counts and limitations.
- `docs/evidence/mobile-short-link-probe-2026-10-18.json`: redacted exact-host/path redirect evidence for one authorized phone-copy short link.

Implementers and reviewers must open the relevant source document when exact field names, schemas, or status mappings are needed. These source documents are planned deliverables and therefore are not injected into the task manifest as static context.

## Confirmed product outcome

The caller sends one supported Xiaohongshu URL to `POST /api/v1/xiaohongshu/parse`. The service returns JSON containing ordered image direct URLs, with an optional nested Live Photo MP4 on each owning image, or exactly one selected normal-video MP4 plus a separate cover. Image-note `videos` remains empty; top-level `videos` is reserved for a normal video note. The caller downloads media directly from the upstream CDN. The v1 service does not proxy, store, bundle, transcode, or stream media files.

## Implementation feasibility

- `curl_cffi==0.13.0` with explicit `chrome136` is the compatibility baseline demonstrated by the existing evidence.
- Redirects must be followed manually so every hop can be checked before a connection is made.
- libcurl `CURLOPT_RESOLVE` provides the required hostname-to-vetted-address binding while preserving TLS hostname verification. The pinned curl_cffi release must be verified with a transport integration test; inability to bind is fail-closed.
- Native `content_callback` collection provides a path to abort decompressed HTML above 2 MiB. The callback-abort mapping must be tested against the pinned release.
- Synthetic/sanitized fixtures can cover deterministic parser semantics. A user-authorized sample confirmed that per-image Live Photo streams can contain an allowed-host H.264-group MP4 master plus backup, but the input token and returned media URLs must not be persisted. Broader real-world upstream compatibility still requires opt-in live probing.
- A user-authorized phone-copy sample confirmed the minimal additional entry point: exact `xhslink.cn/o/<token>` redirects once to exact `www.xiaohongshu.com/discovery/item/<note_id>` while carrying access-significant share parameters. The rebuilt API then parsed 7 ordered images with 7 paired Live Photo MP4s and empty top-level videos. The token, parameter values, note ID, request ID, HTML, and media URLs are not retained. This evidence supports only that exact host/path form, not suffix matching or arbitrary `.cn` routes.

## Delivery constraints

- P1-P4 implementation and local verification are in scope.
- P5 VPS, caller-network, full playback, HTTPS, and rollback rehearsal remain explicitly unverified until the deployment environment is available.
- The workspace is now the root of the intended Git repository and tracks `origin/main`; the task changes remain uncommitted, so Trellis commit/archive completion is still deferred.
