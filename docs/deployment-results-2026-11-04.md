# 小红书匿名移动页修复部署结果

验收时间：2026-11-04 22:00–22:04 US/Eastern（2026-11-05 03:00–03:04 UTC）。

本次修复已在 VPS 生效：两种完整输入的真实产品 API、统一入口及代表图片检查通过。真实调用方网络读取仍待用户验证。

## 版本与回滚

- 分支：main；Git HEAD：`210c607d87e2ce5f15ab1a8c00abcbce0a7aaa42`。
- 原容器：`c46970574947232484dc47ce70bcbfbbe8575f612c6504ccf8b6b7daabfafeb6`。
- 原实际镜像：`sha256:1a565f11742e9f623c23b254412d83792cb3ba330351e23e9cfd054be5ce07d8`。
- 回滚标签：`parser-video:rollback-20261105T030030Z`，未清理旧镜像。
- 新容器：`1b66fcb844f1d3af9cc60beb0b5e4883de13042399dabe1448e6910597c37d9a`。
- 新实际镜像：`sha256:d685af67e81d7e32698d01f3a014baae70b2da43052f38fd9e774ac08d8598aa`，与构建后的镜像 ID 一致。
- 配置备份：`/tmp/parse-video-deploy-20261105T030030Z`，目录 0700、文件 0600，包含原 .env、Compose、Dockerfile、seccomp 与部署元数据。/tmp 不作为长期备份保证。
- 未回滚；未执行 Git add/commit/push，未拉取或覆盖已有修改。原有未跟踪诊断任务目录保留。

## 构建和运行确认

`docker compose config --quiet` 通过；Compose v5.1.1 支持所需参数。执行 `docker compose build api`，正常利用依赖缓存并更新 COPY app 层；构建期间旧服务持续运行。随后执行 `docker compose up -d --no-deps --no-build --force-recreate --wait --wait-timeout 120 api`，仅重建 parse_video 项目的 api 服务。

宿主与容器内 app/parser 顶层六个 Python 模块 SHA-256 全部一致，包含 client、adapters、state_reader、media。运行环境 x86_64 / Python 3.12.8 / curl_cffi 0.13.0；healthy，宿主与容器内 `/healthz` 均返回 status=ok。保留单 worker、127.0.0.1:8000、512 MiB、256 PIDs、只读根文件系统；鉴权存在、production、XHS_IMPERSONATE=chrome136。未修改业务配置、依赖、TLS/DNS 校验或 Nginx。

## 真实验收

输入为用户提供的手机短链及保留全部查询参数的 PC 长链；本记录不保存分享令牌或媒体 URL。目标笔记 ID：`6aeaebe9000000000602c083`。

| 检查 | 手机短链 | PC 长链 |
| --- | --- | --- |
| 文档容器内移动采集 | 目标匹配，1 张图片 | 目标匹配，1 张图片 |
| 原始 livePhoto 标志 / 非空 stream | 0 / 0 | 0 / 0 |
| 旧产品 API，首次 refresh=true | 200，success=true，目标匹配，1 图、0 视频 | 同左 |
| 同诊断进程代表图片 Range | 200，image/jpeg，JPEG 文件头匹配 | 206，image/jpeg，JPEG 文件头匹配 |
| 统一 /api/v1/parse，refresh=true | 200，success=true，error=null，cache miss | 同左 |
| 统一入口重复请求 | 200，cache hit | 同左 |
| 公网 HTTPS 旧产品 API，refresh=true | 200，success=true，error=null，目标匹配，1 图 | 同左 |

Range 请求为 bytes=0-1023，流式读取前 1024 字节后关闭，不下载完整媒体。短链媒体服务返回 200，长链返回 206；两者 MIME 与文件头均匹配。产品输出中 live_video 均为 0，并已检查原始 stream，样本为静态图文。

公网入口为 `https://xiguahong.dpdns.org/api/v1/xiaohongshu/parse`，从 VPS 容器发起、启用系统 CA 的 TLS 验证。该结果覆盖本次从 VPS 访问公网入站链路，不替代真实调用方网络验证。

文档旧 API request_id：
- 短链：`b9a2c1d9-123c-487a-8c0b-b912e4e40a06`
- 长链：`3d21014e-738f-4a89-a170-a6586eb22136`

统一刷新 / 缓存 / 公网 request_id：
- 短链：`a88cadd2-2456-4f64-905b-995f5c230c07` / `ebd4f4a6-b9d4-421f-8b0c-c0f3283476a6` / `2b5245a3-5feb-4bf5-b041-5fc89dad8461`
- 长链：`fe0c2e45-8240-4aa9-ad1d-37fe29f41687` / `47dc6233-1db6-4c07-9f70-bd337d94f662` / `20320402-f698-4d82-b573-8be9cc5cd8b7`

全部 request_id 独立。出站页面与媒体获取、应用解析、Nginx/Cloudflare 公网入站均未观察到本次验收错误。宿主回环健康检查最初在工具沙箱网络下无法连接，转为宿主网络后通过，属于诊断工具边界，不是服务故障。

## 待用户验证

从真实调用方网络请求 API 并读取返回媒体，记录 HTTP 状态与文件类型。VPS 媒体可读不证明其他网络可读，也不保证签名媒体长期有效。
