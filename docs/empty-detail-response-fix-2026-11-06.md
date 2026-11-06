# Empty detail responses and complete mobile Live Photo recovery

## Observed failure

After initial local HTTP acceptance, the user reported two `PARSE_FAILED`
responses. Request ID `f7416132-4708-4028-b842-0935c8d941af` matched an application
502 log. Both authorized static and Live Photo samples reproduced the error.
Independent default-client diagnostics showed short-link 302 → exact
`www.xiaohongshu.com` detail 200, `Content-Type: text/plain`, zero decoded body
characters and no state marker. The precise error was `initial state assignment
missing`, before Set normalization or media normalization.

The source hash and running process were unchanged from the preceding successful
HTTP tests. This establishes a response-shape change, not a Set syntax regression;
its upstream cause (rate, edge routing or other policy) is not established.

A purposeful independent `safari184_ios` comparison returned a nonempty mobile
HTML page for the static sample and normalized one image. For the Live Photo
sample, strict target-bound mobile selection exposed both a supported detail still
and a supported paired MP4. No page, note ID, share token or media URL was saved.

## Repair scope and invariants

1. Recognize only actual zero-byte, HTTP 200 responses from already validated
   note details. Raise an internal typed acquisition outcome, not a parser error.
2. Permit one fresh mobile session using the validated full detail URL. Keep the
   original default desktop strategy, two total attempts, total Deadline, redirect
   budget, target identity, per-hop DNS/public-address checks, IP pinning and TLS.
   No fallback on generic parse errors, short-link emptiness or nonempty shells.
3. If mobile acquisition is also empty, stop with retryable `UPSTREAM_BAD_RESPONSE`.
   Do not add attempts, return empty success or label the note missing.
4. Extend the existing strict mobile image normalization only for complete paired
   MP4 motion. Reuse desktop candidate/backup/codec selection and metadata rules,
   preserve the detail still and original slot, and attach motion to `live_video`.
   Incomplete motion, malformed slots and previews cannot become static success;
   ordinary mobile videos remain unsupported. No new media hosts are added.
5. Preserve the separately tested Set normalization; add deterministic synthetic
   regressions for zero-byte recovery, failure limits, authority/identity/deadline/
   cancellation checks and complete static/Live Photo API results on both routes.

The mobile motion fixture is explicitly synthetic, not an archived upstream page.
Existing tests for a valid motion stream were updated to require a paired result;
tests for unsupported motion still require failure without partial images.

## Validation

- Targeted transport/media/pipeline tests: 140 passed.
- Full offline suite: 309 passed. Ruff format/check passed (46 files); Mypy passed
  (26 source files). Compilation, OpenAPI JSON and diff whitespace checks passed.
- Restarted only the local development service after successful checks, retaining
  loopback port 8000, one worker, existing test authentication and `chrome136`.
  New PID 53018; no configuration changes, VPS deployment or Git write operations.
- Real legacy HTTP API requests with `refresh=true`, 2026-11-06:

  | Sample role | UTC | HTTP | Images / Live Photos / videos | Cache | Request ID |
  | --- | --- | --- | --- | --- | --- |
  | Static regression | 09:07:57 | 200 | 1 / 0 / 0 | miss | 6893814e-ce09-4524-8044-a7a4085a89b0 |
  | Live Photo regression | 09:07:58 | 200 | 1 / 1 / 0 | miss | bddad628-1e18-472a-a0a8-c5e97954ab26 |
  | Set regression | 09:07:58 | 200 | 1 / 0 / 0 | miss | f7ec27af-35d6-4bfa-b21e-7b4d3ceb3d87 |

All three request IDs matched status 200, outcome OK and cache miss in the actual
service log. A later purposeful Live Photo acquisition trace returned a nonempty
78,066-byte desktop detail and succeeded without mobile fallback, showing the
upstream shape can change again. Do not claim that these live successes exercised
the zero-byte branch; its deterministic static/motion/budget evidence is offline.

Validated source SHA-256 values:

```text
client.py       84cfcfc6866bb1a99d329cc3cdc9b549226b61ad875d0c42b50199fe109d722d
media.py        d7b7f9f52e422d853cd2f6cdb38427bab21d929c4ca3642caf2ca70346491b1c
state_reader.py e2bfd1d1980f55ae980b47c0fe3c2ef6ab52909882641b78711b6aa336d4d1c7
```

These API outcomes prove local success at those times, not permanent upstream
availability. Set syntax coverage remains grounded in its synthetic failing-before
regressions; real VPS and caller media playback checks remain separate.

## VPS acceptance after authorized deployment

Check actual running-container client, media and state-reader source hashes.
Replay the same three authorized inputs with `refresh=true` through loopback,
Nginx and public API. Record request IDs, safe failure stages and media counts.
For zero-byte desktop responses, observe at most one mobile attempt on the full
checked detail, with target identity intact. Verify the Live Photo still and
nested MP4 are both present, not a static-only success. Repeated mobile emptiness
must stop as `UPSTREAM_BAD_RESPONSE`. Never change global strategy, credentials,
host rules or budgets merely to turn a failed check into success.
