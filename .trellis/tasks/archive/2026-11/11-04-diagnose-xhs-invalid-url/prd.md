# 分析小红书短链 INVALID_URL

## Goal

只读排查用户授权短链请求的 INVALID_URL，区分入口、DNS 和重定向失败，形成诊断记录；不修改产品代码或部署。

## Requirements

- Read the existing API contract, URL/DNS validation, redirect flow, and prior diagnosis.
- Recheck the supplied public API and trace only the user-authorized short link with bounded anonymous requests.
- Persist redacted findings and identify the smallest justified next action.
- Analysis only: no product-code or deployment changes, full media downloads, or persistence of access-significant URLs, cookies, or API keys.

## Acceptance Criteria

- [x] Confirm whether current source accepts the initial URL shape.
- [x] Capture current public endpoint behavior or report an access limitation.
- [x] Identify the local failing validation stage if reproducible; separate it from server-side hypotheses.
- [x] Save a redacted diagnosis with source references and practical next actions.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
