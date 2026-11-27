# Unified VPS parsing and media proxy

## Current status

Development is complete and approved for archive. Implementation, quality checks and the recorded deployment/sample/tool evidence are retained in verification.md. All still-unverified release/device/source requirements are carried by `/Users/didi/ai_project/video_download_mini/.trellis/tasks/11-27-unified-vps-release-acceptance`; they are not marked passed or silently waived. See completion.md for the transfer map.

## Goal

The mini program submits a share URL to one VPS endpoint. The VPS detects the platform, runs existing XHS acquisition or migrated third-party Douyin/Bilibili/generic requests, and returns image, video, per-image motion-video and cover URLs on its own HTTPS origin. The VPS streams media from upstream without retaining complete media files.

## Confirmed requirements

- The mini program uses one parsing endpoint: `POST /api/v1/parse`. The VPS chooses XHS self-acquisition, the existing third-party Douyin chain, the Bilibili chain, or the existing generic provider.
- Move the current Douyin provider HTTP clients, source-specific normalization, ordering, retries and fallback into the VPS. Preserve the current default provider order initially; there is no client provider selector or client learned preference in the new path.
- The native Douyin acquisition code does not replace the selected third-party chain in this migration. Keep its existing implementation isolated; do not silently add it as a new fallback or promise watermark removal.
- Normal new parsing and expired/history recovery use the same parsing endpoint. Do not require a separate media-ticket POST in this workflow. Media GET/HEAD requests are content retrieval, not additional parsing APIs.
- Use the existing VPS; do not request its location, capacity or traffic budget again.
- Rewrite the existing response media `url` fields directly. A separate download-address request must not be required for the self-hosted parse response.
- All returned image/video URLs and download URLs in every migrated workflow use the VPS origin. No download fallback to direct CDN requests.
- Preserve complete upstream URLs, including signatures in paths and query strings.
- Keep raw CDN addresses in `InternalNote` and the parse cache; issue fresh media URLs when building each public response, including cache hits.
- Credentials are temporary and reusable for display, preview and saving. Their expiry does not extend upstream URL validity.
- Retain `verification=not_checked`; distinguish credential expiry from parse-cache expiry.
- Keep a bounded process-local mapping; issue all media in a work atomically. Do not silently evict unexpired mappings to satisfy a new issuance request.
- Validate media hosts by platform/type, public DNS addresses and every redirect; pin transport connections to validated addresses and preserve TLS hostname verification.
- Use bounded streaming with backpressure, independent download admission/timeouts, cancellation cleanup and redacted logs.
- Use a configured public origin rather than untrusted request Host headers.
- Preserve existing media ordering and MP4 saving semantics; do not silently turn dynamic works into still-only results.

## Verified repository facts

- `app/api/routes.py:parse_media` already exposes `POST /api/v1/parse` with platform detection.
- `app/api/routes.py:parse_note` retains the XHS-specific route.
- `app/models.py:_to_public_components` assembles public media fields.
- `app/services/cache.py` stores raw `InternalNote` records.
- The pre-migration contract excluded media proxying; the implemented contract now covers unified provider dispatch and bounded media delivery, with OpenAPI/docs/specs synchronized.
- Existing Douyin direct acquisition and current mini-program third-party provider chains are separate capabilities. `app/parser/adapters.py:DouyinAdapter` uses short-link expansion, mobile share acquisition for ordinary videos, then eligible browser fallback. `app/parser/douyin/media.py:normalize_douyin_note` explicitly rejects motion-bearing image works.
- `InternalImage.live_video` and public `ImageMedia.live_video` can represent per-image motion, but this does not mean native Douyin acquisition currently supports it. `InternalNote` has no platform field, so provider context must be passed separately if needed.
- `docs/douyin/technical-design.md` does not promise watermark removal or watermark-free output. Selecting native acquisition must not silently introduce a watermark-free guarantee.

## Intended boundaries

- Keep one parse endpoint for all new client parsing; retain the existing XHS route for older-client compatibility.
- Keep media credential/transport responsibilities separate from page acquisition and provider parsing.
- Keep current anonymous sessions isolated; do not accept arbitrary client Cookie/Authorization/Referer headers.
- Do not introduce Redis, a database, persistent media storage, transcoding, native iOS Live Photo generation, or multiple workers.
- This record-synchronization/closure round performs no product changes, Git writes or deployment. Earlier implementation/live checks/deployment remain documented evidence, not new actions.

## Planned acceptance criteria

- AC1: One configured endpoint handles XHS, Douyin, Bilibili and the existing generic path; no new-client direct third-party parse request remains.
- AC2: All non-null `images[].url`, `videos[].url`, `images[].live_video.url` and `cover.url` use the configured VPS origin.
- AC3: Both cache hits and misses issue usable media credentials without mutating raw cached data.
- AC4: Images and complete MP4s stream through the VPS and are usable by the mini program; no client redirect returns to CDN origins.
- AC5: Expired/lost credentials, upstream rejection, overload and timeout have distinguishable status/error headers and bounded client recovery.
- AC6: Unsafe hosts/IPs/redirects never produce an unsafe connection; cancellation releases all resources.
- AC7: The agreed Douyin provider strategy preserves explicitly selected image/video/motion and watermark behavior; no silent loss of slots or motion.
- AC8: Existing parse behavior, media metadata and compatibility routes pass appropriate offline regression checks. Real VPS and device verification is reported separately.

## Final routing decisions

- XHS: existing self-acquisition; do not reactivate disabled third-party XHS providers.
- Douyin: `/douyin` -> `/dyjx` -> ifphp `/svparse` -> `/short_videos`, all server-side.
- Bilibili: `/bilibili` -> `/short_videos`, all server-side.
- Generic: existing `/short_videos` via a fixed server-side provider; this does not promise new platform coverage or arbitrary direct server fetching.
- Remove client-side manual/adaptive provider routing. Use the existing default order on the VPS with one bounded deadline; do not introduce a new shared learned preference system.
- No unresolved product questions remain. Transport/provider-network evidence is an implementation/release gate, not an assumption of success.

## Failure and compatibility decisions

- Douyin fallback remains inside the VPS provider chain and shares one bounded deadline/attempt budget. A failed media publication or media GET must not restart the provider chain.
- Exhausted providers return a stable server error; the client does not call third parties as an emergency fallback.
- Raw historical CDN URLs are refreshed through the same parse endpoint using their saved share URL before use. Expired proxy URLs follow the same bounded refresh path.
- Keep the existing XHS-specific server route compatible for older clients; the new client uses only the unified route.

## Coordination

Client task: `/Users/didi/ai_project/video_download_mini/.trellis/tasks/archive/2026-11/11-27-unified-vps-parse-client/`.
`design.md`, `implement.md` and `verification.md` record the implemented architecture, completed checks and remaining acceptance. See `vps-deployment-verification.md` and `wechat-devtools-verification.md` for scoped live/UI evidence. No remaining acceptance is silently waived.

