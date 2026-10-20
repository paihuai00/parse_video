# 当前小红书解析逻辑

## 1. 结论摘要

当前实现不是调用小红书开放 API，而是使用新建的匿名 `curl_cffi` 会话抓取分享页 HTML，从 `window.__INITIAL_STATE__` 中精确取出请求 note ID 对应的数据，再把图片、Live Photo 和普通视频归一化为统一内部模型。返回的是上游 CDN 临时直链，服务本身不代理、保存、转码或实时验证媒体。

整体分层清晰，安全边界也偏保守：URL、DNS、重定向、HTML 大小、JSON 深度/节点数、CDN 主机和 MP4 格式都采用 fail-closed 策略。最主要的已确认缺口在普通图文完整性：某个图片槽位无法得到合法 URL 时，代码会静默跳过而不是整篇失败，并对后续图片重新编号。

## 2. 调用链路

```text
HTTP 请求
  → FastAPI 请求边界（8 KiB body 上限、request_id、安全日志）
  → X-API-Key 鉴权
  → 旧入口固定小红书 / 统一入口自动识别平台
  → ParseService（限流 → 缓存 → 同 key 合并 → 并发/队列准入）
  → XiaohongshuAdapter
  → XiaohongshuClient（URL/DNS 校验、手动重定向、受限 HTML 获取）
  → state_reader（提取/解码 __INITIAL_STATE__、按 note_id 选择）
  → media.normalize_note（图片 / Live Photo / 普通视频）
  → InternalNote 成功缓存
  → 旧版或统一公开模型 + 每个调用新的 meta
```

### 2.1 HTTP 入口

- `app/api/routes.py:28-49`：旧入口直接调用 `ParseService.parse(...)`，默认 `platform="xiaohongshu"`。
- `app/api/routes.py:52-76`：统一入口先调 `detect_platform`；小红书 URL 最终仍进入同一 `XiaohongshuAdapter`。
- `app/api/auth.py:12-20`：通过常量时间比较校验本服务 `X-API-Key`，与小红书账号/Cookie 无关。
- `app/main.py:44-128`：请求边界限制 body 为 8 KiB，生成 `request_id`，仅记录路径、状态、耗时、结果码、note ID、缓存与准入计数，不记录完整 URL 和签名媒体地址。

### 2.2 共享调度

`app/services/parse_service.py:50-114` 的顺序是：

1. 用 API key 的 SHA-256 识别值执行滑动窗限流，限流在缓存之前，所以缓存命中也消耗额度。
2. 由适配器把完整规范化 URL（包含查询串）哈希成缓存 key；查询参数不会出现在 key 中，但不同访问 token 不会错用同一结果。
3. `refresh=false` 时先查成功结果 TTL/LRU 缓存；默认 TTL 120 秒、最多 256 条。错误不缓存。
4. 相同 key 的并发请求共享一个 leader task；每个 follower 仍占用有界 waiter 容量。最后一个调用者离开时，未完成的孤儿 task 会被取消并 await 清理。
5. leader 在 `AdmissionController` 中取得上游槽位；默认 2 个 active、4 个 waiting，队列最多等 2 秒。
6. 创建 `Deadline(20s)` 后，排队、DNS、重定向、重试、下载和解析共用剩余时间。

## 3. URL、DNS 与 HTML 获取

### 3.1 输入 URL

`app/parser/url_rules.py:14-122` 实施精确允许策略：

- 详情主机仅 `www.xiaohongshu.com` 和 `xiaohongshu.com`；路径仅 `/discovery/item/<24-hex-id>` 或 `/explore/<24-hex-id>`。
- 短链主机仅 `xhslink.com` 和 `xhslink.cn`；后者只允许 `/o/<ASCII URL-safe token>`。
- 只接受 HTTP/HTTPS 及对应默认端口；拒绝用户名/密码、IP 字面量、空白/控制字符、相似域名、非法路径和超过 4096 字符的 URL。
- 删除 fragment，保留原始 query，因为 `xsec_token` 等参数可能影响匿名访问。

### 3.2 DNS 与逐跳连接

- `app/parser/url_rules.py:125-155`：每一跳都重新解析 DNS；如果没有结果，或任一结果不是公网非组播地址，则拒绝连接。
- `app/parser/client.py:97-186`：使用手动重定向，每跳都先重新校验 URL/DNS，再用 `CurlOpt.RESOLVE` 把 TLS 主机绑定到刚验证的 IP 集合；禁用环境代理，保持 TLS 证书验证。
- 单次解析使用新建匿名 session，但同一次重定向链保留上游下发的 Cookie。
- 默认最多 3 次重定向；解压后 HTML 超过 2 MiB 立即中止。连接失败或可重试的上游错误最多重试 1 次，但不重置总 Deadline。
- 请求携带浏览器指纹仿写、中文优先的 `Accept-Language` 和小红书 `Referer`。

### 3.3 页面类型分类

`app/parser/client.py:50-70` 根据 HTTP 状态、最终路径和 HTML 关键词区分：

- 显式删除/不存在 → `NOTE_NOT_FOUND`。
- 登录页 → `UPSTREAM_LOGIN_REQUIRED`。
- 验证码/滑块/安全验证 → `UPSTREAM_ACCESS_RESTRICTED`。
- HTTP 429 或频控文案 → `UPSTREAM_RATE_LIMITED`。
- 其他 4xx/5xx → `UPSTREAM_BAD_RESPONSE`。

## 4. 状态提取

`app/parser/state_reader.py:23-159` 不执行页面 JavaScript，而是直接读取 HTML 内的状态赋值：

1. 查找真正的 `window.__INITIAL_STATE__ = ...` 赋值，跳过只是文本中出现的 marker。
2. 使用感知字符串和转义的括号匹配提取单个 JSON 值；限制 2 MiB 字符和 80 层嵌套。
3. 仅把值位置的 JavaScript `undefined` 替换为 JSON `null`，不会破坏字符串中的同名文本。
4. `json.loads` 后限制最多 200,000 个容器/值节点。
5. 只读取 `state.note.noteDetailMap[note_id].note`，不会使用页面里首个或推荐的其他笔记。

## 5. 媒体归一化

### 5.1 URL 边界

`app/parser/media.py:11-65` 只接受已有脱敏样本和回归支持的精确 CDN 主机：

- `sns-webpic-qc.xhscdn.com`
- `sns-video-v6.xhscdn.com`
- `sns-video-v28.xhscdn.com`
- `sns-bak-v11.xhscdn.com`
- `sns-bak-v10.xhscdn.com`

合法上游 HTTP URL 会归一为 HTTPS，保留路径和签名查询串。任意其他 `*.xhscdn.com` 子域不会因后缀相同而被接受。

### 5.2 普通图文与 Live Photo

- 普通图片按 `urlDefault` → `infoList[imageScene=WB_DFT].url` → `urlPre` 的优先级选取首个合法 URL（`app/parser/media.py:68-85`）。
- `livePhoto=true`、非空 `stream`、`livePhotoUrl` 或 `videoUrl` 任一存在就会标记为 Live Photo（`app/parser/media.py:209-220`）。
- Live Photo 必须同时得到静态图和 `stream` 内可正向证明为 MP4 的动态候选；否则整篇返回 `MEDIA_NOT_FOUND`，不静默降级为普通图（`app/parser/media.py:247-270`）。
- 成功时动态 MP4 嵌套在所属 `images[i].live_video`，不进入顶层 `videos`。

### 5.3 普通视频

- 仅从 `note.video.media.stream` 读取候选（`app/parser/media.py:201-206`）。
- 候选的 `format/container`、MIME 或 URL 路径至少一项必须正向证明 MP4，且不得是 m3u8（`app/parser/media.py:139-147`）。
- 每个候选先看 `masterUrl`，再看 `backupUrls`；所有合法候选先优先 H.264，再按分辨率、码率和宽度排序（`app/parser/media.py:117-198`）。
- 最终只返回一个 MP4；封面独立取自首张合法 `imageList` 图片。没有可支持 MP4 时失败，不仅返回封面。

## 6. 公开响应与错误

- 内部使用不可变 dataclass `InternalNote/InternalImage/InternalVideo/InternalCover`；HTTP 边界再转为禁止额外字段的 Pydantic 模型（`app/models.py:19-57`）。
- 旧入口保留 24 位十六进制 note ID 和小红书文案；统一入口另外接受抖音十进制 ID 并使用中性文案（`app/models.py:104-174`、`app/api/error_handlers.py:24-39`）。
- 图文：`images` 非空、顶层 `videos=[]`、`cover=null`；普通图片序列化时省略 `live_video`。
- 视频：`images=[]`、`videos` 恰好一个、`cover` 可空。
- 媒体均标记 `verification="not_checked"`，`url_expires_at=null`；缓存失效时间不等于 CDN URL 有效期承诺。
- 预期失败通过 `AppError` 稳定映射为 `INVALID_URL`、`NOTE_NOT_FOUND`、`UNSUPPORTED_CONTENT`、`UPSTREAM_*`、`PARSE_FAILED`、`MEDIA_NOT_FOUND`、`RATE_LIMITED`、`BUSY` 等统一 envelope；诊断细节不返回给调用方。

## 7. 已确认缺口：普通图片可被静默丢失

### 证据

`app/parser/media.py:243-274` 对 `imageList` 的处理存在两个静默跳过分支：

- 槽位不是 dict 时直接 `continue`。
- 普通图片的 `_image_url(item)` 返回 `None` 时，不报错也不保留占位。只有 Live Photo 缺静态图时会 fail-closed。

输出 `index` 使用 `len(normalized_images) + 1`（`app/parser/media.py:268`），所以被跳过槽位之后的图片还会被重新紧密编号。用 3 个输入槽位（合法、未允许主机、合法）调用 `normalize_note` 的本地重现结果为：

```text
{'input_slots': 3, 'output_slots': 2, 'indexes': [1, 2]}
```

这与 `README.md:3` 的“完整有序正文图片”、`docs/technical-design.md:33` 的“返回全部正文图片”，以及 `.trellis/spec/backend/service-contract.md:132` 的“partial image slots must fail closed”相冲突。现有 `tests/test_media.py` 覆盖了全部图片无效和 Live Photo 不完整，但没有“普通图文中间一张无效”的回归。

### 影响

- 调用方可能在成功响应中少拿一张或多张正文图，无法通过状态码感知内容不完整。
- `index` 不再表示上游原始槽位，会隐藏丢失位置。
- 新 CDN 主机尚未加入白名单时，这个缺口会把本应可见的上游漂移转化为静默的部分成功。

### 建议的后续修复

将每个上游 `imageList` 槽位视为必须交付的单元：任一槽位不是对象、没有合法静态图 URL，或 Live Photo 缺动态 MP4，都应使整篇返回 `MEDIA_NOT_FOUND`。同时增加“中间坏图”离线回归，防止局部成功再次出现。如产品希望允许部分成功，则需先显式修改公开契约并增加缺失标记，不应继续以完整成功响应表达。

## 8. 其他运行限制与风险

- **上游结构漂移**：实现依赖 `window.__INITIAL_STATE__` 和 `note.noteDetailMap[id].note`。字段调整会明确失败，不会自动退化到其他页面数据源。
- **精确 CDN 白名单**：安全性好，但新的合法 CDN 子域会被拒绝；必须先获取脱敏样本、确认语义并加回归。
- **页面分类是全文关键词启发式**：`classify_page` 会搜索整份 HTML 中的“captcha”、“登录后查看”等文本。它能快速识别挑战页，但如这些字样出现在正常内容或页面脚本中，理论上可能误分类。
- **媒体未验证**：解析器只校验 URL 格式/主机和 MP4 证据，不请求媒体文件；返回的地址可能已失效、对调用方网络不可达，或实际内容与元数据不符。
- **进程内状态**：缓存、限流、合并和准入计数都在单进程内实现，不能在未重新设计前通过多 worker 水平扩展。
- **离线回归不代表实时可用性**：固定 fixture 能验证契约和边界，但不能证明小红书当前仍允许匿名访问或字段未变。

## 9. 验证记录

使用项目 Python 3.12 虚拟环境执行：

```bash
.venv/bin/python -m pytest -q \
  tests/test_url_rules.py tests/test_client.py tests/test_state_reader.py \
  tests/test_media.py tests/test_parse_service.py tests/test_api.py tests/test_contract.py
```

结果：`86 passed in 0.61s`。本次没有访问真实小红书链接，也没有下载或播放媒体。
