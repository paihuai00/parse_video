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
