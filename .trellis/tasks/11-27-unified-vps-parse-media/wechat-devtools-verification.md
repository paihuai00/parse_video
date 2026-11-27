# WeChat developer tools verification — 2026-11-27

## Scope and result

Directly operated the already-open WeChat developer tools (2.02.2609240 Stable), project `/Users/didi/ai_project/video_download_mini`, app version v1.6.3. Tested two representative samples through the actual home-page UI against the deployed HTTPS service. Result: connectivity and individual downloads pass; multi-image display fails acceptance.

| UI operation | Observed result |
| --- | --- |
| Parse authorized Douyin sample (share token omitted) | HTTP 200; title, author 挖挖, and cover rendered |
| Download Douyin video | Media request HTTP 200, system save dialog, application save-success toast; saved MP4 1,467,450 bytes with `ftypisom` signature |
| Parse authorized XHS 13-image sample (share token omitted) | HTTP 200; GitHub飙升榜 title and 13-image list rendered |
| Initial XHS image loading | 6 JPEG requests HTTP 200, 7 media requests HTTP 503 |
| Repeat XHS parse/loading | Reproduced: 6 HTTP 200 and 7 HTTP 503; failed image positions varied |
| Preview first XHS image | Full-screen image visibly rendered |
| Save first XHS image | System save dialog and application success toast; file 194,355 bytes, JPEG/JFIF signature (tool default filename extension was PNG) |
| Swipe to second image on repeat run | `2 / 13` and blank image area; corresponding request returned 503 |

## Failure evidence

A failed request was to the owned `https://xiguahong.dpdns.org/api/v1/media/...` route, with these response headers:

- HTTP 503
- `x-media-error-code: MEDIA_BUSY`
- `retry-after: 2`
- `x-request-id: fa19d550-83df-4682-8a96-46426de37d08`

The developer-tools Network panel showed WeChat's `servicewechat.com` Referer. Requests traversed the Mac's existing local proxy (`127.0.0.1:7890`). No proxy, security, or domain settings were changed.

Local code defaults are media concurrency 2, queue capacity 4, queue wait 2 seconds. The observed burst of 13 image loads exceeds that admission window. This is a likely client/server concurrency mismatch; deployed runtime settings were not independently inspected during this session. A client image scheduling/lazy-load/retry solution should be evaluated while preserving bounded server resource use. Earlier sequential public media download success does not establish concurrent WeChat image-display success.

## Limits and artifacts

Existing `project.private.config.json` has `setting.urlCheck: false`. Therefore this simulator run does not certify production legal-domain configuration or real-device preview/save behavior. Video playback was not verified; the home-page flow exposes video download. The other five samples and Bilibili were not exercised in this UI session. No upload, publication, deployment, code changes, or Git write operation was performed.

Test downloads were moved out of the source tree to `/tmp/wechat-douyin-acceptance-20261127.mp4` and `/tmp/wechat-xhs-acceptance-20261127.png`. A transient malformed URL from UI input replacement produced an expected parse HTTP 400 and an error-report HTTP 400; this was excluded from valid-sample results. Moving temporary download artifacts out of the watched project triggered a developer-tools reload, after which the XHS failure was reproduced.

## Follow-up client fix and bounded validation

The failures above describe the original deployed-client behavior, not the final
client fix. Client commit `d24d47f` adds a shared two-transfer queue, windowed gallery
loading, visible bounded retry, local-file native preview and history unload guards.
No backend source/configuration change was needed for this fix.

The client Agent subsequently repeated the authorized 13-image developer-tool case:
the initial cover/current/adjacent requests were all HTTP 200 (three requests), moving
to the second image only loaded the next neighbor successfully, and all thirteen
full-screen preview preparation requests returned HTTP 200. Native preview displayed
the first image of thirteen using local temporary files, without new MEDIA_BUSY or
image-load errors. Opening native preview directly on remote URLs had failed during
the fix and was replaced; it is not assumed to obey the JavaScript transfer budget.

Final client tests: 69 passed, independently rerun by the coordinating session.
Middle/end gallery windows and same-length content reset have automated coverage;
they were not all individually exercised in the UI. This follow-up did not repeat
album saving or perform device/domain-check-enabled testing. Preview's 50-file/32 MiB
limits are application budgets only, not WeChat platform limits, and do not restrict
ordinary gallery browsing or saving. Old expired history covers need opening the
record and reparsing; retrying the same expired thumbnail URL cannot renew it.

No Mini Program upload/publication or VPS redeployment was performed for this fix.
