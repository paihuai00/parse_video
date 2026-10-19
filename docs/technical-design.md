# 技术方案与已验证细节

日期：2026-10-18（Asia/Shanghai）。状态：P1–P4 已实现并通过离线测试；授权 Live Photo 与手机短链样本已完成本地真实网络脱敏探测，VPS 验收待执行。

## 1. 范围与当前事实

第一版是单台 VPS 上的同步 HTTP JSON API。调用者提交一条小红书链接，服务返回有序图片、与图片一一关联的 Live Photo 动态 MP4，或普通视频笔记的主 MP4 地址。用户已经安装 Docker，将自行部署。

仓库已交付 FastAPI 应用、解析核心、单进程资源控制、离线测试、探测脚本和 Docker/Compose/Nginx 文件。当前未连接 VPS；一篇用户授权的 Live Photo 分享链接已在本地完成脱敏解析及有界文件头检查，一个授权 `xhslink.cn/o/<token>` 样本已确认一次受控跳转可到达标准详情页。部署相关参数是可调整的初始值，不是平台公布的限额或性能承诺。

### 已验证的匿名访问组合

1. 普通 Python HTTP 请求访问给定链接，会收到跳转至 `/login` 的响应；最终 HTTP 200 是登录页，不能当解析成功。
2. 先访问首页、保留服务器发放的匿名 Cookie、补充同站 Referer，没有解决普通客户端的访问问题。
3. `curl_cffi==0.13.0` 的 `impersonate="chrome"` 在本次环境实际对应 `chrome136`；该组合成功获取全部 5 篇笔记。
4. 每次解析使用一个全新的匿名 Session，没有读取本机浏览器 Cookie，没有配置账号或登录会话。只接受该请求流程中服务端正常发放的访客 Cookie。
5. 使用完整分享 URL，保留 `xsec_token`、`xsec_source` 等参数；请求附带 `Referer: https://www.xiaohongshu.com/` 和 `Accept-Language: zh-CN,zh;q=0.9,en;q=0.8`，保持 TLS 证书验证开启。
6. 媒体探测使用页面提供的主媒体地址，将已验证 CDN 主机的协议从 HTTP 提升为 HTTPS，保持路径和查询串不变；匿名读取文件开头，全部返回 HTTP 206 及相符的媒体类型/文件标识。

| 笔记 | 类型 | 已取得内容 |
| --- | --- | --- |
| 希望马来西亚可以尽快逃离烟霾 | video | MP4：720×1280，16.567 秒，4,495,295 字节；封面 1 张 |
| 大马国庆5天4晚旅行攻略 | image | 正文图片 10 张 |
| 离岸信托个税谁来管？外籍个人分红还免不免？ | video | MP4：1280×720，979.410 秒，168,970,581 字节；封面 1 张 |
| 招商银行万事达境外支付失败 | image | 正文图片 4 张 |
| 肥肥猫～ | video | MP4：720×1280，7.175 秒，2,711,080 字节；封面 1 张 |

验证范围是 5 篇笔记和 20 个媒体地址（14 张正文图片、3 张封面、3 个视频）。本次未完整下载、解码播放或确认水印；本地结果也不代替 VPS 出口和调用方网络的验证。分辨率、时长来自页面流元数据。

## 2. 第一版功能

- 一次接收一个完整 URL；支持 `/discovery/item/{id}`、`/explore/{id}`，以及经逐跳检查的 `xhslink.com` 短链和手机复制的 `xhslink.cn/o/<token>`。后者已用授权样本验证一次跳转到标准详情页。
- 图文返回全部正文图片，保持原顺序；Live Photo 在对应图片的 `live_video` 中返回一个选中的动态 MP4。
- 视频返回一个选中的 MP4 和独立封面。
- 返回结构化 JSON 错误，区分本站密钥问题、输入错误、上游登录限制、超时和解析结构变化。
- 提供 `refresh` 跳过本服务缓存；提供 `/healthz` 本机进程健康检查。

第一版的范围不包含分享文案提取、批量解析、作者主页采集、评论采集、直播、转码、下载代理、永久文件存储或无水印处理。未知混合媒体返回 `UNSUPPORTED_CONTENT`；声明为 Live Photo 但没有合法 MP4 时返回 `MEDIA_NOT_FOUND`，不静态降级为成功。

## 3. 技术选择

| 层 | 选择 | 原因及边界 |
| --- | --- | --- |
| 运行环境 | Python 3.12，Debian slim 镜像 | Linux 容器交付；实施时核对目标架构与依赖 wheel |
| API | FastAPI + Pydantic + Uvicorn | 参数校验、结构化响应、OpenAPI；单 worker |
| 上游 HTTP | `curl_cffi==0.13.0`，`impersonate="chrome136"` | 固定已验证组合，避免 `latest` 或隐式浏览器映射变化 |
| 缓存 | 进程内有界 TTL/LRU | 小流量无需独立缓存服务；重启清空可接受 |
| 并发 | asyncio + 有界准入 + 相同请求合并 | 避免每个请求启动浏览器或无限等待 |
| 部署 | Docker Compose 单服务 + 现有 HTTPS 入口 | 服务端只解析页面并返回 JSON |
| 测试 | pytest；API 层测试客户端；离线页面夹具 | 验证业务语义、失败分类及输入边界 |

运行依赖已精确锁定在 `requirements.lock`，开发验证依赖锁定在 `requirements-dev.lock`。不要在部署时无约束升级依赖。curl_cffi 的已验证版本与请求配置是回归基线。

初始资源预算可按 1 vCPU、1 GB 内存评估，应用容器内存上限暂设 512 MB；这些是待验收的估算。服务不加载完整浏览器、不转码、不保存大视频，资源主要花在页面请求和解析上。

## 4. 请求链路

```text
调用方
  → HTTPS 入口
  → API Key / 请求体校验 / 限流
  → 成功缓存 / 同请求合并 / 有界准入
  → 匿名获取笔记页面
  → 提取结构化笔记数据
  → 规范化图片、图片关联的 Live Photo MP4、主视频和封面
  → 成功缓存
  → JSON 响应

调用方取得媒体 URL 后，直接访问小红书 CDN。
```

### 4.1 输入规范化

- Body 只接受 `url` 和可选的 `refresh`；未知字段返回输入错误，避免传入 Cookie 等未支持参数。
- 请求体上限 8 KiB，URL 上限 4096 字符。一次只接受一个 URL。
- 精确允许 `www.xiaohongshu.com`、`xiaohongshu.com`、`xhslink.com`、`xhslink.cn`；其中 `.cn` 入口只允许单段 URL-safe token 的 `/o/<token>`。不使用后缀匹配，`.cn` 的子域、相似域名及其他路径均拒绝；新增主机或路径须有真实样本和测试依据。
- 使用 URL 解析器检查协议、主机、用户信息段和端口；拒绝嵌入用户名密码、IP 字面量、异常端口、非 HTTP(S) 和内网目标。
- 每次重定向重新校验，最多 3 次；不得验证首个 URL 后无条件跟随到任意主机。DNS 结果须为公网地址，实际连接绑定已检查的解析结果，覆盖 IPv4/IPv6。
- 分享查询参数原样保留用于请求，不随意去掉 token 或改变编码。缓存身份使用保留访问参数的规范化 URL 摘要；不把秘密参数写入日志。
- 完整长链接可从路径识别笔记 ID；短链先取得允许范围内的最终详情地址，再确定 ID。授权手机样本的脱敏链路为 `xhslink.cn/o/<redacted>` → `www.xiaohongshu.com/discovery/item/<redacted>`，共一次跳转；最终分享查询值原样保留但不记录。

### 4.2 获取页面

采用 `curl_cffi.AsyncSession` 的匿名请求，不执行页面脚本。每次上游解析使用独立临时 Cookie 会话；支持异步取消与连接关闭。

相较已经成功的探测脚本，生产版需要增加逐跳检查、响应体上限和整体超时。抓取解压后的 HTML 达到 2 MiB 时主动中止，而不是读完后才判断。

先识别最终地址和响应内容：`/login`、验证码、平台限流、明确不存在、正常笔记页。不能把 HTTP 200、存在 `__INITIAL_STATE__` 或页面含任意图片等同于成功。

### 4.3 解析结构化数据

本次成功样本的核心路径为：

```text
window.__INITIAL_STATE__
  .note.noteDetailMap[当前笔记ID].note
```

- 用有界扫描抽取指定赋值中的数据，正确处理字符串、转义、对象和数组边界。
- 使用 JSON 数据解析器；若遇到非标准的 `undefined`，只允许在字符串之外识别值 token 并转换为 null。
- 禁止执行网页里的 `eval`、`exec`、JavaScript 或函数调用。
- 必须选择与请求 ID 一致的笔记，不以映射中的第一条或最后一条代替。
- 移动页面的其他结构可预留解析适配器，但未有夹具和验证前不能声称支持；未知结构报 `PARSE_FAILED`。

### 4.4 媒体规范化

**图片：** 从 `imageList` 按列表顺序读取。优先 `urlDefault`，其次 `infoList` 中的 `WB_DFT`，必要时才使用 `urlPre`。只在同一条目的候选地址中去重，不跨图片位置去重，不改变原顺序。返回的图片可能是 WebP；不把扩展名强改 JPG，不删路径变体参数来声称获得原图。

图片宽高使用 `source_width`、`source_height`，表示页面元数据。页面可能记录原始尺寸，而实际 CDN 地址返回缩放版本；未读取并解码图片前，不宣称为下载文件的实际尺寸。

**Live Photo：** `livePhoto=true` 或图片条目中存在非空动态 `stream` 时，该图片仍保留在原位置，并增加一个 `live_video`。动态候选与普通视频复用相同的合法主机、MP4 证据、主/备用地址和 H.264/分辨率/码率排序规则。空 `stream` 不会把普通图片误判为 Live Photo。动态宽高、时长和大小只读取选中动态候选自身的字段，不能复制静态图元数据；上游未提供时返回 null。声明为 Live Photo 却没有受支持 MP4 时整篇失败，避免调用方误以为拿到了完整内容。

**视频：** 从 `video.media.stream` 收集有合法 URL 的 MP4 候选。优先 H.264，同编码中按分辨率、再按码率降序选择；未知值排在已知值之后。只输出一个选中的 MP4，避免多清晰度被误解为多个不同视频。每个候选优先使用可证明为 MP4 的合法主地址；主地址缺失、不合法或不能证明为 MP4 时，才按顺序考虑合法备用地址。只有封面、没有支持的主视频时必须失败。

视频尺寸、时长、大小均来自选中流的元数据；毫秒时长转为秒，不把原视频的尺寸填入已转码流。编码、清晰度或大小不确定时返回 null。

**封面：** 视频的 `imageList` 作为封面来源，单独放到 `cover`，正文 `images=[]`。图文 `cover=null`，调用方可使用第一张正文图。

**协议和主机：** 返回通过格式及 CDN 主机校验的地址。当前精确允许已实测的 `sns-webpic-qc.xhscdn.com`、`sns-video-v6.xhscdn.com`、`sns-video-v28.xhscdn.com`、`sns-bak-v11.xhscdn.com` 和 `sns-bak-v10.xhscdn.com`；其他子域不会仅因后缀相同而自动信任。新增 CDN 主机/协议行为应先取得样本并加入回归。保留全部签名参数，不拼造未出现的资源路径。

## 5. JSON 契约与直链语义

接口为 `POST /api/v1/xiaohongshu/parse`。生产环境调用头必须包含本站 `X-API-Key`；这只是你部署的接口访问密钥，不是小红书账号登录。

请求：

```json
{
  "url": "https://www.xiaohongshu.com/discovery/item/6ad1f8610000000018018eef?xsec_token=YOUR_SHARE_TOKEN&xsec_source=pc_share",
  "refresh": false
}
```

完整字段定义以 [OpenAPI 契约](openapi.json) 为准。

- 成功信封：`success=true`、`data` 为笔记结果、`error=null`、`meta` 为请求和缓存信息。
- 失败信封：`success=false`、`data=null`、`error={code,message,retryable}`、`meta` 包含 request_id。
- `type=image`：`images` 至少 1 项，普通图片省略 `live_video`，Live Photo 图片包含一个 `live_video` MP4；`videos=[]`，`cover=null`。
- `type=video`：`images=[]`，`videos` 恰好 1 项，`cover` 可以为 null。
- `url_expires_at` 未知时为 null；不得猜测固定 24 小时等期限。
- `meta.cache.expires_at` 仅为本服务缓存淘汰时间，不保证媒体在这段时间内有效。
- 正常解析响应中的 `verification` 固定 `not_checked`，表示该次调用只解析页面，没有下载校验媒体。历史样本的文件头检查不改变后续响应状态。
- `refresh=true` 跳过本服务缓存、重新获取页面，仍受密钥、限流和并发限制；它不延长平台签名 URL 的寿命。

**媒体直链是小红书提供的临时地址，不是本服务托管的永久下载地址。** 调用方拿到后应尽快使用；失效后重新解析。VPS 能访问不代表不同网络的调用方一定能访问，必须单独验收。当前媒体检查附带同站 Referer，该头是否对所有网络必须、地址是否有 IP 相关限制，均没有普遍结论。

## 6. 小流量运行参数

| 参数 | 初始值 | 含义 |
| --- | --- | --- |
| Worker | 1 | 保证内存缓存、限流及合并状态一致 |
| 上游解析并发 | 2 | 完整解析任务的并发数，不只是连接池数 |
| 等待容量 | 4 | 超出容量返回 503 BUSY，不无限排队 |
| 排队时间 | 2 秒 | 超时返回 BUSY |
| 总请求时限 | 20 秒 | 从准入开始，覆盖排队、跳转、重试和解析 |
| 连接时限 | 5 秒 | 仍受整体剩余时间约束 |
| 成功缓存 TTL | 120 秒 | 保守初值，非 CDN 有效期 |
| 缓存容量 | 256 条 | 有界 LRU/TTL，失败不缓存 |
| 接口限流 | 每 API Key 每 60 秒最多 20 次 | 命中缓存与 refresh 也计数；超额返回 429 |
| 临时故障重试 | 最多 1 次 | 仅连接故障或部分临时上游错误，受总时限约束 |
| HTML 上限 | 2 MiB | 解压后字节数 |
| 重定向上限 | 3 次 | 每一跳独立检查 |

登录页、验证码、明确不可见、解析结构变化不自动重试。相同缓存键的进行中请求可以合并一次上游工作，但等待者同样计入有界准入；取消一个等待者不能破坏其他等待者。过期条目和限流记录应主动清理。

升级多进程或多副本前，应重新设计缓存、限流和并发状态共享，不能直接把 worker 数从 1 调大。

## 7. 错误与可观测性

| HTTP | 业务码 | 含义 |
| --- | --- | --- |
| 400 | INVALID_REQUEST / INVALID_URL | JSON 或链接不合法 |
| 401 | UNAUTHORIZED | 本站 API Key 缺失或错误 |
| 404 | NOTE_NOT_FOUND / ROUTE_NOT_FOUND | 明确笔记不存在 / 本站路由不存在 |
| 405 | METHOD_NOT_ALLOWED | 请求方法不支持 |
| 413 | INPUT_TOO_LARGE | 请求体超过上限 |
| 422 | UNSUPPORTED_CONTENT | 直播或当前无法完整处理的未知混合媒体 |
| 429 | RATE_LIMITED | 本站调用限流 |
| 500 | INTERNAL_ERROR | 未预期内部错误 |
| 502 | UPSTREAM_BAD_RESPONSE / PARSE_FAILED / MEDIA_NOT_FOUND | 上游异常、结构变化或应有媒体缺失 |
| 503 | BUSY / UPSTREAM_LOGIN_REQUIRED / UPSTREAM_ACCESS_RESTRICTED / UPSTREAM_RATE_LIMITED | 本站繁忙或平台访问限制 |
| 504 | UPSTREAM_TIMEOUT | 整体上游解析超时 |

`NOTE_NOT_FOUND` 必须有明确上游依据；没有笔记数据不能直接当作删除。平台要求登录不返回本站 401，避免调用方误以为 API Key 错误。

所有应用层响应，包括框架默认 404/405/校验异常，统一为 JSON 信封；自有反向代理的 413/502/503/504 同样处理。网络断连、TLS 握手失败或第三方网关替换响应不在此保证内。

记录 request_id、笔记 ID、耗时、缓存命中、结果码、并发和队列状态。日志不记录 API Key、Cookie、完整分享查询串、签名媒体地址或页面全文。`/healthz` 只检查进程，不每隔几十秒访问小红书。

## 8. 当前验证状态与外部验收

Python 3.12 的 88 项离线测试覆盖 URL/DNS 策略、精确 `.cn` 手机短链路径及相似域拒绝、逐跳安全跳转、初始状态读取、普通图片、多个 Live Photo 和普通视频规范化、统一 API 信封、鉴权、缓存、请求合并、限流、队列、取消、日志脱敏、运行时 OpenAPI 及示例契约。2026-10-18 的授权 Live Photo 样本返回 18 张有序图片、2 个嵌套动态 MP4、空顶层 `videos`；静态图和动态 MP4 各有一个代表性地址完成 1024 字节有界文件头检查，均返回 206，未执行完整下载或播放，输入 token 与媒体 URL 未持久化。同日授权手机短链样本确认一次手动跳转到标准详情页；重建后的本地 API 将其解析为 7 张有序图片、每张都带嵌套 Live Photo MP4、空顶层 `videos`，探测只记录主机、脱敏路径、查询键名及媒体计数。变更后重新执行 Compose 配置校验、镜像构建、容器启动与 `/healthz`；目标 VPS 原生架构与出口、HTTPS、调用方完整媒体下载和回滚演练仍保持未验证。

1. 5 个已知样本取得正确类型和数量，视频封面不计入正文图片。
2. 页面解析与接口测试使用脱敏夹具，不把每次测试都变成真实平台请求。
3. 登录页、无效链接、超时、结构变化都有正确 JSON 和 HTTP 状态。
4. 超并发、缓存容量、超时、取消和刷新行为符合有界设计。
5. Linux 容器内验证已锁定请求配置；VPS 解析成功后，再从实际调用方网络读取返回媒体。
6. 图片检查代表性文件的实际格式；视频用部分内容检查可达性，完整下载/播放验证单独记录，不能混淆。

## 9. 依据

- 本地实测：[匿名验证记录](evidence/anonymous-probe-2026-10-17.json)。
- Live Photo 实测：[脱敏探测记录](evidence/live-photo-probe-2026-10-18.json)。
- 手机短链实测：[脱敏跳转记录](evidence/mobile-short-link-probe-2026-10-18.json)。
- [curl_cffi v0.13.0 浏览器配置源码](https://github.com/lexiforest/curl_cffi/blob/v0.13.0/curl_cffi/requests/impersonate.py)：固定 `chrome136` 基线。
- [yt-dlp 小红书解析源码](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/extractor/xiaohongshu.py)：页面结构及媒体字段的参考；本项目仍以真实样本和自身测试为准。
- [FastAPI 官方容器部署说明](https://fastapi.tiangolo.com/deployment/docker/)：从官方 Python 镜像构建服务。
- [Docker Compose 官方文档](https://docs.docker.com/compose/)：单机容器配置与生命周期管理。
