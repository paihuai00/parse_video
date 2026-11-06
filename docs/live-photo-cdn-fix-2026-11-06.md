# Live Photo CDN compatibility repair

## Plan and acceptance criteria

The authorized sample reaches a desktop detail page, decodes its state, and
selects one image with a Live Photo H.264 candidate. Its master and both backup
hosts are absent from the exact media allowlist, so normalization fails with
`MEDIA_NOT_FOUND` instead of returning the complete still/motion pair.

1. Confirm the candidate shape and rejection reason without retaining input
   tokens, note IDs, pages, or signed URLs.
2. Add only the observed exact hosts `sns-video-v4.xhscdn.com`,
   `sns-bak-v1.xhscdn.com`, and `sns-bak-v6.xhscdn.com` to the existing shared
   media URL policy. Keep MP4 evidence, authority checks, media ordering and
   per-image motion ownership intact.
3. Add sanitized offline regression coverage for each host, backup selection,
   unsupported formats, unknown/similar hosts, credentials and ports, plus both
   public API routes through the real parser/service chain.
4. Run the full Python 3.12 test suite, Ruff, Mypy, compilation, OpenAPI JSON
   validation and diff whitespace checks.
5. Restart only the existing local development service and replay the authorized
   request with `refresh=true`; require one image with one nested motion MP4 and
   no top-level videos. Report any live upstream limitation separately.

No VPS deployment, dependency changes, mobile motion support, generic fallback,
JavaScript execution or wildcard media-host expansion is included. The user's
existing instruction to avoid creating a new Trellis task remains in effect.
Git writes belong to the user.

## Sanitized acquisition evidence

- Default strategy: `chrome136`; short host `xhslink.cn` returned 302 and exact
  detail host `www.xiaohongshu.com` returned 200, using existing transport bounds.
- Desktop state: one normal image, `livePhoto=true`, one H.264 stream candidate.
- Master: exact `sns-video-v4.xhscdn.com`; backups: exact
  `sns-bak-v1.xhscdn.com` and `sns-bak-v6.xhscdn.com`. All three supplied HTTP
  paths ending in `.mp4`; production normalization upgrades accepted URLs to HTTPS.
- Independently read the primary over HTTPS with all DNS answers checked public,
  `CurlOpt.RESOLVE` pinning, TLS verification, no environment proxy, no redirects,
  the original bounded deadline and Range `bytes=0-1023`: HTTP 206,
  `Content-Type: video/mp4`, 1024 bytes, `ftyp` header matched.
- Backup host provenance comes from the same candidate. Backup media bytes have
  not been downloaded; do not claim independent playback or availability checks.
- This proves the allowlist omission for this observed candidate. It does not
  establish other shard hosts, permanent availability, or a need for fallback.

## Validation results

- Implemented the three exact host additions; no changes to parsing strategies,
  public schemas, dependencies, mobile motion scope or runtime budgets.
- Added 29 regression cases covering exact hosts, HTTPS/query preservation,
  missing positive MP4 evidence, unsafe authorities, unknown shards and complete
  master/backup results through both public API routes. The targeted media and
  pipeline suite passed 71 tests; the full offline suite passed 236 tests.
- Ruff format/check passed (46 files), Mypy passed (26 source files), compilation,
  OpenAPI JSON syntax and `git diff --check` passed under Python 3.12.16.
- Restarted only the existing local Uvicorn development service on
  `127.0.0.1:8000`, one worker, unchanged default `chrome136` strategy. Health 200.
- Real legacy API request with `refresh=true` at 2026-11-06 08:19:03 UTC:
  HTTP 200, `success=true`, one image with one nested Live Photo MP4, zero
  top-level videos, cache miss, selected motion host `sns-video-v4.xhscdn.com`.
  Request ID `679a94f6-05fd-4c6f-bdd7-1a43fe2f8ecf`; matching application log
  reports status 200, outcome OK, cache miss, approximately 393 ms processing.
- The service remains running for local user testing. This is local evidence;
  VPS deployment/acceptance and full media playback remain unverified.
- No Git write operations or new Trellis task were performed. The pre-existing
  `.trellis/config.yaml` edit remains untouched.
