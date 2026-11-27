# Local live-sample verification — 2026-11-27

## Target and method

Current working-tree source ran in the existing Python 3.12.16 `.venv` with Uvicorn, one worker, bound only to `127.0.0.1:8001`. The pre-existing Docker service on port 8000 was left running. Media publication was enabled for this process with a new ephemeral signing key. No production configuration or source was changed.

The configured public origin is `https://localhost`. Tests deliberately mapped each issued media path/query to `http://127.0.0.1:8001`; the same local media route performed actual upstream retrieval and streaming. This verifies local HTTP behavior, not public HTTPS, Nginx, VPS networking, or WeChat device/domain compatibility.

All HTTP calls used cURL with explicit timeouts. Seven unique user-authorized links were tested; the duplicate GitHub share text was deduplicated.

## Results

| Sample | Content | Parse HTTP | Parse seconds | Media GET |
| --- | --- | --- | --- | --- |
| dy1: 挖挖 | 0 images / 1 videos | 200 | 3.19 | 2/2 |
| dy2: 极目新闻 | 0 images / 1 videos | 200 | 3.96 | 2/2 |
| dy3: 二手工程机械Lucy | 0 images / 1 videos | 200 | 2.86 | 2/2 |
| xhs1: GitHub飙升榜 | 13 images / 0 videos | 200 | 0.66 | 13/13 |
| xhs2: 撒娇的噜噜 | 0 images / 1 videos | 200 | 0.67 | 2/2 |
| xhs3: 我知道你贵 | 0 images / 1 videos | 200 | 0.56 | 2/2 |
| xhs4: 你们就宠它吧 | 0 images / 1 videos | 200 | 0.63 | 2/2 |

- Parsing: 7/7 real upstream requests succeeded. Returned titles matched the supplied work descriptions. No motion-bearing sample was returned.
- Media GET: 25/25 succeeded: 6 MP4 videos, 13 JPEG article images, 6 JPEG covers. Total 47,657,914 bytes.
- Each media request returned 200 directly without a client CDN redirect. cURL exited 0; MIME type, file magic, and declared Content-Length (when present) matched. No full codec decode or device playback was performed.
- HEAD: 7/7 representative media requests returned 200.
- Cache: a repeated non-refresh parse hit the cache and issued different media credentials.
- Health 200, missing-key 401, invalid input 400, invalid media credential 403 all matched expectations.

## Reproduction and artifacts

Import `local-live-samples.postman_collection.json` from this task directory. Its local development key is `local-test-key`. Run folders in order; each parse saves newly issued media URLs and maps their origin to `baseUrl` for local downloads. No production credentials are included.

Raw parse responses, request IDs, response headers, full downloaded files, cURL scripts and JSON summaries remain in `/tmp/parse-video-local-20261127/` (private directory). Temporary media files are test artifacts, not application caching. The background service PID is stored in that directory as `server.pid`; `server.log` contains sanitized application logs.

The service was left running for user inspection. Ephemeral credentials expire after 30 minutes or a server restart; reparse to obtain fresh ones.

## Remaining release checks

Real VPS/provider/CDN network behavior, Nginx configuration, production TLS, WeChat legal domains and real-device behavior remain unverified. The task stays in progress; no deployment, archive, journal, or Git write operation was performed.
