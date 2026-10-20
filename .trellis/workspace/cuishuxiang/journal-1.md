# Journal - cuishuxiang (Part 1)

> AI development session journal
> Started: 2026-10-18

---



## Session 1: Complete XHS parser VPS compatibility

**Date**: 2026-10-19
**Task**: Complete XHS parser VPS compatibility
**Branch**: `main`

### Summary

Completed the Xiaohongshu media parser implementation and local Docker validation. Diagnosed the VPS Live Photo failure as exact CDN host drift, added sns-video-v28 and sns-bak-v10/v11 allowlist entries with regression coverage, documented the redacted VPS case, and archived the implementation task. VPS deployment and caller integration remain operational follow-up checks.

### Git Commits

| Hash | Message |
|------|---------|
| `c2944e3` | (see git log) |
| `5ab8b93` | (see git log) |

### Status

[OK] **Completed**


## Session 2: Douyin parser implementation paused and archived

**Date**: 2026-10-20
**Task**: Douyin parser implementation paused and archived
**Branch**: `main`

### Summary

Implemented and locally validated controlled Douyin parsing and the unified API; fixed native-Linux Chromium HOME/Crashpad startup; archived at the user's request with target-VPS 60-second acquisition timeout explicitly unresolved.

### Main Changes

- Added unified Xiaohongshu/Douyin parsing, bounded anonymous Chromium acquisition, container controls, tests, and delivery evidence.
- Recorded rollback anchors and the VPS progression from Crashpad 502 to post-startup 504 timeout in the archived pause handoff.

### Git Commits

| Hash | Message |
|------|---------|
| `04037bd` | (see git log) |
| `be32fc7` | (see git log) |

### Testing

- [OK] 132 offline tests plus Ruff, mypy, dependency, OpenAPI/JSON, Compose, sandboxed Chromium, real local samples, and representative media reads passed.
- [OK] Target VPS Chromium launch passed after writable HOME/XDG fix; full Douyin acquisition still timed out under an independent 60-second deadline.

### Status

[OK] **Completed**

### Next Steps

- If resumed, restore the archived task context and run the staged proxy/commit/DOMContentLoaded diagnostic before changing the public 20-second timeout.


## Session 3: 审计小红书 HTTP 请求逻辑

**Date**: 2026-10-20
**Task**: 审计小红书 HTTP 请求逻辑
**Branch**: `main`

### Summary

完成公开接口、解析链路和历史请求逻辑审计；确认不存在闲置的第二套生产请求实现，用户决定保留现有生产链路与 probe 工具并结束任务。

### Main Changes

- 创建并归档分析任务，记录三个公开 HTTP 路由及其请求契约。
- 确认两个解析接口共同复用 XiaohongshuAdapter/XiaohongshuClient；未删除任何产品或探测代码。

### Git Commits

(No commits - planning session)

### Testing

- [OK] Trellis 任务校验通过；接口与契约相关测试 16 passed，此前小红书相关离线回归 86 passed。

### Status

[OK] **Completed**

### Next Steps

- 无；如未来要删除 probe 或调整接口能力，另建任务评审。
