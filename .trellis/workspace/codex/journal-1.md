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
