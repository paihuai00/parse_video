# 小红书与抖音媒体解析 API

这是一个可部署在单台 VPS 上的小流量 JSON API。统一入口接收一条受支持的小红书或抖音链接，服务匿名解析页面并返回完整有序正文图片，或普通视频的一个 MP4 直链及其独立封面。旧小红书入口保留原有图文、视频和 Live Photo 行为。媒体文件由调用方直接从上游 CDN 下载，本服务不代理、保存或转码媒体。

抖音真实验证中，两条普通视频样本和一条静态图文样本在新的匿名无头浏览器上下文中自动解析成功，代表 MP4 与 WebP 均由独立 HTTP 会话读取 1024 字节并核对文件头；第四条样本的图片槽位带 2.033 秒动态 MP4，按首版范围返回 `UNSUPPORTED_CONTENT`。样本结论和容器结果见 [抖音实现验收](docs/douyin/implementation-evidence-2026-10-20.md)。

## 快速开始

需要 Python 3.12：

```sh
python3.12 -m venv .venv
. .venv/bin/activate
pip install -r requirements.lock
python -m playwright install --no-shell chromium
export XHS_API_KEY='替换为随机长密钥'
uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 --workers 1
```

健康检查不会访问任一内容平台：

```sh
curl --fail http://127.0.0.1:8000/healthz
```

通过统一入口解析一条完整分享 URL：

```sh
curl --request POST http://127.0.0.1:8000/api/v1/parse \
  --header 'Content-Type: application/json' \
  --header "X-API-Key: $XHS_API_KEY" \
  --data '{"url":"<完整小红书或抖音分享链接>","refresh":false}'
```

旧调用方可继续使用 `POST /api/v1/xiaohongshu/parse`。成功响应中的 `images[].url`、可选的 `images[].live_video.url` 或 `videos[0].url` 是临时直链。普通图片省略 `live_video`；小红书 Live Photo 的静态图和动态 MP4 保持在同一个图片项中。抖音动态图片首版明确拒绝，避免静默丢失运动部分。

## Docker

复制配置并设置密钥：

```sh
cp .env.example .env
# 编辑 .env，填写 XHS_API_KEY
docker compose config --quiet
docker compose build
docker compose up -d
```

Compose 默认只绑定 `127.0.0.1:8000`，以 UID/GID `10001`、单 Uvicorn worker、只读文件系统运行。`/tmp` 与非 root 浏览器的 `/home/app` 分别使用有界 tmpfs，后者为 Chromium 配置和 crashpad 元数据提供临时可写目录。镜像包含固定版本 Chromium，并应用配套的 seccomp sandbox profile；每次抖音解析使用独立浏览器进程和匿名上下文，PID、并发、请求数、隧道字节及总时限均受限。公网接入示例见 `deploy/nginx.conf.example`。

2026-10-20 的本机 Docker Desktop `linux/arm64` 验收确认了缺失/空生产密钥会启动失败、容器健康检查通过，并且 512 MiB 内存、256 PID、只读根、64 MiB `/tmp`、16 MiB 非 root HOME 与 `json-file` 日志轮转配置已应用。受限容器内的抖音真实请求成功，但内存发生上限回收，因此生产保持浏览器并发 1 并在目标 VPS 复测。该结果不替代目标 VPS 验收。

## 离线验证

```sh
pip install -r requirements-dev.lock
ruff format --check app tests scripts
ruff check app tests scripts
mypy app
pytest -q
```

真实探测必须显式提供一至两条有权使用的链接，脚本只输出脱敏摘要，包括图片数、Live Photo 数和普通视频数：

```sh
XHS_API_KEY="$XHS_API_KEY" python -m scripts.probe '<小红书或抖音链接>'
```

`--check-media-headers` 会读取最多两个代表性媒体的文件开头；含 Live Photo 时最多选择一张静态图和一个动态 MP4。`--full-download` 会完整下载同样的最多两个媒体，只应在确认带宽和内容后使用。两项检查都与单纯页面解析分开记录。

## 设计边界

- 精确支持 `www.xiaohongshu.com`、`xiaohongshu.com` 的 `/discovery/item/{id}`、`/explore/{id}`，以及逐跳校验的 `xhslink.com` 短链和手机复制的 `xhslink.cn/o/<token>`。`.cn` 相似域名、子域名及其他路径不受支持。
- 固定 `curl_cffi==0.13.0` 和 `chrome136`，每次解析使用新的匿名 Cookie 会话。
- 固定 `playwright==1.64.0` 和配套 Chromium。抖音浏览器全部 HTTPS 连接经回环 CONNECT 代理：精确主机白名单、逐连接公网 DNS 校验，并直连已检查 IP；默认一次最多 500 个浏览器请求、32 MiB 双向隧道流量、2 MiB 页面状态及 1 个浏览器任务。
- 逐跳手动处理最多三次重定向；拒绝非公网 DNS 结果，并通过 `CURLOPT_RESOLVE` 绑定已检查的地址。
- 解压后的 HTML 上限 2 MiB；总时限 20 秒，连接时限 5 秒。
- 成功缓存默认 120 秒、最多 256 条；每密钥每分钟 20 次；最多两个上游任务和四个等待者。
- 支持图文中的 Live Photo：静态图保留原顺序，动态 MP4 放在对应图片的 `live_video`；缺少受支持动态 MP4 时失败，不返回残缺的静态结果。
- 不支持账号登录、调用方 Cookie、验证码绕过、直播、未知混合媒体、批量解析、媒体代理或永久存储。
- 抖音首版支持普通视频与静态图文；图片槽位带动态 MP4 的作品返回 `UNSUPPORTED_CONTENT`。

## 文档

| 文件 | 内容 |
| --- | --- |
| [技术方案](docs/technical-design.md) | 请求链路、解析规则、安全边界和资源控制 |
| [接口契约](docs/openapi.json) | OpenAPI 3.1 公共契约 |
| [响应示例](docs/examples/) | 请求、普通图文、Live Photo 图文、视频和错误 JSON |
| [实施清单](docs/implementation-plan.md) | 已验证工作和仍需外部执行的验收项 |
| [部署说明](docs/deployment.md) | Docker、Nginx、VPS 验收与回滚 |
| [抖音实现验收](docs/douyin/implementation-evidence-2026-10-20.md) | 四样本、媒体可读性、浏览器与资源证据 |
| [匿名验证记录](docs/evidence/anonymous-probe-2026-10-17.json) | 早期 5 篇笔记的脱敏可行性证据 |
| [Live Photo 探测记录](docs/evidence/live-photo-probe-2026-10-18.json) | 单篇授权样本的脱敏数量与有界文件头检查 |
| [手机短链探测记录](docs/evidence/mobile-short-link-probe-2026-10-18.json) | 授权 `xhslink.cn/o/<token>` 样本的脱敏跳转形态与安全控制 |

示例中的 `media.example.com` 和 `YOUR_SHARE_TOKEN` 都是占位符，不能用于下载或成功率验证。
