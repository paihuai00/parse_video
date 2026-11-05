# 其他解析路线与移动端实测突破

日期：2026-11-04。用户要求继续调查其他解析方案。此轮只研究和更新方案，未修改产品代码、未部署、未读取用户浏览器 Cookie 或启动已登录浏览器。

## 首选结论：当前样本存在无需登录的移动端 HTTP 路线

在独立临时诊断环境中，复用项目 XiaohongshuClient、固定 curl_cffi 0.13.0，替换匿名请求 impersonate 为 safari184_ios。保持原始完整分享 URL、逐跳 URL/DNS 公网校验、CurlOpt.RESOLVE 地址绑定、TLS、关闭代理、每次 20 秒总期限、2 MiB 页面上限、独立匿名 Cookie 会话。

| 请求特征 | PC 完整长链 | 手机短链 |
| --- | --- | --- |
| 既有 chrome136（前轮） | /404 后 INVALID_URL | /404 后 INVALID_URL |
| chrome131_android | 跳转不受支持路径后 INVALID_URL | 跳转不受支持路径后 INVALID_URL |
| safari184_ios | 重定向到允许的详情路径后 HTTP 200；现有 select_note 报 PARSE_FAILED | HTTP 200；现有 select_note 报 PARSE_FAILED |

对 iOS 页进行额外结构检查，两个输入均确认：

- window.__INITIAL_STATE__ 可通过现有有界 JSON 解码器解码。
- noteData.hasError 为 false。
- 笔记对象位于 state.noteData.data.noteData；该对象 noteId 与请求目标匹配。
- type=normal，imageList 恰为 1 张；livePhoto=false，stream 为空；图片尺寸 1427 × 1427。
- 图片候选使用 imageList[i].url 及 infoList 下 H5_DTL/H5_PRV，而非现有 WB_DFT/urlDefault/urlPre。
- 对一个代表性图片执行 HTTPS、公网 DNS 与地址绑定、TLS、禁用代理/自动跳转、Range bytes=0-1023 的有界检查：精确主机 sns-webpic-qc.xhscdn.com（已在产品白名单），HTTP 206，Content-Type image/jpeg，检查 1024 字节，JPEG 文件头匹配。

完整链接、token、目标 ID、页面、媒体 URL、Cookie 值均未保存。本机 Python 3.15.2 与支持的 3.12 不同，且不是服务器出口；这是本样本可匿名获得匹配图片数据的实测证据，不是已上线成功或所有内容类型的保证。

移动端返回标记为普通静态图文。本次没有普通视频或 Live Photo 的移动端成功样本；不据此承诺相关媒体完整性，也不能把移动端可能减少的字段当成完整动态内容。

## 已确认的适配缺口

1. app/parser/state_reader.py:153 的 select_note 只读取 note.noteDetailMap[id].note；移动端数据即使已获取，也会报 note state is missing。
2. app/parser/media.py:72 的 _image_url 只读取 urlDefault、WB_DFT、urlPre，忽略当前真实移动端 H5_DTL/H5_PRV 及直接 url。即使改笔记选择器，也还需要明确的移动端图片归一化。
3. 原有 /404 状态跳转分类缺陷依旧存在。只替换 XHS_IMPERSONATE 环境变量会从 INVALID_URL 变成 PARSE_FAILED，不能构成完整修复。

## 路线比较

### A. 自有匿名移动分享页适配（推荐）

证据：上述样本的真实成功数据与图片头检查。保留桌面现有能力，增加有界 iOS 获取与移动 schema 适配。最小交付先覆盖已证实的普通静态图文；视频、Live Photo 需要独立样本，不能丢失动态部分后伪成功。

成本主要是新增获取策略、精确 schema 分支和回归验证；无账号会话运维或第三方 API 费用。服务器环境的匿名可用性仍待实测。

### B. 开源解析器参考

作者仓库：https://github.com/JoeanAmier/XHS-Downloader

作者 README 明确写 Cookie 非强制，未配置时视频画质有限；提供 /xhs/detail API 及 download=false，并包含浏览器用户脚本。这说明“所有解析都必须登录”不是可靠结论。但未安装运行该完整项目、未对本样本调用其 API，不能把 README 作为样本成功证据。可参考字段适配和测试思路；直接复用代码前需要审查 GPL-3.0 许可及依赖边界。

### C. 真实浏览器获取（当前降为后备研究）

匿名浏览器可能初始化页面会话与 JS；若确实只有登录后可得，可在用户授权范围设计独立账号会话，但这是现有匿名契约以外的范围。本轮已有更轻的匿名 HTTP 成功路线，无需优先建设浏览器运行时。

MediaCrawler 源码参考：https://github.com/NanmiCoder/MediaCrawler/blob/main/media_platform/xhs/core.py 及 client.py。它使用浏览器上下文/Cookie；会话检查失败会进入登录流程，不能当成必然免登录的替换件。未运行该项目。

### D. 第三方笔记 API（文档候选，未调用收费接口）

TikHub 服务商原始文档：

- https://docs.tikhub.io/420136391e0 图文详情：GET /api/v1/xiaohongshu/app_v2/get_image_note_detail。
- https://docs.tikhub.io/420136392e0 视频详情：GET /api/v1/xiaohongshu/app_v2/get_video_note_detail。

文档支持 note_id 或 share_text，后者包括 .cn 短链；需要服务商 Bearer token。图文接口遇视频只给封面等基础信息，需要另调视频接口。文档说明上游业务失败可能仍计费；没有服务商凭据，未发送用户样本到该服务，不能承诺可解析本样本或 Live Photo 完整。

Postman 公共 API 发现（Orbit）也找到 AnyAPI RedNote Note；其 integrate brief 明确为部分匹配，schema 没展示媒体直链且 output.data 样例为空，不足以满足当前直链需求。未调用收费 provider。Postman CLI 未登录，未执行账号内搜索、Context Graph 或依赖下载。

## 推荐决策

优先在自有服务内实施“桌面保留 + 有界 iOS 移动页获取 + 移动状态和图片 schema 适配”，并修正状态跳转误分类。没有证据需要先引入登录账号、全浏览器或付费平台。上线验收在服务器出口复测两个授权输入；成功标准是匹配目标笔记并返回完整已支持媒体，不能只以 HTTP 200 或错误码改变为完成。
