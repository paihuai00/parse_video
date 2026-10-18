# 实施拆分与验收清单

状态日期：2026-10-18。P1–P4 的代码与交付文件已完成 88 项离线测试，本机 `linux/arm64` Docker 构建与运行验收及功能变更后重建均已通过；另有一篇授权 Live Photo 样本完成脱敏解析与有界文件头检查，一个授权手机短链样本确认 `xhslink.cn/o/<token>` 经一次安全跳转到标准详情页并由本地 API 成功解析。目标 VPS 环境和 P5 仍待部署验收。

## P0：方案和接口契约（本轮完成）

- [x] 验证匿名请求组合：curl_cffi 0.13.0 / chrome136。
- [x] 解析 5 篇样本并检查 20 个媒体地址的文件开头。
- [x] 明确纯 JSON、单链接、小流量、返回临时媒体直链的范围。
- [x] 编写技术方案、OpenAPI、响应示例、部署步骤和本清单。
- [x] 保存不含分享 token 或签名媒体 URL 的验证摘要。

交付：`README.md`、`docs/technical-design.md`、`docs/openapi.json`、`docs/examples/`、`docs/deployment.md`、`docs/evidence/`。

完成标准：契约语法有效，响应示例能通过相应 Schema，文档中的接口地址、配置和响应语义一致。

本轮检查结果：OpenAPI 3.1 校验通过；请求、图文、视频、错误 4 个示例均通过 Schema 校验。另验证 5 个应拒绝的输入/响应：视频缺少 MP4、空图文、混合媒体误报为视频、请求携带未支持的 Cookie 字段、将未检查的媒体标记为已验证。文档相对链接与脱敏验证记录均已检查。

## P1：解析核心与最早的 VPS 探测（代码和本地授权样本探测完成，VPS 待执行）

依赖：P0。

计划文件：

```text
app/config.py
app/errors.py
app/models.py
app/parser/url_rules.py
app/parser/client.py
app/parser/state_reader.py
app/parser/media.py
scripts/probe.py
tests/fixtures/
tests/test_url_rules.py
tests/test_state_reader.py
tests/test_media.py
```

任务：

- [x] 建立 Python 项目和精确依赖锁文件；保持已验证的 curl_cffi 和浏览器配置。
- [x] 将匿名请求封装为可取消、有超时和响应体上限的异步客户端。
- [x] 实现精确域名/路径校验、短链逐跳检查、公网目标检查。
- [x] 按真实手机复制样本兼容精确 `xhslink.cn/o/<token>`，并覆盖相似域名、其他 `.cn` 路径、危险跳转和缓存身份测试。
- [x] 安全读取初始数据，处理字符串外的 undefined；不执行网页脚本。
- [x] 将网页媒体转换为独立的内部模型；正文图片、与图片关联的 Live Photo 动态 MP4、普通主视频和封面分开。
- [x] 完成 MP4 选择规则和未知字段的 null 行为。
- [x] 对登录页、验证码、未知结构、多个 Live Photo、空动态流、缺少动态 MP4 和不支持直播建立离线夹具或分类测试；明确不存在由分类测试覆盖。
- [x] 提供小型探测入口，让部署者在 VPS 运行 1～2 条真实链接，提前发现出口或架构问题。
- [x] 使用一篇授权 Live Photo 样本验证 18 张图片、2 个动态 MP4 的配对结果，并分别对一个静态图与一个动态 MP4 读取 1024 字节文件头；未持久化 token 或媒体 URL。
- [x] 使用一个授权手机短链样本验证一次手动跳转到标准详情页，并由重建后的 API 成功解析 7 张均带动态 MP4 的图片；只记录脱敏主机/路径形态、查询键名和媒体计数，不持久化 token、查询值、笔记 ID、请求 ID 或媒体 URL。

验收：普通图文返回有序正文图片；Live Photo 图文保持静态图顺序并把一个动态 MP4 放入所属图片，缺少动态 MP4 时失败；普通视频各返回一个正确主视频及独立封面；缺少主视频时失败；非法输入不会访问非允许目标；VPS 探测结果被明确记录。

若 VPS 当前无法匿名访问，先保留错误原因并排查实际环境差异，不宣称换部署位置或换客户端一定能解决，也不默认添加账号会话。

## P2：JSON API（离线完成）

依赖：P1。

计划文件：

```text
app/main.py
app/api/routes.py
app/api/auth.py
app/api/error_handlers.py
tests/test_api.py
tests/test_contract.py
```

任务：

- [x] 实现 `POST /api/v1/xiaohongshu/parse` 和 `GET /healthz`。
- [x] 生产模式 API Key 必须配置；验证请求头，不接受请求体传登录 Cookie。
- [x] 使用 Pydantic 校验输入和输出，与设计契约保持一致。
- [x] 实现统一成功/失败信封；覆盖框架 404/405/参数校验及未知异常。
- [x] 请求 ID 贯穿响应和日志；任何异常不暴露堆栈、密钥或分享 token。
- [x] 明确 `verification=not_checked`、缓存时间和媒体到期时间不同的语义。
- [x] 增加可选、普通图片不输出的 `images[].live_video`；图文顶层 `videos` 语义不变，并同步 OpenAPI 与脱敏示例。

验收：图文、视频、空字段、错误和鉴权用例均通过契约校验；所有预期应用层响应为 JSON；日志中无凭证和签名地址。

## P3：小流量控制（离线完成）

依赖：P2。

计划文件：

```text
app/services/parse_service.py
app/services/cache.py
app/services/admission.py
app/services/rate_limit.py
tests/test_cache.py
tests/test_admission.py
tests/test_rate_limit.py
```

任务：

- [x] 单进程成功缓存，120 秒 TTL、256 条上限，过期可清理。
- [x] 缓存键包含链接访问参数的摘要；失败不缓存，旧结果不冒充刷新成功。
- [x] `refresh=true` 绕过缓存，仍遵守资源控制。
- [x] 同一缓存键并发请求合并；新鲜请求 ID 不复用旧响应 ID。
- [x] 2 个上游任务、4 个等待名额、最多等待 2 秒，整体请求最多 20 秒。
- [x] 每 API Key 每 60 秒最多 20 次，超额 429；繁忙 503；提供适当 Retry-After。
- [x] 超时、取消、断开连接后正确释放资源；限制缓存、等待者和限流表大小。

验收：用模拟上游验证并发和超时边界，不对小红书做负载压测。重复请求减少上游次数，取消一个等待者不会让其他请求失效。

## P4：Docker 交付（文件与本地容器验收完成，目标 VPS 待验证）

依赖：P3；P1 的早期 VPS 探测可提前执行。

计划文件：

```text
Dockerfile
compose.yaml
.dockerignore
.env.example
deploy/nginx.conf.example
requirements.lock（或等价锁定文件）
tests/test_health.py
```

任务：

- [x] Python 3.12 slim 镜像、非 root 配置、单 Uvicorn worker。
- [x] 配置环境变量、健康检查、自动重启和日志滚动。
- [x] 默认只映射主机回环地址，由现有 HTTPS 入口代理；不擅自覆盖已有服务。
- [x] 提供反向代理 JSON 错误模板，复用应用信封。
- [x] 在本机 Docker Desktop `linux/arm64` 完成镜像构建、非 root/单 worker 启动、缺失或空密钥启动失败、回环绑定、健康检查、内存上限和日志轮转配置验收。
- [ ] 验证 Linux 目标架构依赖安装、匿名请求以及容器重启行为。
- [x] 写明构建、启动、更新、保留旧镜像和回滚步骤。

验收：部署者可按 [部署说明](deployment.md) 完成启动；未配置密钥时生产启动失败；健康检查不访问上游；镜像/配置版本可追溯。

## P5：VPS 和实际调用方验收（待部署者执行）

依赖：P4。

- [ ] VPS 能处理用户提供的图文和视频样本，记录日期与结果。
- [ ] 从 VPS 读取代表性返回媒体的文件开头，确认类型与响应。
- [ ] 从真实调用方的网络访问同一批 URL，验证是否需要 Referer 及是否可下载。
- [ ] 再做一次完整短视频下载/播放检查，与仅文件头验证分开记录。
- [ ] 缓存命中与 refresh 行为符合文档，密钥错误、输入错误、限流和上游失败均为 JSON。
- [ ] HTTP 与 HTTPS 入口、代理错误、端口暴露和既有服务共存配置符合部署目标。
- [ ] 保存部署镜像标签和依赖版本，完成一次回滚演练。

若实际调用方不能使用返回直链，则记录为当前能力边界。媒体代理或对象存储会引入额外带宽/存储，应另行设计，不在本次纯直链 API 中悄悄加入。

## 实施顺序

P0 → P1 → 尽早在 VPS 探测 → P2 → P3 → P4 → P5。

目前不需要更多服务器信息即可开始 P1～P4。部署时再由你填入密钥、域名和端口；没有域名时先使用本机端口或 SSH 隧道验证，再接入 HTTPS。
