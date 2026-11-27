# Backend implementation plan

> Development closure approved on 2026-11-27. See [completion](completion.md) and the [remaining acceptance task](/Users/didi/ai_project/video_download_mini/.trellis/tasks/11-27-unified-vps-release-acceptance/prd.md). This closure supersedes prior in-progress status summaries; unchecked release items are transferred, not passed.

## Entry gate

- [x] Obtain explicit approval of the latest final plan. Remain planning until then; do not run `task.py start` or change product code yet.
- [x] Recheck task artifacts, applicable backend specs and unrelated worktree changes. No Git write operations, even indirectly through hooks/tests.
- [x] Complete the approved initial memory lifecycle; keep finished runs immutable as historical evidence. This update is explicitly authorized record maintenance.

## 1. Contract and bounded transport proof

- [x] Map unified platform/identity/optional metadata contracts, keeping legacy XHS strictness. Inspect every `InternalNote.note_id` caller before allowing missing third-party IDs.
- [x] Add deterministic proof tests for source URL byte preservation, vetted-IP connections/TLS identity, bounded slow-consumer buffers and cancellation. Choose the smallest transport satisfying all four.
- [x] Record configurable credential/connection/queue/byte/time budgets as application defaults, not claims about WeChat limits. Keep one worker.

## 2. Provider migration

- [x] Add fixed bugpk/ifphp provider clients and source-specific JSON normalizers; migrate the ifphp environment credential without exposing it.
- [x] Implement Douyin default chain, Bilibili chain and generic fixed provider. Keep XHS acquisition unchanged and native Douyin isolated.
- [x] Preserve positive image/video evidence, complete slot ordering, motion pairing and relevant text/author metadata.
- [x] Extend platform dispatch, cache identities and request coalescing safely; bound all retries/fallback by one deadline. Keep publication errors outside provider retry handling.
- [x] Add fixtures for each provider shape, missing IDs, metadata, dynamic content, malformed/oversized JSON, provider failures and deadline exhaustion. Synthetic fixtures must be labeled.

## 3. Media credentials and publication

- [x] Implement bounded credential records/signing, atomic per-work registration and rollback of unpublished batches.
- [x] Publish all image/video/motion/cover/avatar addresses on configured VPS origin at response time; cache remains raw.
- [x] Cover fresh/cache-hit responses, no raw nested URL leakage, expiry, restart, capacity and concurrent atomic registration.

## 4. Media HTTP retrieval

- [x] Implement credential-authorized GET/HEAD, per-hop media policy and pinned transport.
- [x] Implement byte-correct full streaming, content checks, separate admission, explicit Range policy and all disconnect/error cleanup.
- [x] Add stable status/error headers; keep streaming completion telemetry separate from request header timing.
- [x] Test unsafe DNS/redirects, lookalike hosts, tampered/expired credentials, HTML masquerading as media, truncated/oversized bodies, stalls, queue saturation and cancellation.

## 5. Deployment/spec synchronization

- [x] Update Nginx media locations, generic errors, no-buffer/cache settings and safe logs.
- [x] Update configuration, environment examples, dependency locks if needed, OpenAPI/examples, README and deployment/service-contract docs.
- [x] Preserve the legacy XHS route and unrelated Node/reporting services. Document old-client/old-route compatibility and rollout switch.

## 6. Local quality checks

Run in the supported Python 3.12 environment after implementation, not during planning:

```sh
ruff format --check app tests scripts
ruff check app tests scripts
mypy app
pytest -q
python -m compileall app tests scripts
python -m json.tool docs/openapi.json >/dev/null
```

- [x] Validate runtime OpenAPI against checked-in schema/examples; tests do not call real upstreams.
- [x] Run client integration fixtures for all platform/provider paths.
- [x] Nginx `nginx -t` passed before/after the recorded VPS cutover; lifecycle/test helpers were checked for prohibited Git writes.


## 7. Recorded release progress and remaining acceptance

- [x] Backend candidate deployment and authorized seven-work live verification completed; candidate and formal HTTPS each passed 7/7 parses and 25/25 full media downloads.
- [x] Nginx runtime validation, safe media routing and independently verified representative Mac-to-production image/video downloads completed.
- [x] Shared two-transfer scheduling/local-preview fixes passed 69 client tests and the bounded 13-image developer-tool preview case; backend remained unchanged.
- [x] Rollback backups and automatic cutover recovery were prepared; this does not establish a completed rollback drill.
- [ ] Verify Bilibili, generic and motion-photo live sources; the existing sample set did not cover them.
- [ ] Complete domain-check-enabled real-device preview/save, post-fix album saving, cancellation and any necessary HEAD/Range validation.
- [ ] Complete experience/formal client publication only after acceptance and explicit authorization.
- [ ] Exercise an actual rollback drill and verify ongoing image/video behavior under production concurrency.

See `verification.md`, `vps-deployment-verification.md` and `wechat-devtools-verification.md`. This synchronization does not deploy or retest live services.
