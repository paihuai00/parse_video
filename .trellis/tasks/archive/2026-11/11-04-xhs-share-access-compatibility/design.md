# Technical design: distinguish upstream states and qualify anonymous acquisition

## Evidence and boundaries

See research/share-link-comparison.md for baseline desktop failures, research/alternative-acquisition.md for local mobile success, and research/vps-verification-report.md for user-relayed VPS container success on the short link. The current product selector still rejects the acquired mobile schema; VPS media and full API acceptance remain open. The existing service remains anonymous, accepts one complete share URL, and does not download media. Error handling stays within parser/client.py; API envelopes and central public messages remain compatible.

## Track A: minimal error-classification correction

Keep parse_url strict for caller input and normal note hops. Add a narrow redirect classification boundary after a legitimate note response and before submitting the next URL to note-path validation. Share or factor authority checks rather than duplicating host/protocol/port/credential logic.

Authority-invalid, cross-platform, arbitrary-path, credential-bearing, unsafe-address, or otherwise dangerous destinations remain INVALID_URL and must not be fetched. Any connection still requires public-address DNS checks and pinned addresses. Classification of an exact known status destination requires a vetted authority; do not allow arbitrary paths merely to run classify_page afterward.

Exact known login destinations may return UPSTREAM_LOGIN_REQUIRED without fetching the login page. An exact /404 destination without explicit missing-note evidence returns UPSTREAM_BAD_RESPONSE (502, not retryable by default), not NOTE_NOT_FOUND. Unknown errorCode values, including the observed -510001, must not acquire invented semantics. Relative locations must be resolved before validation. Original deadline and redirect budget apply throughout.

This corrects the misleading INVALID_URL but does not restore anonymous content access. Diagnostics contain only safe stage, upstream status, target category, and bounded recognized error-code fields; never full URLs, query values, tokens, cookies, or HTML. Do not echo arbitrary upstream strings as public diagnostics.

## Track B: preferred anonymous mobile acquisition and schema support

Subsequent real probes in research/alternative-acquisition.md demonstrate a lighter solution for this sample: safari184_ios retrieves a mobile note with matching noteId, hasError=false, one ordinary static image, and a usable H5 detail image URL. A bounded local representative image check returns HTTP 206, image/jpeg and JPEG magic. The user-relayed VPS report independently confirms short-link mobile acquisition in the real x86_64/Python3.12.8/curl_cffi0.13.0 application container, but not VPS media, PC-long-link or full API success. VPS image stream contents remain unchecked; verify those before claiming motion completeness.

Preserve the existing desktop strategy. The first implementation has one evidence-backed fallback trigger: a validated note response redirects to exact same-host /404 after redirect authority validation. Represent this as a narrow internal typed acquisition failure, preserving the public generic upstream error if fallback also fails. Do not classify arbitrary public INVALID_URL or generic PARSE_FAILED as fallback-eligible. Direct login, explicit missing content, challenges/rate limits, network timeout, arbitrary paths, initial malformed URLs, unsafe redirects or unsafe DNS do not trigger mobile fallback in this scope.

Keep strategy composition at the client/acquisition boundary so existing adapter/service contracts and test fetcher seams remain compatible. Invoke the mobile strategy at most once, in an independent anonymous session, preserving the original full input URL/query. Desktop retry, mobile fallback and all redirects consume the same Deadline and parse-level bounded retry/redirect accounting; no new 20-second or three-redirect allowance per strategy. An internal shared budget may be passed through private helpers without changing public API payloads. Record and test the upper bound across combinations, including cancellation and exhausted remaining time. No global environment-only fingerprint replacement is sufficient.

Select mobile data only from the exact state.noteData.data.noteData object, validate container types and noteData.hasError, and require its noteId to match the requested ID. Preserve the existing decoder size/depth/node limits and desktop selection branch. Do not recursively search the page for an arbitrary note-shaped object.

Extend media normalization with explicit mobile image candidates: prefer H5_DTL from infoList, then a positively applicable direct image URL. H5_PRV is a preview and is not by itself proof of complete media; an unlabeled direct URL equal to a known preview URL cannot rescue a preview-only item. All candidates pass existing exact CDN host and HTTPS normalization. Preserve image ordering and dimensions; do not copy image metadata to video.

Validate every mobile image slot before normalization: require a nonempty imageList of image objects with usable detail candidates; reject a malformed/missing slot instead of inheriting the legacy normalizer's skip-and-continue behavior. Inspect livePhoto, stream and other recognized motion evidence per slot. Mobile motion/video is outside this first verified scope and must fail closed, never return a still-only success. Do not tighten unrelated desktop behavior in this task. Existing desktop video/Live Photo support remains intact.

The current sample has livePhoto=false and no stream metadata. That supports its observed mobile static-image result; it does not prove every desktop motion note is faithfully represented by the mobile page.

## Track C: conditional browser or provider research

Deferred from this implementation scope. The login-modal marker issue remains an unconfirmed separate risk; do not expand this task into refactoring login classification without a matching real fixture. The existing user request is satisfied by the evidence-backed mobile path plus the narrow redirect correction.

The user confirmed full content is visible in a logged-in desktop browser. This establishes access within that account session, not a universal login requirement. Browser research is now secondary because Track B has positive local evidence. If still necessary after mobile qualification, compare a fresh anonymous browser with HTTP on the deployment egress. Preserve the original complete URL and verify exact requested note identity. Success requires complete media information, not a loaded shell, login overlay, error page, or recommendation feed.

The subsequent logged-out screenshot shows a login modal with note content visible behind it. This establishes a UI login prompt, not whether complete media data is unavailable. A fresh context must exclude pre-logout memory and cached content. Inspect bounded target-note state/network results even when a modal is shown; do not infer anonymous access by hiding the modal. Current classify_page rejects login markers before target-state decoding, so a fixture with complete target data plus a modal is a classification risk to investigate, not a confirmed second root cause. Any proposed refinement must distinguish a login prompt from an actual missing-data/login barrier and retain explicit challenge/denial handling.

If the browser succeeds while HTTP fails, propose a separately bounded Xiaohongshu browser acquisition boundary. Existing Douyin BoundedConnectProxy demonstrates public-address pinning and cleanup, but its resources and allowlists are not Xiaohongshu evidence. Any browser proposal must explicitly cover exact required hosts, request/byte/state/process budgets, original total deadline, independent anonymous contexts, worker capacity, cancellation, and unchanged media normalization.

If anonymous browsing also fails, do not implement a speculative browser fallback. Distinguish observed login requirements from unknown access restrictions; isolate session, token freshness, and egress factors with authorized samples. Importing account cookies or adding login capability is outside the current contract and requires a separate scope decision.

Third-party API and open-source candidates are documented in research/alternative-acquisition.md. Neither provider credentials nor paid operations are available/used. No provider or downloader is selected for integration; its published capability does not prove this sample succeeds. A new provider would also need media-completeness, exact CDN policy, credentials, cost/deadline and failure-semantic review.

## Compatibility and rollback

Final deployment is a Linux VPS using the existing Python 3.12 Debian image. safari184_ios is a curl_cffi impersonation profile, not an actual Safari/browser dependency. Short-link acquisition on the real egress is now supported by the user-relayed VPS report. Complete remaining media/long-link/API acceptance and independently verify public ingress and client-side CDN consumption. See research/vps-deployment-impact.md and research/vps-verification-report.md. This local session did not access the server.

Local Git inspection established that the reported VPS commit be32fc7 is an ancestor of current75b3b62, and app/tests/scripts/requirements/pyproject/Dockerfile/compose/deploy have no diff; intervening changes are Trellis records. No user decision is needed on source divergence for these product files. Image-wide provenance still needs a traceable candidate version/digest at release; a reused image tag is insufficient proof. Keep production rollout separate from local implementation/testing.

No request schema change, token rewriting, global host expansion, automatic redirects, extra unbounded retries, or production deployment in this task's planning phase. Legacy and unified routes retain their messages and common envelope. Track B uses an already supported curl_cffi fingerprint and an already allowlisted observed image host; no dependency upgrade is justified by these probes. Rollback the mobile strategy and schema branch independently, preserving desktop parsing; Track A can also be reverted independently. Browser runtime changes require their own evidence and review before implementation.
