# 本地实现验证

日期：2026-11-05（Asia/Shanghai）。本轮已按用户明确授权进入实现，未连接、部署或切换 VPS。

## 实现

- 客户端对已校验笔记详情页的精确同源 /404 跳转使用内部 typed error；默认桌面策略可在剩余额度内切换一次固定 safari184_ios。
- 两策略及临时故障重试共享两次尝试、parse级重定向上限和原始 Deadline；状态页不连接，不安全/无关失败不兜底；移动重定向绑定原目标笔记身份。
- 精确移动状态选择保留布局来源；现有 select_note 作为兼容字典接口仍可用。移动归一化严格验证每个静态图片槽位和详情候选，拒绝预览唯一结果与动态/视频伪静态成功。
- 公共请求/响应 schema、默认桌面配置、依赖、Docker/Compose未改变。文档、英文规范及VPS验收命令同步更新。

## 支持运行时与离线检查

独立临时环境：/tmp/parse-video-runtime-20261104，Python3.12.16，项目锁定 requirements-dev.lock 依赖。系统Python3.15未用于质量门。临时环境未写入项目依赖。

实现代理报告及独立复核代理已执行的完整离线套件：190 passed。Ruff格式/检查、Mypy26个源文件及compileall通过。OpenAPI JSON语法、git diff --check和docker compose config --quiet通过。

本机Docker daemon未运行，因此没有候选镜像构建/启动证据；Compose静态校验不等于镜像或VPS验收。

独立trellis-check已完成全范围复核并独立运行190项测试、Ruff、Mypy26源文件、compileall、OpenAPI JSON与diff检查，全部通过，未发现产品代码缺陷。它修复了VPS内联诊断的长链身份验证，使其同时绑定原始长链ID而不只相信最终跳转ID；以离线替身实际执行短链、匹配长链和不匹配长链，错配在API/媒体检查前停止，输出保持脱敏。该诊断验证不是VPS真实网络结果。

## 原始授权样本的真实网络/API检查

使用支持的Python3.12.16，在真实create_app/ParseService/客户端/选择器/归一化/响应模型链路中，经HTTPX ASGITransport调用API。测试只对授权的小红书/CDN产生真实外部访问；未启动公网服务器，未修改生产配置。探测进程关闭日志输出，仅打印脱敏统计；未持久化真实笔记ID、输入URL、token、HTML或签名媒体URL。

| 用例 | HTTP/结果 | 媒体 | 缓存 | request ID |
| --- | --- | --- | --- | --- |
| 原始手机短链，旧小红书路由，refresh=true | 200，success=true，error=null，ID与授权长链目标匹配 | 图片1，Live Photo0，视频0 | miss | 6b9c73b4-8fc7-483e-bae8-65e60bf1f8c2 |
| 原始PC长链，统一路由，refresh=true | 200，success=true，error=null，ID匹配 | 图片1，Live Photo0，视频0 | miss | 17f6370c-7869-45b9-bfbf-1193304f719e |
| 同一手机短链，统一路由，refresh=false | 200，success=true，error=null，ID匹配 | 图片1，Live Photo0，视频0 | hit | 56232d84-b6e2-4f2a-9d75-a193ccc5660a |

三次请求ID互异，验证了跨路由共享结果缓存而不共享调用方请求元数据。

对返回的第一张代表图片，重新验证全部DNS地址为公网并以CurlOpt.RESOLVE绑定，禁用环境代理/自动重定向，启用TLS，Range bytes=0-1023。结果：精确主机sns-webpic-qc.xhscdn.com，HTTP206，Content-Type image/jpeg，检查1024字节，JPEG文件头匹配。未完整下载或解码整张图片，不将来源尺寸作为文件实际尺寸验证。

## 尚未完成

### 用户本地 Postman 测试服务

2026-11-05 按用户要求启动实际 Uvicorn HTTP 服务，Python3.12.16，监听127.0.0.1:8000、单worker、development环境、独立本地测试鉴权。进程PID12197（工具会话16387），不是Docker/VPS服务，未改变生产配置。测试密钥值不写入记录。

独立GET /healthz为200/status=ok。Postman CLI对旧小红书接口重放授权短链返回success=true、error=null、ID匹配、图片1、动态0、视频0，CLI退出0；request ID为886a06db-4ae9-4acb-90d7-f5b30f77e9b3。服务按用户要求保持运行供其本机Postman测试；代码尚未提交，VPS尚未部署。

### 外部验收

- 候选代码的VPS镜像构建/启动、PC长链/stream/媒体/完整API和公网入口验收。
- 真实调用方网络读取返回媒体、发布/回滚演练。
- 移动普通视频或Live Photo真实schema支持，均在本轮新增移动能力范围之外；桌面已有能力由离线回归覆盖。

这些检查由VPS执行端按docs/vps-xhs-mobile-acceptance.md完成。本地实现与验证完成不能被描述为已上线。
