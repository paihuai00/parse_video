# 小红书 NETWORK_ERROR 排查记录

复测日期：2026-10-31，本机 macOS arm64。用户已授权分析原链接并创建任务；随后要求启动本地服务供其测试。产品代码未修改。

## 最终收敛结论

用户已确认服务器问题修复，并要求收敛任务。服务器 Codex 的反馈为：后端正常，Nginx inactive，没有监听公网端口。本会话对公网接口与 `/healthz` 的普通 curl 实测均返回 Cloudflare HTTP 521，未取得后端 JSON 或 request ID；这与源站接入层未启动的现象吻合。

服务器公网失败的已确认故障层为 Cloudflare → 源站 Nginx。直接访问后端 8000 端口绕过 Nginx，因此后端正常与公网失败可以同时发生。`nginx -t` 只检查配置，Docker Compose 只管理已定义的容器，都不能证明宿主机 Nginx 已运行。Nginx 最初为何 inactive（未启动、未自启或被停止）没有日志证据，保持未知。

服务器端修复结果由用户确认，本会话未登录服务器、执行远程启停或修改远程配置。没有修复后的独立公网复测数据；不将用户确认描述为本机执行过的远程操作。小程序将具体 HTTP 错误映射为 `NETWORK_ERROR` 仍属推断，未取得客户端代码验证，也不能严格证明最初 10 月 30 日日志与当前 521 是同一次故障。

以下首条样本的 CDN 白名单缺口是另一个独立发现，未修改产品代码；此次关闭的是排查与运行验证任务，不代表已经修复该兼容问题。其与登录跳转分类问题均保留为后续可选范围，不阻塞本次分析归档。

### 公网测试证据

- 成功的本地样本对应公网旧接口 POST：HTTP 521，耗时约 1.221 秒，`Server: cloudflare`，响应 `error code: 521`，CF-Ray `a53021e5e97269e8-SEA`。
- 普通 curl 的公网 `/healthz`：HTTP 521，CF-Ray `a53022444f8b4311-LAX`；响应 Date 为 `2026-10-31 05:07:02 GMT`。
- Python urllib 的同域名请求另观察到 HTTP 403 / Cloudflare 1010（客户端特征限制），与系统 curl 的 521 为不同结果，不能混为后端业务错误。

### 运维经验

部署验收需要分别检查后端健康、Nginx 服务状态、实际 80/443 监听、公网精确接口路径，以及云安全组/防火墙和 Cloudflare 源站配置。配置检查成功不等于服务可用；容器健康不等于公网入口可用。后续日志诊断应保留原始 HTTP 状态、业务错误码、request ID 或 Cloudflare Ray ID，并区分代理错误与应用错误。

## 首条样本的独立解析结论

使用项目固定的 Python 3.12、`curl_cffi==0.13.0`、`chrome136` 和真实 FastAPI 应用复现：短链 302 → 详情页 200 → HTTP 502 `MEDIA_NOT_FOUND`。该笔记实际为 `type=normal`、5 张 Live Photo，顶层普通视频为空。页面获取和状态解码均成功。

5 张图片的 H.264 动态流主地址均使用 `sns-video-qc.xhscdn.com`，备用地址均使用 `sns-bak-v6.xhscdn.com`，路径均具有 `.mp4` 后缀。两个精确主机不在 `app/parser/media.py:11` 的白名单中，`normalize_media_url()` 将地址过滤为空，最终在 `app/parser/media.py:258` 抛出 `MEDIA_NOT_FOUND`，内部原因 `declared Live Photo has no supported MP4`。

这是当前环境已确认的解析阻断原因，不能在缺少线上证据时认定它就是 10 月 30 日事件的完整根因。

## 当前调用链

`POST /api/v1/parse`（自动识别平台）或旧 `POST /api/v1/xiaohongshu/parse` → API Key 校验 → `ParseService`（限流、成功缓存、请求合并、并发与排队、20 秒总 deadline）→ `XiaohongshuAdapter` → `XiaohongshuClient`（逐跳 URL/DNS 校验、绑定公网 IP、匿名会话和 TLS 验证）→ 提取 `window.__INITIAL_STATE__` → 按 note ID 选择 → 媒体归一化 → API 响应。

错误不进入成功缓存。Live Photo 无法取得受支持动态流时整篇失败，是现有契约要求，不应通过静默退化为静态图片来规避。

## 验证证据

### 固定运行时的完整 API 请求

- 通过 FastAPI TestClient 调用真实解析服务，未替换 DNS、HTTP 响应或解析结果；仅包装方法记录脱敏阶段信息。
- 短链与详情页均通过公网 DNS 检查。
- 上游响应分别为 302、200。
- 本机完整 API 耗时约 0.598 秒；服务日志耗时 584.32 ms。
- 结果：HTTP 502，`error.code=MEDIA_NOT_FOUND`，`retryable=false`。
- 本机 request ID：`25144917-ff7b-470c-bc36-d84324bcc46c`，仅用于本次复测，不关联历史线上事件。

### 不落盘的对照实验

同一次匿名抓取的数据，仅在独立 Python 进程内临时扩展 `ALLOWED_MEDIA_HOSTS` 为原集合加上述两个精确主机；进程退出后恢复，不修改源代码：

- 归一化成功，`kind=image`。
- 图片数 5，嵌套 Live Photo 数 5，顶层普通视频数 0。
- 独立对两个主机各取一个代表性媒体，验证 DNS 全部为公网地址并用 `CurlOpt.RESOLVE` 绑定，TLS 校验开启，禁用代理与自动跳转，发送 Range 请求。
- 两者均返回 HTTP 206、`Content-Type: video/mp4`；各检查 1024 字节，均具有 MP4 `ftyp` 文件头。
- 未进行完整媒体下载，未将 HTML、分享查询参数或签名媒体 URL 保存到仓库。

### 现有测试

执行以下定向检查：

```sh
/tmp/parse-video-runtime-20261031/bin/pytest -q \
  tests/test_client.py tests/test_url_rules.py tests/test_parse_service.py \
  tests/test_api.py tests/test_state_reader.py tests/test_media.py tests/test_logging.py
```

结果：83 passed in 4.24s。现有测试没有上述两个真实 CDN 主机的兼容样本，无法捕获本次缺口。未修改代码，未运行浏览器相关测试；本轮也不涉及抖音浏览器。

## NETWORK_ERROR 的来源仍需客户端/线上证据

- `app/errors.py:7` 的公共错误定义不包含 `NETWORK_ERROR` 或“网络异常，请稍后重试”。
- `app/api/error_handlers.py:24` 返回结构为 `success/data/error/meta`，保留真实错误码和 request ID。
- 本仓库没有小程序 `pages/index/index`、`onParse` 或版本 1.6.3 的客户端代码。
- 因此用户日志来自另一层包装；客户端或中间层把非 2xx/异常统一转换为 `NETWORK_ERROR` 是合理推断，尚未经代码证实。也不能排除历史事件中的真实网络错误。
- 用户日志的 `receivedAt` 为 2026-10-30 04:50:26.560 UTC，即北京时间 12:50:26.560；它是上报接收时间，不一定等于请求发生时间。
- 仍需该时间附近的服务日志 `status/outcome_code/duration_ms/request_id` 和客户端 HTTP 错误处理，确认线上是否同为 `MEDIA_NOT_FOUND`。已向用户请求；用户当前选择先本地测试。

## 次要问题：登录跳转错误分类

普通系统 curl（与项目固定指纹不同，且该探测逐跳未维护匿名 Cookie 会话）观察到详情页返回 302 到 `/login`。这只是不同请求组合下的表现，不是固定运行时请求的结果。

代码可独立确认：`app/parser/client.py:157` 遇到重定向只更新 `current_url` 并进入下一轮；`app/parser/client.py:105` 先调用 `resolve_url()`，后者的笔记路径规则拒绝 `/login`（`app/parser/url_rules.py:79`），返回 `INVALID_URL`。后面的 `classify_page()` 虽支持登录分类，但在这种跳转链中无法执行。现有 `test_page_classification` 只直接调用分类函数，未覆盖完整的登录重定向。

这是独立的错误分类缺陷，不是本次固定运行时 `MEDIA_NOT_FOUND` 的原因。

## 建议的最小后续修复

1. 根据当前真实页面与有界文件头证据，仅新增两个精确媒体主机 `sns-video-qc.xhscdn.com`、`sns-bak-v6.xhscdn.com`，保留全部现有 URL、DNS、TLS 和格式限制。
2. 增加脱敏 Live Photo 回归样本：新主地址成功、主地址不可用时受支持备用地址成功、未知主机仍拒绝、5 张图片的动态部分及顺序均保留。
3. 客户端保留后端 `error.code` 和 `meta.request_id`；仅真实请求传输失败使用 `NETWORK_ERROR`。实施需要客户端代码。
4. 登录重定向分类单独修复：在已验证目标主机、协议、端口后识别登录跳转，不通过扩大可抓取路径解决。

## 本地测试环境

- 为避免更改项目依赖，在 `/tmp/parse-video-runtime-20261031` 创建 Python 3.12.16 环境，严格安装 `requirements-dev.lock`。
- 启动命令：`XHS_ENV=development XHS_API_KEY='<独立本地测试密钥>' /tmp/parse-video-runtime-20261031/bin/uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 --workers 1`。
- 仅监听本机回环地址；使用独立本地测试密钥，不记录密钥值，不使用生产密钥。
- 服务仍运行当前代码；未应用上述建议修复。浏览器依赖包已安装，尚未安装 Playwright Chromium，因此本地验证范围为小红书。
- 启动后通过独立 HTTP 请求验证：`GET /healthz` 为 200 / `{"status":"ok"}`；原链接 `POST /api/v1/parse` 为 502 / `MEDIA_NOT_FOUND`，request ID `b4e9b3c3-589c-499c-aef8-444cd97a567e`。


## Docker 构建跟进

用户切换到 Docker 后在基础镜像 metadata 获取阶段出现 `DeadlineExceeded`。本机 Docker Desktop 正常，最初没有任何缓存镜像；命令行访问 `registry-1.docker.io`、`auth.docker.io` 均在 5 秒连接时限内超时。随后实际执行 `docker pull python:3.12.8-slim-bookworm` 成功，镜像 digest 为 `sha256:2199a62885a12290dc9c5be3ca0681d367576ab7bf037da120e564723292a2f0`。继续构建时 metadata 阶段耗时 0 秒，进入 pip 依赖下载。因此首次失败与镜像仓库网络访问相关，非应用解析代码错误；终端直连失败不代表 Docker 自身拉取一定失败。

Compose 环境最初未设置 API Key。已在 Git 忽略的本地 `.env` 中设置用户明确指定的测试密钥，并限制文件权限为 0600；此处不保存密钥值。未修改 Dockerfile、Compose、Docker Desktop 网络设置或镜像源。


### Docker 最终结果

- `docker compose --progress plain build` 完整成功，pip、Debian 系统依赖、Chromium 和 FFmpeg 均安装完成。
- 应用镜像 `parser-video:0.1.0` 已生成；镜像配置 digest `sha256:2ad89f1f216f511ec9cddd0ac5b08c815f55d734638ba8726a3b834fda0cbfe5`。
- 已正常停止此前主机上 PID 3280 的 Uvicorn，释放 8000 端口。
- `docker compose up -d --no-build --wait --wait-timeout 60` 成功，容器 `parse_video-api-1` 为 Healthy。
- 独立 HTTP 健康检查：200，`status=ok`。
- 使用用户最新提供的第二条短链和其指定的 API Key 调用统一接口：HTTP 200，`success=true`，图片数 1，Live Photo 数 1，顶层视频数 0；request ID `d77e1c48-c35a-49e9-a617-6ee7f47253d8`。
- 当前 127.0.0.1:8000 由 Docker Compose 容器提供服务；此前临时 Python 服务已停止。
- 首条短链的两个 CDN 主机白名单兼容问题仍未修改。第二条短链成功不代表第一条已修复。
