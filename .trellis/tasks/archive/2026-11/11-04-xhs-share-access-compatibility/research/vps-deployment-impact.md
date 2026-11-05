# VPS 部署影响与验收

日期：2026-11-04。用户明确最终部署目标是 VPS。本轮仅检查仓库部署文件与依赖原始资料，未连接 VPS，未取得目标系统、架构、地域或出口信息。

## 结论

推荐的匿名 iOS 移动页获取可以作为 Linux 服务方案；safari184_ios 是 curl_cffi 的 HTTP/TLS 请求模拟选项，不要求安装 Safari、iOS、macOS 或图形桌面。本机成功仍不能替代 VPS 实测，尤其是出口 IP/网络差异。

## 已有部署条件

- Dockerfile 基于 python:3.12.8-slim-bookworm，锁定 curl_cffi 0.13.0，以 UID/GID 10001、单个 Uvicorn worker 运行。
- compose.yaml 已有只读根、临时可写目录、512 MiB 容器内存、256 PID、并发与队列配置；本次移动 HTTP 获取不新增浏览器进程或本地登录会话存储。镜像已有 Chromium 是抖音能力所需，不能因小红书使用轻量 HTTP 就直接删除它。
- 现有部署文档记录过 linux/arm64 本地镜像验收及另一个 VPS 小红书成功样本，但不是本次 safari184_ios 路线的目标 VPS 验收。
- app/parser/client.py 显式 trust_env=False。宿主机设置 HTTP_PROXY/HTTPS_PROXY 不会自动让该客户端走代理；若将来需要支持受控出口，必须显式设计和验证地址校验/绑定语义，不能把配置环境变量当成已经切换出口。

## 主要影响

1. 出口环境：上游看到 VPS 的出口地址/网络而非用户电脑。IP 所在网络、地区、请求频率、会话与 TLS 特征都可能影响结果。当前没有证据断言这台 VPS 被限制或某个地区必然成功，不能预先承诺换 IP/代理能解决。
2. 入站与出站分开：Cloudflare/Nginx 是调用方到 API 的入站链路；在现有配置下不会改变应用连接小红书的出口 IP。公网 API 返回正常 JSON 不代表上游可访问，/healthz 也不联系小红书。
3. DNS/TLS/路由：在运行容器内验证目标域名解析及 HTTPS；VPS 的 IPv4/IPv6 可达性可能不同。保留逐跳全部 DNS 公网检查、地址绑定及 TLS；遇到超时先隔离实际路由，不为兼容而允许私网或任意主机。
4. 架构与依赖：目标可能是 amd64 或 arm64。必须在原生目标架构验证固定 curl_cffi 导入与 safari184_ios 的真实请求，不能只检查 Python 枚举存在或 Docker build 成功。优先复用现有 Debian/Python 3.12 镜像，不需要为了模拟 iPhone 更换系统。
5. 时延和容量：远端网络耗时可能更长，桌面与移动策略共享原有 20 秒总期限，不应变成两轮各 20 秒。保留单 worker、并发 2、等待队列 4；512 MiB 是现有容器配置，不是整机资源或所有混合抖音负载的容量保证。
6. 媒体使用链路：VPS 能取得直链和读取图片头不等于小程序/浏览器能读取同一 URL。现有架构是调用方直连 CDN，还需调用方网络验证，不能把容器成功当作跨网络媒体可用的保证。

## 最小 VPS 验收顺序

1. 在实际部署架构构建/启动现有镜像；确认 Python 3.12、curl_cffi 0.13.0、safari184_ios 可发起验证 TLS 的请求。先在容器本机端口验收，后测公网入口。
2. 在相同运行容器和出口，使用完整授权短链/长链分别执行 iOS 匿名采集；初步诊断可直接检查 noteData.data.noteData，而不调用尚未适配的 select_note。必须记录目标 ID 是否匹配、hasError、类型和媒体数量，不能仅凭 HTTP 200 验收。
3. 完成移动 schema 适配后，再通过真实 API 重放两个输入并开启 refresh；对本样本要求 1 张完整静态图片、目标身份匹配、无错误。不要仅将 XHS_IMPERSONATE 改为 safari184_ios 后就当成修复，当前选择器和图片归一化仍缺适配。
4. 用有界请求验证至多两个代表媒体文件头；本样本验证一张 JPEG 即可。再由真实调用方读取返回直链。
5. 检查总期限、缓存、排队/并发及公网 Nginx/Cloudflare 错误 envelope；区分入站故障、网络超时、上游状态和解析 schema 失败。保留 request ID、镜像版本和安全阶段标记，不记录完整 URL/token/媒体地址。
6. 目标出口匿名采集成功后才将该 VPS 标为支持；若失败，按 DNS/TLS/状态/schema 分层继续排查，再决定是否需要浏览器/其他服务，不能直接假定必须账号登录。

## 探测工具交付注意

仓库 scripts/probe.py 可以对 API 输出脱敏摘要，但现有 Dockerfile 仅 COPY app，不包含 scripts/；不能要求用户在当前运行镜像中执行不存在的 /app/scripts/probe.py。实施阶段应提供可直接在运行容器中执行的诊断入口，或明确宿主机依赖/脚本路径。不要通过安装新版系统 curl 来替代固定 curl_cffi 的真实指纹验证。

## 原始依赖参考

- https://github.com/lexiforest/curl_cffi/blob/v0.13.0/README.md （HTTP/TLS 指纹模拟与安装/平台说明）
- https://github.com/lexiforest/curl_cffi/blob/v0.13.0/curl_cffi/requests/impersonate.py （固定版本 safari184_ios 选项）

这些资料证明库的机制/配置，不能证明小红书对目标 VPS 的访问结果。
