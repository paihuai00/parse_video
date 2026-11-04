# 小红书短链 INVALID_URL 诊断

日期：2026-11-04。范围：分析用户授权的单条手机短链及公网旧接口；未修改产品代码或部署。

## 结论

初始链接格式被当前代码支持。实际复现的失败发生于上游重定向后的路径校验：短链 302 → 标准笔记详情页 302 → 同主机 `/404` → `INVALID_URL`，内部原因是 `unsupported note path`。

该链路在项目实际 `XiaohongshuClient`、固定 `curl_cffi==0.13.0`、`chrome136`、匿名 Cookie 会话、关闭环境代理、逐跳 DNS 公网验证、地址绑定、TLS 校验和原始 20 秒总期限下复现。重定向到 `/404` 后在路径校验阶段停止，未请求该页。不能仅凭路径名称或 302 状态认定原笔记已删除，也不能证明当前笔记可匿名解析。

本机运行环境为 Python 3.15.2，项目声明支持 Python 3.12。此前临时 3.12 环境已不存在，Docker daemon 未运行。本次为诊断创建了独立 `/tmp/parse-video-diagnosis-20261104` 环境，没有修改项目依赖；不能将这些结果描述为完整生产环境验证。

## 公网接口证据

系统 curl 重放用户提供的旧接口 POST：HTTP 400，`error.code=INVALID_URL`，`retryable=false`，耗时 2.519 秒。新 request ID：`6e8d54ee-6ccd-4ba3-be6f-47a4a40d367c`。

Postman CLI 1.80.0 对相同接口亦取得相同业务 envelope，request ID：`b1a78f1e-a5f8-476c-ab0b-9ef25c7efe1c`，CLI exit 1。response-only 输出没有报告断言计数，因此不宣称内联断言已通过。没有初始化、绑定或上传 Postman 工作区。

未登录服务器或取得线上上游追踪。公网和本地错误一致，支持同类缺陷解释；服务器是否走完全相同的 `/404` 跳转链，仍需在服务器出口使用同样的脱敏逐跳探测确认。

## 本地证据与代码路径

1. 直接调用 `parse_url()`：用户原始输入被接受，`host=xhslink.cn`、`is_short_link=true`。入口规则在 `app/parser/url_rules.py:68`。
2. 普通系统 curl 的有界、逐跳公网 DNS 校验探测：短链 302 → 标准详情页 302 → `/login`。这次请求没有项目指纹或跨请求匿名 Cookie 会话，与项目客户端结果分开记录。
3. 项目客户端第一次探测：短链 302 → 详情页 302 → 非笔记状态页；验证失败 `unsupported note path`。各已连接主机 DNS 全部为公网地址。
4. 为消除状态页路径未知，再做一次相同客户端探测，明确目标为 `www.xiaohongshu.com/404`，仍得到 `INVALID_URL`。
5. `app/parser/client.py:157` 在 302 时只构造下一跳并继续；`app/parser/client.py:105` 调用 `resolve_url()`，后者在 DNS 前调用 `parse_url()`。`app/parser/url_rules.py:79` 只接受标准笔记路径，故 `/404` 和 `/login` 都会失败。
6. `classify_page()` 在 `app/parser/client.py:180` 才执行，无法处理被前置路径校验拦截的状态页；现有 404/登录页面分类不能覆盖这条重定向链。
7. `app/api/error_handlers.py:24` 仅公开固定消息，不包含内部 detail，因此错误响应表面上像用户传入了无效链接。
8. `refresh=true` 只跳过结果缓存，见 `app/services/parse_service.py:61`；不会改变 URL 或重定向校验，不能解决本次失败。

原链接、note ID、分享查询值、API Key、Cookie、HTML 和媒体 URL 未保存到该记录。

## 验证

`/tmp/parse-video-diagnosis-20261104/bin/pytest -q tests/test_url_rules.py tests/test_client.py`

结果：45 passed，73 条 Python 3.15 asyncio 弃用警告。未运行全套 API、媒体或浏览器测试。现有登录测试直接调用分类函数；缺少短链 → 详情页 → 登录/错误页的完整回归覆盖。

## 建议的最小修复范围

- 保持用户入口、精确主机、协议、端口、DNS 公网地址、地址绑定及重定向预算限制。
- 将上游状态跳转与用户输入格式错误分开处理。对合法详情页响应中的重定向，先验证目标主机、协议和端口，再按有证据的上游状态映射错误；不要把 `/404`、`/login` 当作可提交的笔记路径，也不要放开任意路径或自动跟随。
- 已确认登录目标可映射 `UPSTREAM_LOGIN_REQUIRED`；只有明确的缺失语义才映射 `NOTE_NOT_FOUND`。未知 `/404` 状态或未识别错误参数保持通用上游错误，例如 `UPSTREAM_BAD_RESPONSE`，直到有证据支持更精确的分类。
- 增加短链 → 详情页 → `/404`、登录目标、外站/私网危险目标的回归测试，并保留正常详情页和缓存行为覆盖。
- 修正错误分类只能改善返回语义，不能保证该笔记会恢复匿名访问。若需要确认公网根因，可在服务器出口重放一次相同指纹的脱敏逐跳探测，并结合本次 request ID 查日志。
