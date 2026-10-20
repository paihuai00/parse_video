# Research: 抖音公开作品的上游解析选项

- Query: 分析公开分享页视频、图文解析的数据候选、匿名限制，以及签名/Cookie/浏览器是否应进入首版。
- Scope: mixed（本仓库契约 + 官方开放平台文档 + 第三方解析器自身源码）；仅研究，不实现。
- Date: 2026-10-19（Asia/Shanghai）
- Evidence boundary: 本研究没有请求用户提供的四个短链；样本结果由主会话记录。第三方源码只能证明该项目如何尝试解析，不能证明抖音当前、所有地区或部署环境均返回这些字段。
- Integration update: 主会话反馈用户已选择统一入口并保留旧接口；已在 `docs/douyin/` 编写规划。主会话请求短链时遇到本地 DNS 解析失败，未取得页面；这是环境验证阻塞，不是内容不存在、上游挑战或解析不可行的证据。

## Findings

### 结论与推荐

优先验证“受控展开短链 → 移动分享页 → 有界提取 JSON → 按请求作品 ID 匹配 → 媒体归一化”路径。视频和普通图文均有第三方实现证据，但尚不足以保证四条用户样本成功。网页详情接口、签名和浏览器保留为后续独立决策，不应因为开源项目存在这些组件就纳入首版。缺少数据应有明确失败结果，不拼接猜测可播放的 URL 或宣称“原画无水印”。

### 本地文件与可复用模式

| 文件 | 内容与证据 |
| --- | --- |
| `.trellis/spec/backend/service-contract.md` | 单作品解析、匿名会话、逐跳 DNS/IP/host 校验、总 deadline、成功缓存、媒体不代理与错误分层的现行契约。 |
| `.trellis/spec/backend/error-handling.md` | 区分登录、挑战、限流、明确不存在、解析失败与媒体缺失；不泄露上游 HTML/Cookie。 |
| `app/models.py:19` | `InternalVideo`、`InternalImage`、`InternalNote` 可以承载平台适配器归一化结果。 |
| `app/models.py:60` | 请求是单个 `HttpUrl` 与 `refresh`；原始分享文案不是当前已支持输入。 |
| `app/models.py:104`、`app/models.py:113` | 公共 `note_id` 限制为 24 位十六进制；抖音十进制作品 ID 不能直接复用这个校验。需主设计明确兼容扩展或平台模型。 |
| `app/parser/state_reader.py:23` | 已有字符串/转义感知的括号匹配，且限制长度、深度；其 marker 当前是小红书专用。可复用算法原则，不能直接把抖音 HTML 传给现有入口。 |
| `app/parser/media.py:11`、`app/parser/media.py:42` | 精确 CDN host 校验当前只含小红书；新增平台需独立、经样本验证的 host 集合。 |

相关 specs：上述 backend 两文件及 `backend/index.md`。研究读取了 `.trellis/workflow.md`；未读取角色隔离的 implement/check manifests。

### 第一方事实：开放平台并不是任意分享链接解析 API

抖音官方“查询特定视频的视频数据”接口要求权限、用户授权及 access-token，`item_ids` 仅能查询 token 对应用户上传的视频，内容以统计与作品信息为主。由此推断：该接口不能直接替代本任务“用户粘贴任意公开视频/图文短链”的匿名解析需求。这不等于证明不存在任何其他官方能力。

来源（访问日期均为 2026-10-19）：[抖音开放平台 video/data](https://open.douyin.com/platform/resource/docs/openapi/video-management/douyin/search-video/video-data)。

### 第三方源码事实：内嵌状态候选

1. `jackwoo725-ux/douyin-downloader` 的 `backend/douyin.py:180` 提取 `_ROUTER_DATA`，支持对象或再次 JSON 编码的字符串；`:327` 尝试 `www.iesdouyin.com/share/video/{id}/`、`share/slides`、`share/note`。这是可测试候选，不代表每个路径被抖音官方支持。
2. `jiuhunwl/short_videos` 的 `api/douyin/DouyinParser.php:398` 支持两种候选：`window._ROUTER_DATA` 内 `loaderData` 中动态 key 下的 `videoInfoRes.item_list`；以及 URI 解码后的 `RENDER_DATA` 内 `app.videoDetail`。该项目自身主入口访问带 Cookie 的页面，不能据此宣称匿名成功。
3. 这些源码都有“取第一个作品”或广泛递归搜索的行为。本仓库应该改为明确候选容器 + 请求 ID 精确匹配 + 有界遍历；推荐流/其他作品不能误命中。不能执行上游脚本，也不能用 `eval`。

来源：[Python 分享页实现](https://github.com/jackwoo725-ux/douyin-downloader/blob/main/backend/douyin.py)、[PHP 多状态实现](https://github.com/jiuhunwl/short_videos/blob/main/api/douyin/DouyinParser.php)。二者均为第三方实现，不是官方稳定契约。

### 媒体映射候选及本项目决策

| 上游候选 | 现有结果映射 | 必须验证的细节 |
| --- | --- | --- |
| `aweme_id` | `note_id`（或主设计确定的通用字段） | 保持字符串，避免 JS 数字精度损失；与目标 ID 相符。 |
| `desc` | `title` | 允许空值；抖音文案可能没有单独标题。不要从分享文案臆造上游标题。 |
| `images[]` 的 `url_list[]`；另一路可能为 `urlList[]` | 有序 `images[]`，`videos=[]` | 遍历全部图片；URL 列表通常是同张图片的候选地址，不是多张图片。不能遇到坏图就静默返回不完整成功。 |
| `video.play_addr.url_list`、`play_addr_h264`、`bit_rate[].play_addr` | 一个经过选择的 MP4 候选 | 不能因 URL 看起来像视频就把格式标为 MP4；候选容器、编码、清晰度都需要证据。 |
| `video.cover`、`origin_cover` | 可空独立 `cover` | 图片正文与封面分离；不要把动态封面误当视频作品。 |
| `video.duration` | `duration_seconds` | yt-dlp 的 app schema 按毫秒除以 1000；需按明确 schema 转换，不能靠“大于 1000 就认为毫秒”。 |
| `music` 或图文伴随的 `video` 占位字段 | 普通图文仍为图片结果 | 音乐、封面、占位不自动构成顶层混合媒体；不能仅用是否存在 `video` 判断类型。 |
| `images[i].video` 等动态图片候选 | 若未来支持，嵌套 `images[i].live_video` | 本任务首先明确普通图文范围；已识别动态内容不能悄悄扔掉动作部分并声称完整成功。 |

字段来源：上述 Python 实现 `:276` 与 PHP 实现 `:439`；视频变体和时长另见 [yt-dlp tiktok.py](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/extractor/tiktok.py)（本次原始源码行 `450–488`、`557–559`）。本表右列是本研究针对现有契约的设计建议，不是上游承诺。

第三方实现存在 `playwm` 替换、使用 URI 拼接播放端点、改 CDN host 的做法；本项目没有证据证明这些改写能保持 URL 签名、媒体格式、访问权限和质量，因此不建议照搬。`url_expires_at=null`、`verification=not_checked` 保持原契约；缓存 TTL 不等于上游链接寿命。

### 匿名访问、签名、Cookie 与浏览器

| 路径 | 实现证据 | 首版建议 |
| --- | --- | --- |
| 移动分享 HTML | Python 源码尝试直接 HTTP 请求并解析状态 | 最小验证路径。先确认四样本与部署出口能拿到完整数据；匿名会话收到的临时 Cookie 不等于导入用户登录 Cookie。 |
| 网页详情 JSON | yt-dlp `DouyinIE._real_extract` 请求 `/aweme/v1/web/aweme/detail/`，缺少详情时提示新 Cookie，且注明不一定需要登录 | 保留为候选。该错误是解析器判断，不是抖音官方诊断；空响应本身不能断言必须登录。 |
| 带签名网页请求 | Evil0ctal 的 v4 `get_douyin_headers` 从配置读取 Cookie，`fetch_one_video` 添加 `a_bogus` | 说明有维护签名与会话的路径，但 v4 是历史分支，本次未验证可用性。不能将其作为当前保证或无条件 fallback。 |
| 浏览器渲染 | 可用于人工/诊断确认客户端是否能加载内容；本研究未执行浏览器会话 | 没有证据证明必须加入生产浏览器。新增浏览器会改变部署、会话与并发模型，应先用实际失败证据决定。 |

来源：[yt-dlp Douyin 实现](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/extractor/tiktok.py)（原始源码 `1495–1508`）；[Evil0ctal v4 web_crawler.py](https://github.com/Evil0ctal/Douyin_TikTok_Download_API/blob/v4/crawlers/douyin/web/web_crawler.py)（`73–109`）。后者在 main 的旧路径已返回 404，说明不能继续引用旧博客路径当当前实现。

可预期但待样本验证的失败：短链失效、区域/出口差异、登录或挑战 HTML 仍返回 200、空壳 HTML、字段漂移、限流、CDN 过期或另需请求上下文。建议复用现有错误分类：仅有明确不存在证据才返回 `NOTE_NOT_FOUND`；空 HTML/缺少状态优先归类解析或上游响应失败，明确挑战才返回 `UPSTREAM_ACCESS_RESTRICTED`。

### 验证与实施前门槛

1. 主会话对四样本分别记录重定向 host/path、作品 ID、HTTP 状态、状态容器、类型、图片数量/视频候选字段；不记录敏感 query、Cookie、完整媒体签名。
2. 取得可脱敏的真实响应结构后建立离线 fixture，再确定状态读取路径、类型 discriminator、CDN host 和 MP4 选择规则。
3. 重定向和 URI 播放端点若有必要，全部纳入原有逐跳安全校验与总 deadline，不能让底层 HTTP 客户端自动跟随绕过校验。
4. 至少验收普通视频、全部有序图文、错误作品 ID、推荐作品干扰、缺失媒体、挑战页、空壳页及未知字段形态；保留小红书回归。
5. 如果分享页在目标部署环境持续不足，先形成“会话/签名/浏览器补充方案”的独立设计，再判断是否扩大范围；不把本次任务默认升级为签名逆向、登录凭证管理或浏览器服务。

### 来源版本记录

网页访问时间：2026-10-19。GitHub API 查询 branch commit SHA 返回 403 rate limit，因此未能固定提交；为减少漂移歧义，记录直接下载源码内容的 SHA-256（未落盘源码）：

| 来源 | 分支 | SHA-256 |
| --- | --- | --- |
| yt-dlp `yt_dlp/extractor/tiktok.py` | master | `3257fdea744811ea2e1bfee665a97d6ab85517339ee672f2e43e238e6b997c9e` |
| jackwoo725-ux `backend/douyin.py` | main | `e6280f3bd6c3844884da0614277f980a79cddadabef9ad9a50fdb13fdaa43413` |
| Evil0ctal `crawlers/douyin/web/web_crawler.py` | v4 | `2eff0352ef3eccd1d49ac8fb4c211678e1db73f04187a0d3048c4c452d8000a7` |

Web 索引的 yt-dlp 行号与直接原始文件读取有差异，文中精确行号优先使用本次原始文件读取；链接分支以后可能变化。第三方项目代码的许可证未在本研究审查，当前仅用于理解候选结构，不建议直接复制实现。

## Caveats / Not Found

- 未证明四个短链可匿名解析，未验证任何 CDN 资源可下载，未做水印、最高画质或有效期保证。
- 未发现可作为任意公开分享页稳定契约的官方 schema；开放平台授权 API 与此需求存在范围差异。
- 未证明 `RENDER_DATA` 仍普遍包含媒体数据；只能列为具有源码依据的备选，不自动堆叠无限 fallback。
- 抖音图文可能带音乐或动态图片；需要主设计明确普通图文、动态图片和直播的范围与失败策略。
- 文中的精确 host 候选和字段形态必须由用户样本/受控补充样本收敛，不能把第三方宽泛 host/递归/自动重定向做法迁入本项目。
