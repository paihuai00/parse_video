# 统一 VPS 媒体解析与中转 API

统一入口 `POST /api/v1/parse` 识别小红书、抖音、B站或既有通用分享链接。小红书保持现有匿名自解析；抖音在 VPS 内依次请求 bugpk `/douyin`、`/dyjx`、ifphp `/svparse`、bugpk `/short_videos`；B站使用 `/bilibili`、`/short_videos`；通用路径只调用固定 `/short_videos`。不接受客户端指定提供方，不新增原生抖音兜底。

开启 `MEDIA_PUBLICATION_ENABLED=true` 后，响应中的图片、视频、动态 MP4 和封面 `url` 直接返回 `MEDIA_PUBLIC_ORIGIN` 下的短期中转地址。客户端直接 GET，不需要额外申请下载地址。VPS 实时转发媒体，不保存完整文件或转码。默认关闭该开关用于分阶段上线；新客户端在关闭期间不得直接下载 CDN URL。

完整配置、兼容和上线门槛见 [统一解析与媒体中转](docs/unified-vps-media.md)。本次实现只进行离线验证；第三方接口在实际 VPS 上的可达性、CDN完整文件及微信真机预览/相册行为尚未验证。原生抖音历史验收见 [原生抖音实现验收](docs/douyin/implementation-evidence-2026-10-20.md)，不代表迁移后的第三方链路已验收。

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

旧调用方可继续使用 `POST /api/v1/xiaohongshu/parse`。开启发布开关后，成功响应中的 `images[].url`、可选的 `images[].live_video.url`、`videos[0].url` 和 `cover.url` 是自有域名下可重复使用的临时中转地址。普通图片省略 `live_video`；小红书 Live Photo 的静态图和动态 MP4 保持在同一个图片项中。第三方抖音动态图片必须保留完整图片槽位与动态视频配对；不完整或未知的动态结构拒绝为静态图成功。

### 在 Postman 中下载抖音视频

导入 [本机验收 Collection](docs/postman/parse-video.postman_collection.json)，在本地环境中填写 `apiKey` 和 `douyinUrl`。默认服务地址为 `http://127.0.0.1:8000`。运行 **抖音视频** 文件夹，先解析，再向返回的 `data.videos[0].url` 发送独立 GET。也可以把这个地址复制到新的 GET 请求中保存 MP4。直链过期时重新解析原分享链接。

**小红书回归**和**抖音图文回归**分别使用授权样本变量 `xiaohongshuUrl` 和 `douyinImageUrl`。

## Docker

复制配置并设置密钥：

```sh
cp .env.example .env
# 编辑 .env，填写 XHS_API_KEY
docker compose config --quiet
docker compose build
docker compose up -d
```

Compose 默认只绑定 `127.0.0.1:8000`，以 UID/GID `10001`、单 Uvicorn worker、只读文件系统运行。当前统一接口在服务端调用第三方抖音链。仓库保留的原生抖音代码及 Chromium 依赖与统一入口隔离，不会被静默接入新的兜底。其临时文件位于有界的 `/tmp` 或 `/home/app`。公网接入示例见 `deploy/nginx.conf.example`。

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
- 固定 `curl_cffi==0.13.0`，桌面策略默认 `chrome136`；已校验详情页跳转到同主机精确 `/404`，或返回 HTTP 200 且正文为零字节时，允许一次 `safari184_ios` 匿名移动页兜底。空响应重试完整详情地址。两种策略共享原始总期限、重试和跳转预算，不需要安装 Safari 或提供登录 Cookie。
- 移动页支持完整普通图文及具有完整配对 MP4 的 Live Photo，校验目标 ID、错误标记及每个图片槽位，优先使用 `H5_DTL` 详情图；预览图、缺图或无法配对的动态内容不会被当作完整静态结果返回。移动普通视频仍不支持。
- 固定 `playwright==1.64.0` 和配套 Chromium。抖音浏览器全部 HTTPS 连接经回环 CONNECT 代理：精确主机白名单、逐连接公网 DNS 校验，并直连已检查 IP；默认一次最多 500 个浏览器请求、32 MiB 双向隧道流量、2 MiB 页面状态及 1 个浏览器任务。
- 逐跳手动处理最多三次重定向；拒绝非公网 DNS 结果，并通过 `CURLOPT_RESOLVE` 绑定已检查的地址。
- 解压后的 HTML 上限 2 MiB；总时限 20 秒，连接时限 5 秒。
- 成功缓存默认 120 秒、最多 256 条；每密钥每分钟 20 次；最多两个上游任务和四个等待者。
- 支持图文中的 Live Photo：静态图保留原顺序，动态 MP4 放在对应图片的 `live_video`；缺少受支持动态 MP4 时失败，不返回残缺的静态结果。
- 不支持账号登录、调用方 Cookie、验证码绕过、直播、未知混合媒体、批量解析、永久媒体存储或转码。
- 原生抖音历史代码仍拒绝动态图文；当前第三方链以独立适配支持配对动态视频，实际来源可用性仍须验收。

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
