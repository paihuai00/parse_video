# Journal - codex (Part 1)

> AI development session journal
> Started: 2026-10-31

---



## Session 1: 小红书解析故障排查与公网入口收敛

**Date**: 2026-10-31
**Task**: 小红书解析故障排查与公网入口收敛
**Branch**: `main`

### Summary

完成小红书解析链路分析、本地 Docker 启动及真实样本验证；公网 curl 复现 Cloudflare 521，结合服务器 Nginx inactive 反馈确定公网接入层故障，用户确认修复后归档。未修改产品代码。

### Main Changes

- 归档排查任务与脱敏证据，区分公网 Nginx 故障和首条样本独立 CDN 白名单兼容问题。

### Git Commits

(No commits - planning session)

### Testing

- [OK] 既有定向测试 83 passed；本地 Docker healthy，最新样本 HTTP 200，1 张 Live Photo。
- [OK] 公网修复前 POST 与 healthz 均返回 Cloudflare 521；服务器修复成功由用户确认。

### Status

[OK] **Completed**


## Session 2: 小红书 INVALID_URL 跳转诊断

**Date**: 2026-11-04
**Task**: 小红书 INVALID_URL 跳转诊断
**Branch**: `main`

### Summary

公网复现 HTTP 400；当前代码接受手机短链。项目固定 curl_cffi/Chrome 指纹本地复现详情页跳转 /404 后被路径校验误报 INVALID_URL，普通 curl 则跳转登录页。45 项 URL/客户端测试通过；Python 3.15 诊断环境与项目 3.12 有差异。只记录分析，未修改产品代码或部署。

### Git Commits

(No commits - planning session)

### Status

[OK] **Completed**

### Next Steps

- 如需实施，单独修复上游状态跳转错误分类并增加完整跳转链回归测试；线上具体跳转仍需服务器出口证据。


## Session 3: 小红书匿名移动页修复完成与部署移交

**Date**: 2026-11-05
**Task**: 小红书匿名移动页修复完成与部署移交
**Branch**: `main`

### Summary

实现有界iOS匿名兜底、移动状态及完整静态图片适配；190项离线检查和独立复核通过，原始短/长链本地API及JPEG检查通过。用户确认本地Postman正常，明确要求归档并自行Git提交；归档和journal均禁用自动提交，VPS部署与剩余媒体/API/调用方验收移交用户VPS Codex。

### Main Changes

- 已归档11-04-xhs-share-access-compatibility；未执行git add/commit/push。

### Git Commits

(No commits - planning session)

### Testing

- [OK] Python3.12.16：190 passed；Ruff/Mypy/compile/OpenAPI/Compose静态检查通过；本地真实API和Postman CLI成功。

### Status

[OK] **Completed**

### Next Steps

- 用户手动提交并同步VPS；按部署prompt保留旧镜像、重建并重建容器、核对源码和镜像、执行VPS媒体及公网验收，失败回滚。


## Session 4: Fix exact Live Photo CDN host compatibility

**Date**: 2026-11-06
**Task**: Fix exact Live Photo CDN host compatibility
**Branch**: `main`

### Summary

Added three observed exact Live Photo video hosts after bounded HTTPS MP4 header verification. Added 29 offline regressions; full suite 236 passed; Ruff, Mypy, compilation, OpenAPI JSON and diff checks passed. Restarted local development service; authorized real request returned one image with one paired motion MP4 and cache miss. No new task, VPS changes or Git writes.

### Git Commits

(No commits - planning session)

### Status

[OK] **Completed**


## Session 5: Handle bounded rednote Set state serialization

**Date**: 2026-11-06
**Task**: Handle bounded rednote Set state serialization
**Branch**: `main`

### Summary

Verified extraction succeeds before decoding fails on synthetic new Set(array). Added string-aware data-only Set wrapper normalization, exact source-size enforcement and 50 offline regressions. Full suite 286 passed; Ruff, Mypy, compilation, OpenAPI JSON and whitespace checks passed. Three authorized live samples passed via independent ASGI app; local responses did not reach rednote, so VPS recovery remains unverified. Added explicit synthetic fixture and VPS verification steps. No Git writes, new task, service restart or deployment.

### Git Commits

(No commits - planning session)

### Status

[OK] **Completed**


## Session 6: Recover bounded empty detail responses with complete mobile motion

**Date**: 2026-11-06
**Task**: Recover bounded empty detail responses with complete mobile motion
**Branch**: `main`

### Summary

Reproduced both user failures as checked HTTP 200 text/plain zero-byte details, before Set parsing. Added typed one-shot mobile recovery on full checked detail URLs within shared attempts, redirects, identity and deadline checks; enabled mobile image motion only with complete detail still and shared supported MP4 pair. Full suite 309 passed; Ruff, Mypy, compilation, OpenAPI JSON and whitespace checks passed. Restarted local service; all three real refresh requests returned 200 including one paired Live Photo. Upstream later served desktop HTML again; deterministic empty-response branch evidence is synthetic. No Git writes, new task or VPS changes.

### Git Commits

(No commits - planning session)

### Status

[OK] **Completed**


## Session 7: Regional Live Photo video host repair and VPS release

**Date**: 2026-11-06
**Task**: Regional Live Photo video host repair and VPS release
**Branch**: `main`

### Summary

Validated and pushed f9dd538; fast-forwarded the same VPS repository, deployed API, and passed all three real parse ingress layers.

### Main Changes

- Added three exact video-only rednote CDN hosts and 47 regional regression cases; preserved existing configuration edits.

### Git Commits

- Work commit `f9dd538a2a7491e74988398258479502b38ff93d`, explicitly authorized, pushed and deployed. Journal helper auto-commit disabled.

### Testing

- [OK] 385 tests; Ruff; Mypy; compile; OpenAPI JSON; synthetic baseline/candidate; local real HTTP; deployed source hashes; VPS loopback, verified Nginx TLS and public HTTPS all passed.

### Status

[OK] **Completed**

### Next Steps

- Unknown media hosts remain rejected; investigate new candidates with bounded sanitized evidence.

### Deployment evidence

- New container: `df631ff18719`; image `sha256:570abd1e037a075b5e87aa0ec1512ea09bdfa742891aaa0866539f0b195541f0`.
- Rollback image retained: `parser-video:rollback-20261106-before-f9dd538`.
- Running parser hashes matched; production configuration files and runtime environment unchanged.
- 2026-11-06 UTC: all refresh requests returned 200 JSON, cache miss, 4 images / 4 nested Live Photo MP4s / 0 top-level videos.
- VPS loopback, 13:38:21 UTC: `a8bef0e2-cf6e-46cb-8898-3c2ac1f1a302`, 2732 ms.
- Verified local Nginx HTTPS, 13:38:24 UTC: `72e98c5f-61af-46d0-a323-3164e5a0e767`, 1880 ms.
- Public HTTPS, 13:38:26 UTC: `f792d623-1647-4d5e-a9ff-98b543078ead`, 2664 ms.
- All request IDs matched successful application logs; both proxy requests matched Nginx logs.
- No new task created; existing unrelated planning tasks were not archived.


## Session 8: Confirmed deployed API and archived resolved diagnosis

**Date**: 2026-11-06
**Task**: Confirmed deployed API and archived resolved diagnosis
**Branch**: `main`

### Summary

Confirmed f9dd538 API container rebuilt at 2026-11-06 13:36:56 UTC and remains running/healthy. Final public parse recheck passed; archived the local diagnosis and VPS counterpart/evidence tasks with --no-commit.

### Main Changes

- Archived 10-31-xhs-server-diagnosis with completion evidence; preserved original edits and disabled automatic session commits on both machines.

### Git Commits

(No commits - planning session)

### Testing

- [OK] 2026-11-06 13:48:44 UTC: public HTTP 200 JSON, cache miss, 4 images, 4 Live Photo MP4s, zero top-level videos. Request e443efb3-cc75-4493-b8e3-3a4e0d9d2a7c matched application log.

### Status

[OK] **Completed**


## Session 9: 抖音普通视频接入移动分享页 HTTP 解析

**Date**: 2026-11-24
**Task**: 抖音普通视频接入移动分享页 HTTP 解析
**Branch**: `main`

### Summary

统一接口自动区分抖音和小红书，本机 Docker 可用，抖音视频返回可独立下载的 MP4 直链。

### Main Changes

- 接入匿名移动分享页采集，支持实测的精确 CDN，保留图文解析与安全回退。
- 补充 Postman Collection、部署说明和 Trellis 服务契约。

### Git Commits

(No commits - planning session)

### Testing

- [OK] Ruff、mypy、403 项 pytest 与本机 13 条 Postman 断言通过。
- [OK] 两条抖音视频完整下载并解码，三条小红书短链通过两个入口，抖音动态图文返回预期的 422。

### Status

[OK] **Completed**

### Next Steps

- 迁移到 VPS 后复验真实出口网络和调用方媒体下载。


## Session 10: 统一 VPS 解析进展同步与旧任务收尾

**Date**: 2026-11-27
**Task**: 统一 VPS 解析进展同步与旧任务收尾
**Branch**: `main`

### Summary

同步已有部署和验收证据及任务路径，当前统一解析任务保留进行中，不新增部署或 Git 写操作。

### Main Changes

- 同步 PRD、设计、实施清单、验证记录和 relatedFiles，纠正正式发布前启用生产中转的顺序。

### Git Commits

(No commits - planning session)

### Testing

- [OK] 核对既有 489 后端测试、69 客户端测试、VPS 七条解析和25个完整下载及 Nginx 验证记录；本轮未重跑全量测试。

### Status

[OK] **Completed**

### Next Steps

- 保留真机域名校验与修复后相册保存、B站/通用/动态图文线上覆盖、正式发布和回滚演练。


## Session 11: 统一 VPS 后端开发完成归档

**Date**: 2026-11-27
**Task**: 统一 VPS 后端开发完成归档
**Branch**: `main`

### Summary

按用户确认将后端任务以开发完成归档；未验收的真机、来源、发布与回滚事项由独立上线验收任务承接，未标记通过。

### Main Changes

- 保留489项测试、VPS/Nginx及七条解析25个完整下载的已有证据，完成路径与后续任务关联。

### Git Commits

(No commits - planning session)

### Testing

- [OK] 本轮仅验证记录、引用及任务状态，不重跑测试或执行线上操作。

### Status

[OK] **Completed**

### Next Steps

- 跟踪小程序仓库11-27-unified-vps-release-acceptance验收任务，发布和线上操作仍需相应授权。
