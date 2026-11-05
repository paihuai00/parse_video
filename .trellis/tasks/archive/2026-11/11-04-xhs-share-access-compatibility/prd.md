# 小红书匿名移动页兼容修复规划

## Goal

让已授权的小红书分享链接在现有 Linux VPS 服务中，通过有证据支持的匿名移动页路线返回完整静态图文，同时修复上游状态跳转被误报为用户链接无效的问题。

## Background and Evidence

| 来源 | 已确认结果 | 尚未覆盖 |
| --- | --- | --- |
| 当前公网旧接口 | 两个原始输入均返回 HTTP 400 INVALID_URL | 修改后的完整 API 行为 |
| 本机会话 | 桌面策略跳转 /404；匿名 safari184_ios 对短链和 PC 长链均取得 ID 匹配、hasError=false 的移动状态；普通图文1张，livePhoto=false、stream空；代表图片206/image/jpeg且文件头匹配 | 本机为Python3.15，不能替代支持运行时验收 |
| 用户桌面浏览器 | 登录时完整内容可见；退出后截图有登录弹窗及背景笔记内容 | 不能凭截图判断完整媒体、缓存或登录必要性 |
| 用户转述的VPS Codex | 实际x86_64/Python3.12.8/curl_cffi0.13.0容器内，手机短链iOS匿名获取成立且ID匹配，现有select_note仍PARSE_FAILED | PC长链未填入；媒体Range未做；stream内容未检查；完整API和调用方CDN读取未做 |
| 本地Git核对 | VPS提供的be32fc7是当前75b3b62的祖先；app/tests/scripts/依赖锁/pyproject/Dockerfile/compose/deploy均无差异，后续提交仅Trellis记录 | 镜像完整提交来源及发布候选仍在发布验收中确认 |

研究证据保存在 research/share-link-comparison.md、alternative-acquisition.md、vps-deployment-impact.md、vps-verification-report.md。输入携带不同分享token和app_share/pc_share来源；交换详情路径未恢复桌面访问，未经证据不改写分享参数或解释-510001的语义。

## Requirements

- R1：保持原有单链接请求、两条API路由及响应字段。保留完整分享查询值和桌面已支持能力。
- R2：将已验证详情页产生的精确上游状态跳转与用户无效输入区分。现有失败锚点为 app/parser/client.py:105、app/parser/client.py:157 和 app/parser/url_rules.py:79；登录/错误分类执行点在 app/parser/client.py:180。未知/404与-510001不能推断删除。
- R3：首版只针对安全、已验证详情页跳向同站点/404的已知失败类别，增加一次匿名safari184_ios兜底。非法输入、危险目标、DNS安全拒绝、超时、限流和未知解析错误不因兜底被重复执行。沿用原始20秒期限、并发准入、重定向及重试上限，不能为第二策略重新计时。
- R4：支持精确移动状态noteData.data.noteData，要求容器类型、hasError和noteId有效且目标匹配；保留桌面note.noteDetailMap选择器，见 app/parser/state_reader.py:146。不得用任意递归搜索、推荐内容或HTTP200作为成功依据。
- R5：支持移动H5_DTL及有明确语义的详情图片字段，复用精确CDN校验；现有候选缺口位于 app/parser/media.py:72。图片顺序、数量和来源尺寸完整保留；H5_PRV预览不能单独证明完整图片可用。
- R6：新增移动路径首版只承诺已验证的普通静态图文；检查每张图片的动态标记和stream，不得把动图、视频、缺图或未知结构静默降成部分静态成功。已有桌面视频/Live Photo和抖音行为不退化。
- R7：保持匿名会话、TLS、公网DNS逐跳验证及地址绑定、精确主机/路径/端口、页面/状态大小和取消清理边界。不新增媒体下载代理或保存媒体。
- R8：交付VPS可运行的脱敏验收命令及可追溯候选版本，分开验证容器出站、API入站和真实调用方CDN读取。不持久化完整分享URL、真实笔记ID、token、Cookie、HTML或签名媒体URL。

## Acceptance Criteria

- [x] AC1（R2/R3/R7）：安全详情页/404跳转可进入一次移动兜底；移动也失败时返回准确或保守上游错误。非法输入、相似域、外站、凭证、端口和私网/混合DNS等在连接前拒绝，且不触发兜底。
- [ ] AC2（R4/R5/R6）：两个授权原始输入在VPS真实API返回匹配目标的完整已支持静态图文。本样本预计1张图片，只有核实stream和媒体后才算完成。
- [x] AC3（R4/R5/R6）：移动状态错误/类型异常/ID错配、缺图/非法槽位、未知主机、预览唯一候选、动态标记或不支持流均不返回部分成功；正常多图保持顺序/数量。
- [x] AC4（R1/R3/R6/R7）：桌面普通图文/视频/Live Photo、抖音、两条API契约、缓存/refresh/合并/限流/准入/期限/取消与安全日志通过相关回归；依赖和请求响应schema保持兼容。
- [ ] AC5（R7/R8）：在支持的Python3.12完成规范检查，并验证VPS原生运行镜像。代表媒体有界文件头检查、真实调用方媒体读取、容器及公网API均通过；/healthz或镜像构建成功不能替代。

## Out of Scope

新增账号登录/Cookie管理、付费API或浏览器兜底、无证据的指纹/主机扩张、移动视频/Live Photo通用支持、登录弹窗分类重构、媒体代理/转码、多worker扩容及未经单独授权的生产部署。

## Completion and Handoff

2026-11-05 用户确认本地服务在其Postman中运行正常，并明确要求归档本次任务、由用户自行提交Git，再交由VPS Codex拉取/重建/部署与验收。本地实现、190项离线回归、独立复核、真实授权短/长链完整ASGI/API、代表图片及本地HTTP/Postman CLI检查均已通过。

本次按用户指示归档的是本地实现与交付任务。AC2与AC5中仍未完成的候选VPS媒体、PC长链、完整API、调用方读取和发布/回滚检查明确移交到部署阶段，保留未勾选，不宣称已在VPS生效。执行入口为docs/vps-xhs-mobile-acceptance.md。

用户自行进行代码和记录提交；AI不git add/commit/push。归档与journal使用--no-commit，生产部署由用户后续向VPS Codex授权执行。当前本地测试服务按用户需要保持运行。
