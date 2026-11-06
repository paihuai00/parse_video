# Regional Live Photo video host compatibility

## Diagnosis and evidence boundaries

Baseline: `256d8db066e7a4b15a5a7901ca27731bfc88adbf`. Development and VPS
repositories use the same origin/main and baseline commit; all three deployed
parser source hashes matched. The pre-existing local `.trellis/config.yaml` edit
and VPS untracked diagnostic directory are preserved.

On 2026-11-06, an authorized four-slot Live Photo returned complete domestic
media locally but regional media on VPS. VPS acquisition reached rednote desktop
HTML, decoded state and selected the correct four-slot note. All still candidates
used the already accepted `sns-web-i10.rednotecdn.com`. Each motion stream had one
candidate: master `sns-v28.rednotecdn.com`, backups `sns-v11.rednotecdn.com` and
`sns-v27.rednotecdn.com`. Their HTTP URLs passed non-host structural checks and
provided positive MP4 path evidence. The unsupported hosts caused
`502 MEDIA_NOT_FOUND / declared Live Photo has no supported MP4`.

VPS read one representative still and its primary MP4 over verified HTTPS with
all DNS answers checked public, pinned IPs, no environment proxy, no redirects,
and exactly 1024 body bytes each. Both returned 206; JPEG and MP4 ftyp signatures
matched. Backups have same-note candidate provenance but no independent byte or
playback verification. No real page, note ID, share parameters or signed media URL
is stored in this report or the synthetic fixtures.

Cross-vantage diagnostic IP pinning did not exchange outcomes: VPS still
redirected to rednote using the development-observed detail server IP; development
still returned domestic content using the VPS-observed IP. The full detail URL
hashes matched. A fresh VPS direct-detail session still redirected to rednote;
development's direct rednote request redirected back to Xiaohongshu. An isolated
VPS mobile comparison still failed with unsupported motion. This supports
source-network-dependent region selection; the upstream's precise IP-geolocation,
ASN or other decision rule is not observable here. No DNS or strategy changes are
part of the repair.

Direct VPS API and correctly verified local Nginx HTTPS returned application JSON
with MEDIA_NOT_FOUND. The public request reached Nginx, which sent a 228-byte 502,
while Cloudflare returned a 16-byte plain-text 502 without the request ID. This is
a separate ingress diagnostic limitation; no Cloudflare/Nginx changes are needed
for the media fix.

## Repair and prevention

Add only the three evidenced exact hosts in a video-only set used by the existing
URL normalizer. Keep existing shared/image hosts unchanged. Normal-video and
Live Photo master/backup candidates already request video context, so no alternate
fetcher, fallback, dependency, runtime setting or public schema change is needed.

The previous regional Live Photo fixture used domestic motion and did not exercise
regional video hosts. The new explicitly synthetic fixture has four ordered
regional still/motion slots, Set/undefined syntax and an unrelated note preceding
the requested note. Regression coverage includes video-only host roles, unsafe
authorities, unknown shards, required MP4 evidence, normal videos, all three
master/backup choices, both public routes and desktop/mobile paths. Incomplete
fourth-slot motion cannot become partial or static-only success.

Unknown hosts remain rejected. Future failures should be diagnosed by acquisition,
state decoding, identity selection and media normalization, then record only host,
field, type/count and rejection rule in a bounded independent diagnostic. Do not
log raw URLs or page fragments, guess numbered shards, rewrite regional hosts into
domestic hosts, or treat local success as regional acceptance.

## Release procedure

Run all locked Python 3.12 offline checks and one authorized local real API request
before committing and pushing. On VPS, require a clean tracked baseline and the
same origin/main, fast-forward only, retain the current image for rollback, build
only api and recreate only that service. Compare source hashes inside the running
container and require the same real request through loopback, verified local
Nginx HTTPS and public HTTPS to return four ordered images with four nested motion
MP4s and no top-level video. Health alone is insufficient.

## Local validation before release

- Python 3.12.16 with locked runtime/development dependencies: **385 tests passed**
  (47 additional regressions). Ruff check/format, Mypy (26 source files), compile,
  checked-in OpenAPI JSON validation and diff whitespace checks passed.
- With the new video-only set disabled only inside an isolated synthetic check,
  the four-slot fixture reproduces the baseline missing-MP4 error; with the set
  enabled it returns four complete ordered pairs.
- An independent single-worker loopback Uvicorn served the authorized real legacy
  API request at 2026-11-06 13:34:43 UTC: HTTP 200, cache miss, four images, four
  nested Live Photo MP4s and no top-level videos. Request ID
  `715050bc-d170-4bc2-b41d-043d5a0ed6cf` matched the successful application log.
  The temporary verification service was stopped afterward. This domestic local
  success does not replace regional VPS acceptance.
- New `app/parser/media.py` SHA-256:
  `fa2cb4fd7adc8079ffc7e819f539d3e47d703c4ad2d4dbc9278999c1cf7f144a`.
  Client/state-reader hashes remain unchanged from the baseline.
