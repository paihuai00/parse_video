# Docker 部署与验收清单

仓库已提供统一 API、`Dockerfile`、`compose.yaml`、`.env.example` 和 Nginx 示例。Compose 配置、本机 `linux/arm64` 镜像构建和容器运行已通过验收；小红书授权样本及抖音普通视频/静态图文均完成本地脱敏探测。目标 VPS 架构、出口网络及调用方媒体读取仍需部署者按本文执行验收。用户自行在已有 Docker 的 VPS 上部署，无需提供 SSH 密码或服务器密钥。

## 1. 目标运行方式

- Python 3.12，基础镜像采用 `python:3.12.8-slim-bookworm`；仍需在目标 Linux 架构验证镜像构建。
- FastAPI + Uvicorn，固定 **1 个 worker**，容器内监听 `0.0.0.0:8000`。
- 固定 `curl_cffi==0.13.0` 和 `XHS_IMPERSONATE=chrome136`，保留 TLS 证书验证。已验证的本地匿名请求组合是第一版基线，升级库或浏览器配置必须重新验证样本。
- 固定 `playwright==1.64.0` 及配套 Chromium。抖音解析使用新的匿名浏览器进程和上下文，完整 Chromium 沙箱开启；应用进程仍以 UID/GID 10001 运行。
- 单进程使用内存缓存、并发限制和有界等待队列，不依赖数据库、Redis 或任务服务。重启清空这些内存状态；增加 worker 会让限流与缓存分裂，不能直接作为扩容办法。
- API 只返回图片、每张小红书图片可选的 Live Photo 动态 MP4、普通视频主地址及元数据，不代理、保存或转码媒体。调用方直接访问对应平台 CDN。
- 本机端口只映射至 VPS 的 `127.0.0.1:8000`，公网入口通过现有 Nginx 提供 HTTPS。

## 2. 配置约定

API 使用请求头 `X-API-Key`，服务端密钥变量统一为 **`XHS_API_KEY`**，不另设 `API_KEY` 别名。生产环境缺失或为空时必须启动失败，不能退化为公开无鉴权模式。`GET /healthz` 不要求密钥，只返回必要的健康状态，不包含配置、Cookie 或上游访问详情。

以下内容已写入 `.env.example`；密钥必须在部署时替换，示例不提供可用默认密钥。

```dotenv
XHS_API_KEY=
XHS_ENV=production
XHS_IMPERSONATE=chrome136
XHS_REQUEST_TIMEOUT_SECONDS=20
XHS_CONNECT_TIMEOUT_SECONDS=5
XHS_UPSTREAM_CONCURRENCY=2
XHS_QUEUE_CAPACITY=4
XHS_QUEUE_WAIT_SECONDS=2
XHS_CACHE_TTL_SECONDS=120
XHS_CACHE_MAX_ENTRIES=256
XHS_RATE_LIMIT_PER_MINUTE=20
XHS_MAX_REDIRECTS=3
XHS_MAX_HTML_BYTES=2097152
XHS_DOUYIN_BROWSER_CONCURRENCY=1
XHS_DOUYIN_BROWSER_MAX_REQUESTS=500
XHS_DOUYIN_BROWSER_MAX_BYTES=33554432
XHS_DOUYIN_STATE_MAX_BYTES=2097152
XHS_DOUYIN_BROWSER_CHANNEL=
```

20 秒是从请求准入开始的完整处理时限，包含排队、跳转、重试和解析，不能在每次跳转或重试时重新计时；排队同时受 2 秒上限约束。Nginx 的等待时间应略大于应用的完整处理时限，让应用优先返回契约中的错误。HTML 上限按解压后的正文计算。缓存 TTL 不代表媒体直链的有效期。

部署时从 `.env.example` 复制生成 `.env`，在本地生成随机密钥后填入；`.env` 不提交到版本控制，权限限制为部署用户可读。密钥只提供给受信任的服务端调用方，不能写进公开网页前端。

## 3. Compose 配置

`compose.yaml` 使用本地构建的 `parser-video:0.1.0` 标签；该标签不是远程仓库中的可拉取镜像。Dockerfile 创建 UID/GID `10001`，安装锁定依赖，并以单 worker 启动 Uvicorn。实际文件还启用了只读文件系统和 `/tmp` tmpfs。

```yaml
services:
  api:
    build: .
    image: parser-video:0.1.0
    user: "10001:10001"
    env_file:
      - path: .env
        required: false
    ports:
      - "127.0.0.1:8000:8000"
    restart: unless-stopped
    init: true
    mem_limit: 512m
    pids_limit: 256
    security_opt:
      - seccomp=./deploy/chromium-seccomp.json
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
    healthcheck:
      test:
        - CMD
        - python
        - -c
        - "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2).read()"
      interval: 30s
      timeout: 3s
      retries: 3
      start_period: 10s
    read_only: true
    tmpfs:
      - /tmp:size=64m,mode=1777,noexec,nosuid
```

`required: false` 只用于让交付仓库在尚未创建本机 `.env` 时也能执行静态配置校验；
生产进程仍会在 `XHS_API_KEY` 缺失或为空时拒绝启动。部署前仍必须按上文创建 `.env`。

`deploy/chromium-seccomp.json` 固定取自 Playwright `v1.64.0` 官方 Docker 配置，以 Docker 默认 seccomp 为基础额外允许 Chromium 沙箱需要的 `clone`、`setns` 和 `unshare`；不要删除该配置或改用 `--no-sandbox`。本地抖音容器实测在 512 MiB 限制内完成真实解析，没有 OOM；该值不是所有架构和负载的最低保证。日志写标准输出，不向镜像目录写文件；`PYTHONDONTWRITEBYTECODE=1` 避免生成字节码。只读文件系统与临时目录行为仍需在目标 Docker 主机验证。

Docker 健康检查只证明应用本身能响应；不向小红书发请求，避免健康探针消耗请求配额。`restart: unless-stopped` 会处理进程退出，但容器仅变为 `unhealthy` 时不会自动重启，需保留告警或人工排查入口。

## 4. 分阶段启动与接入

### 第一步：本机构建

以下交付文件已经存在；带“目标架构”的条件仍需在 Docker 主机验证：

| 交付物 | 验收要求 |
| --- | --- |
| `Dockerfile` | Python 3.12 slim、固定依赖、非 root、单 worker；本机 `linux/arm64` 构建通过，目标 VPS 原生架构仍待验证 |
| `compose.yaml` | 本机端口绑定、资源与日志限制、健康检查；配置校验通过 |
| `.env.example` | 列出配置和默认值，密钥为空；实际 `.env` 被版本控制忽略 |
| API 应用 | 实现解析入口、鉴权、健康检查、统一错误格式和请求编号 |
| Nginx 接入模板 | 不覆盖已有配置；代理层错误与 API 契约一致 |

文件交付后，在部署目录运行：

```sh
docker compose config --quiet
docker compose build
docker compose up -d
docker compose ps
```

2026-10-18 在 Docker Desktop `linux/arm64` 上完成的本机证据如下：

- `docker compose config --quiet` 和镜像构建通过；锁定的 `curl_cffi==0.13.0` 安装了原生 aarch64 wheel。
- 当时本机访问 Docker Hub 鉴权端点发生 TLS 超时，因此先从 AWS Public ECR 的 Docker Official Images 镜像取得同一 `python:3.12.8-slim-bookworm` 标签（digest `sha256:2199a62885a12290dc9c5be3ca0681d367576ab7bf037da120e564723292a2f0`），在本机重打标签后使用 `--pull=false` 完成构建。该结果不证明目标部署网络能从 Docker Hub 冷启动拉取基础镜像。
- 缺失和显式为空的生产 `XHS_API_KEY` 均以退出码 1 拒绝启动；配置临时本地测试密钥后，`docker compose up -d` 和 `/healthz` 通过，容器状态为 `healthy`。
- 运行进程为 UID/GID `10001:10001`，进程表只有一个带 `--workers 1` 的 Uvicorn；实际端口映射为 `127.0.0.1:8000`。
- 运行态检查确认 cgroup 内存上限为 512 MiB、根文件系统只读、`/tmp` 使用 tmpfs，并应用 `json-file` 的 `max-size=10m`、`max-file=3` 配置。

这些证据覆盖本地容器交付，不覆盖真实页面匿名访问、目标 VPS 原生架构、HTTPS、调用方媒体下载或回滚演练。

不要将完整渲染配置或 `.env` 粘贴到公开日志中。先在运行 Docker 的机器上访问健康接口：

```sh
curl --fail --silent --show-error http://127.0.0.1:8000/healthz
```

解析请求的契约固定为：

```http
POST /api/v1/parse HTTP/1.1
Content-Type: application/json
X-API-Key: <部署时设置的密钥>

{"url":"<完整小红书或抖音分享链接>","refresh":false}
```

初次验证保留分享链接的完整查询参数。`refresh:true` 只能跳过结果缓存，不能绕过鉴权、限流、并发或队列限制。具体成功及错误 JSON 以 API 契约文档为准，部署层不另定义一套返回结构。

统一入口还支持精确 `v.douyin.com` 短链、`www.douyin.com/video/<id>`、`www.douyin.com/note/<id>` 及已验证的 iesdouyin 分享路径。旧 `POST /api/v1/xiaohongshu/parse` 保留原行为。相似域和其他路径会返回 `INVALID_URL`；服务不会为了兼容短链而放宽 DNS、公网地址、端口或最终详情页校验。

### 第二步：先通过本机端口或 SSH 隧道验收

用户可在 VPS 本机调用上述接口，或在自己电脑上建立已有 SSH 账号的本地转发：

```sh
ssh -N -L 18000:127.0.0.1:8000 <已有SSH用户>@<VPS地址>
```

此时在用户电脑访问 `http://127.0.0.1:18000`。使用用户已有的 SSH 配置及认证方式，不需要向本项目提供密码或私钥。此阶段不必开放公网 8000 端口。

### 第三步：接入现有 Nginx 的 HTTPS 站点

在已有配置之外新增专用站点或经确认的 API 路由，先备份涉及的配置，再检查并平滑加载，不覆盖现有业务。完整起点见 `deploy/nginx.conf.example`；以下只展示核心转发关系：

```nginx
location = /api/v1/parse {
    proxy_pass http://127.0.0.1:8000;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-API-Key $http_x_api_key;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 30s;
}
```

该示例假定 Nginx 运行在 VPS 宿主机；若 Nginx 也在容器中，它的 `127.0.0.1` 指向自身，必须改用经过确认的容器网络连接方式，不能照抄上游地址。TLS 证书和域名使用现有配置或用户自行配置的证书方案。

上线模板还必须处理下列事项：

- 统一入口请求体限制；由 Nginx 产生的 `413`、`502`、`503`、`504` 必须返回 API 契约规定的 JSON 字段、业务错误码、`Content-Type` 和请求编号。完整错误映射在实现阶段与 API 一并交付，不能把默认 HTML 错误页作为最终行为。
- 保留应用已返回的错误 JSON，不能用笼统的代理错误页覆盖更明确的上游失败原因。
- 只信任实际受控的代理链；如按来源 IP 限流，由 Nginx 与应用共同配置可信代理，不直接信任调用方伪造的 `X-Forwarded-For`。
- 不记录 `X-API-Key`、完整分享令牌或签名媒体 URL；使用请求编号关联代理与应用日志。
- 不新增媒体代理路由。图片和视频地址由调用方自行使用，跨域或下载权限问题不会因 API 使用 HTTPS 自动消失。

修改后先运行 `nginx -t`，检查通过再按现有部署方式 reload；不直接替换全局配置或重启其他站点。

## 5. VPS 与调用方两端验收

### 5.1 已记录的 VPS Live Photo case（2026-10-19）

一次用户授权的手机复制短链在 VPS 上成功跳转到标准详情页并返回 7 张有序图片；7 张图片均带有 Live Photo 的 H.264 动态流，顶层 `videos` 为空。该 VPS 样本使用了此前本地样本未出现的精确媒体主机：`sns-video-v28.xhscdn.com`、`sns-bak-v11.xhscdn.com`、`sns-bak-v10.xhscdn.com`。这些主机已加入精确白名单并有回归测试；不扩展为任意 `*.xhscdn.com`。记录未保存分享令牌、签名媒体 URL、HTML 或 API 密钥。

本地匿名解析成功不代表任意 VPS 出口都成功。至少用现有图文、视频样本完成以下检查，并记录镜像版本、网络环境、时间和结果；不要在记录中保留敏感令牌。

1. **应用状态：** 缺少密钥时拒绝启动；错误密钥拒绝解析；`/healthz` 能独立响应。
2. **VPS 解析：** 保留完整分享链接进行匿名请求；成功结果必须包含匹配的笔记 ID 和支持的媒体，不能把跳转登录后的 HTTP 200 当作解析成功。Live Photo 图文应保持图片顺序，并把动态 MP4 放在所属图片的 `live_video`，顶层 `videos` 仍为空。
3. **媒体可用性：** 从 VPS 检查代表性图片和 MP4，再从真实调用方网络读取相同直链。服务端可读不代表调用方 IP、Referer 或浏览器环境同样可读；记录需要的条件，不默认承诺跨网络长期可用。
4. **缓存与容量：** 重复请求命中缓存；刷新请求仍受限制；同链接并发请求合并；队列满、等待超时和超频返回预定错误，不无限等待。
5. **失败可诊断：** 区分超时、平台登录要求、访问验证、限流、笔记不可见和结构解析失败；未知原因保持未知，不统一误报为“链接失效”。
6. **代理契约：** 验证 Nginx 产生的 `413/502/503/504` 与应用错误使用同一 JSON 结构；应用原始错误原因不会被覆盖。
7. **容器限制：** 非 root 运行、内存与日志限制生效；若启用只读文件系统，重启和解析均通过；重启后缓存丢失属于预期。

网页中的宽高是来源元数据，不一定等于所返回 CDN 文件的实际尺寸。直链也可能带签名或时效限制；缓存有效期不能用作其到期时间。遇到调用方下载失败，应保留 HTTP 状态、发生位置和请求编号，先判断是解析阶段还是媒体访问阶段失败，不反复更换账号或无上限重试。

## 6. 版本、回滚与架构兼容

每次正式部署使用可追溯的版本标签或镜像 digest，保存上一版镜像及配套配置。不要在生产中追随 `latest`，也不要独立升级 `curl_cffi` 或切换 `XHS_IMPERSONATE` 后省略回归验证。

更新顺序为：构建候选镜像 → 本机端口验收 → 小范围真实调用验收 → 切换版本。若失败，恢复上一版镜像引用与兼容配置，执行 `docker compose up -d --no-build`，再检查 `/healthz` 和一条代表性解析请求。回滚前保留失败日志中的请求编号、业务错误码和版本信息；不要用清理全部容器、镜像或卷来替代回滚。

目标 VPS 可能是 `linux/amd64` 或 `linux/arm64`。Python 基础镜像存在对应架构，不代表固定版本 curl_cffi 的二进制依赖在该架构必然可用；实现阶段必须在目标架构验证安装、导入、TLS 请求和样本解析。若某架构不满足依赖条件，应明确标注支持范围或单独解决构建问题，不能默默改为最新版依赖。首版不承诺多架构发布，也不将 QEMU 模拟运行视为原生验证。

## 7. 部署相关任务拆分

| 阶段 | 任务 | 完成标准 |
| --- | --- | --- |
| D1 | 固定请求与 API 行为 | 在实现中冻结匿名请求配置、鉴权及错误契约；现有样本验证通过 |
| D2 | 容器交付 | 补齐 Dockerfile、Compose、环境示例；目标 Linux 架构构建和非 root 启动通过 |
| D3 | 单机运行验证 | 在本机端口或隧道完成健康、解析、缓存、并发和失败检查 |
| D4 | HTTPS 接入 | 提供完整 Nginx 模板，统一代理错误 JSON；保留已有站点配置 |
| D5 | VPS 与调用方验收 | 两端验证媒体访问条件，保存失败原因，形成明确支持范围 |
| D6 | 发布与回滚 | 固定镜像版本，保留上一版，实际演练一次回滚 |

当前已完成 D1 的离线实现、D2/D4 的文件交付、D2 的本机 `linux/arm64` 构建和运行验收，以及 D3 的本地抖音真实解析。目标 VPS 与调用方验收、HTTPS 接入和实际回滚演练尚未执行。
