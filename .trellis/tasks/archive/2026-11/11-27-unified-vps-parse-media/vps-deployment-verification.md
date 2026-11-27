# VPS deployment and live verification — 2026-11-27

## Deployed state

The user explicitly authorized commits/pushes in both owned repositories, VPS pulls, and deployment. Deployment was performed through the user's already-authenticated Termius session to `root@192.129.160.164` after desktop control recovered.

- Backend repository: `/var/ai_project/parse_video`, GitHub `paihuai00/parse_video`, deployed commit `fea3e7d` on `main`.
- Client repository: `/var/ai_project/video_download_mini`, GitHub `paihuai00/video_download_mini`, pulled commit `dfe6c9d`. The existing server checkout kept its `feat/error-email-reporting` branch name after a successful fast-forward pull from `origin/main`; no branch switch or force operation was used.
- Formal application: existing Compose API container `parse_video-api-1`, bound to `127.0.0.1:8000`.
- Public origin: `https://xiguahong.dpdns.org`; publication enabled with a separately generated server-only signing key, stored only on the VPS.
- Container health is `healthy`; UID/GID remains `10001:10001`; root filesystem remains read-only. Existing resource limits, sandbox policy and one-worker configuration were retained.
- Nginx configuration passed `nginx -t` before/after cutover and was reloaded. The existing HTTPS site received only the media location and named media-error responses from the repository template. Media buffering/cache/temp spill are disabled. A safe media access log excludes URI/query; the media location suppresses URL-bearing error logs.
- Existing Node/reporting service was not restarted. WeChat Mini Program upload/publication was not performed.

## Backups and cutover

Before building, the running old image was tagged `parser-video:before-unified-20261127-064921`. Previous application environment, Nginx site and rollback image metadata are in the private server directory:

`/var/backups/parse-video-unified-20261127-064921`

The new image was built on the VPS. A temporary candidate container, using the same non-root/read-only/memory/sandbox constraints, listened only on `127.0.0.1:18001`. It passed live checks before formal replacement and was stopped at cutover. The cutover script prepared automatic restoration of the old environment, Nginx site and image if startup or configuration validation failed; rollback was not triggered or exercised.

Unrelated local/VPS Trellis edits and untracked Node environment/dependency files were preserved. No credentials were committed. The two functional commits were pushed earlier; this report records subsequent deployment evidence.

## Live evidence

All seven unique, user-supplied samples were exercised against real providers/CDNs, not mocks.

| Target | Parsing | Full media GET | Transferred bytes |
| --- | --- | --- | --- |
| VPS candidate (loopback) | 7/7 | 25/25 | 47,657,775 |
| Formal HTTPS origin, requested from VPS through Cloudflare/Nginx | 7/7 | 25/25 | 47,657,775 |
| Independent Mac client against formal HTTPS origin | 2/2 (Douyin + XHS) | 2/2 representative files | 1,661,805 |

The 25 files comprise six MP4 videos, thirteen article JPEGs, and six JPEG covers. cURL completed with exit code 0 and HTTP 200 without redirect-following enabled. File signatures, content types and declared lengths were checked. The independent Mac client additionally verified MP4/JPEG signatures. Normal HTTPS certificate verification was retained.

The seven work labels are: Douyin 挖挖 / 极目新闻 / 二手工程机械Lucy; XHS GitHub飙升榜 / 撒娇的噜噜 / 我知道你贵 / 你们就宠它吧. No dynamic-photo sample was returned; this run does not verify motion-photo behavior.

Private raw responses, headers, downloaded test files and machine-readable summaries remain under the backup directory's `candidate/` and `public/` subdirectories; logs contain only result summaries/request IDs. VPS test scripts are `/tmp/parse-video-vps-validate.py` and `/tmp/parse-video-vps-cutover.py`; `/tmp/parse-video-deploy-backup` points to the backup directory. Mac external-client evidence is `/tmp/parse-video-public-20261127/summary.json`. Test artifact retention does not change the application's streaming/no-permanent-media-storage behavior.

## Remaining acceptance

These results supersede earlier statements that deployment, real VPS/CDN access and Nginx runtime validation were unperformed. WeChat developer-tool, legal-domain-enabled real-device preview/save, cancellation/Range behavior on device, Bilibili/generic live samples and an actual rollback drill remain unverified. The task stays `in_progress` for remaining release gates. No Mini Program publication, task archive or journal entry was performed.
