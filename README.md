# 小红书媒体解析 API

这是一个可部署在单台 VPS 上的小流量 JSON API。调用方提交一条受支持的小红书分享链接，服务匿名解析页面并返回正文图片直链，或一个 MP4 直链及其独立封面。媒体文件由调用方直接从上游 CDN 下载，本服务不代理、保存或转码媒体。

当前已完成 P1–P4 的应用代码、离线测试和容器交付文件。Python 3.12 离线测试、静态检查和 Compose 配置校验已通过；真实小红书链接、Docker 镜像运行、VPS 出口、HTTPS 和调用方下载仍需在部署环境验收。

## 快速开始

需要 Python 3.12：

```sh
python3.12 -m venv .venv
. .venv/bin/activate
pip install -r requirements.lock
export XHS_API_KEY='替换为随机长密钥'
uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 --workers 1
```

健康检查不会访问小红书：

```sh
curl --fail http://127.0.0.1:8000/healthz
```

解析一条完整分享 URL：

```sh
curl --request POST http://127.0.0.1:8000/api/v1/xiaohongshu/parse \
  --header 'Content-Type: application/json' \
  --header "X-API-Key: $XHS_API_KEY" \
  --data '{"url":"<完整小红书分享链接>","refresh":false}'
```

成功响应中的 `images[].url` 或 `videos[0].url` 是临时直链。调用方应尽快下载；重新解析可以取得当前页面提供的地址，但不能保证延长上游签名寿命。

## Docker

复制配置并设置密钥：

```sh
cp .env.example .env
# 编辑 .env，填写 XHS_API_KEY
docker compose config --quiet
docker compose build
docker compose up -d
```

Compose 默认只绑定 `127.0.0.1:8000`，以 UID/GID `10001`、单 Uvicorn worker、只读文件系统运行。公网接入示例见 `deploy/nginx.conf.example`。

## 离线验证

```sh
pip install -r requirements-dev.lock
ruff format --check app tests scripts
ruff check app tests scripts
mypy app
pytest -q
```

真实探测必须显式提供一至两条有权使用的链接，脚本只输出脱敏摘要：

```sh
XHS_API_KEY="$XHS_API_KEY" python -m scripts.probe '<分享链接>'
```

`--check-media-headers` 会读取最多两个媒体的文件开头；`--full-download` 会完整下载最多两个媒体，只应在确认带宽和内容后使用。两项检查都与单纯页面解析分开记录。

## 设计边界

- 精确支持 `www.xiaohongshu.com`、`xiaohongshu.com` 的 `/discovery/item/{id}`、`/explore/{id}`，以及逐跳校验的 `xhslink.com` 短链。
- 固定 `curl_cffi==0.13.0` 和 `chrome136`，每次解析使用新的匿名 Cookie 会话。
- 逐跳手动处理最多三次重定向；拒绝非公网 DNS 结果，并通过 `CURLOPT_RESOLVE` 绑定已检查的地址。
- 解压后的 HTML 上限 2 MiB；总时限 20 秒，连接时限 5 秒。
- 成功缓存默认 120 秒、最多 256 条；每密钥每分钟 20 次；最多两个上游任务和四个等待者。
- 不支持账号登录、调用方 Cookie、验证码绕过、实况图、批量解析、媒体代理或永久存储。

## 文档

| 文件 | 内容 |
| --- | --- |
| [技术方案](docs/technical-design.md) | 请求链路、解析规则、安全边界和资源控制 |
| [接口契约](docs/openapi.json) | OpenAPI 3.1 公共契约 |
| [响应示例](docs/examples/) | 请求、图文、视频和错误 JSON |
| [实施清单](docs/implementation-plan.md) | 已验证工作和仍需外部执行的验收项 |
| [部署说明](docs/deployment.md) | Docker、Nginx、VPS 验收与回滚 |
| [匿名验证记录](docs/evidence/anonymous-probe-2026-10-17.json) | 早期 5 篇笔记的脱敏可行性证据 |

示例中的 `media.example.com` 和 `YOUR_SHARE_TOKEN` 都是占位符，不能用于下载或成功率验证。
