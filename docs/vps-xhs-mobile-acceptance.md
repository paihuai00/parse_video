# 小红书移动页修复：VPS 验收

此步骤在候选版本构建、启动后执行；不通过修改 `XHS_IMPERSONATE` 代替代码更新。先保留旧版本与配置，记录候选代码版本及镜像 ID/digest。以下命令不会切换镜像、修改配置或导入登录 Cookie。

## 1. 原生运行环境

在部署目录检查实际运行容器：

```sh
docker compose ps
docker compose exec -T api python -c 'import platform; from importlib.metadata import version; print({"python": platform.python_version(), "architecture": platform.machine(), "curl_cffi": version("curl_cffi")})'
```

当前目标是已报告的 `x86_64/Python 3.12/curl_cffi 0.13.0`。`healthy` 只表示应用存活，不表示平台访问或媒体检查成功。实际发布时应记录镜像 ID/digest，不能只记录复用的 `parser-video:0.1.0` 标签。

## 2. 同进程补齐采集、API 与代表图片

以下针对已授权的普通静态图文样本。分别运行两次，输入原始手机短链、完整 PC 长链；不要保留占位文字，不要删除查询参数。Bash 的隐藏输入避免链接进入命令历史。容器已有的 API Key 仅在进程内使用，不打印。

诊断会先直接验证一次 iOS 移动状态，再调用真实旧 API；为补齐之前遗漏的媒体检查，允许这次有明确目的的重新获取。媒体地址只保留在同一进程内，最多检查一张代表图片的前 1024 字节。没有将 scripts/probe.py 假定为镜像内文件。

```sh
read -r -s -p '完整授权分享链接: ' XHS_PROBE_URL
export XHS_PROBE_URL
docker compose exec -T -e XHS_PROBE_URL api python - <<'PY'
import asyncio
import json
import os
import socket
from dataclasses import replace
from http.client import HTTPConnection
from urllib.parse import urlsplit

from curl_cffi import CurlOpt, requests

from app.config import Settings
from app.parser.client import Deadline, XiaohongshuClient
from app.parser.media import normalize_media_url
from app.parser.state_reader import decode_initial_state
from app.parser.url_rules import is_public_address, parse_url


async def acquire(settings, raw_url):
    requested_id = parse_url(raw_url).note_id
    client = XiaohongshuClient(replace(settings, impersonate="safari184_ios"))
    page = await client.fetch(raw_url, Deadline(settings.request_timeout_seconds))
    root = decode_initial_state(page.html)["noteData"]
    note = root["data"]["noteData"]
    images = note.get("imageList", [])
    matched = (
        root.get("hasError") is False
        and note.get("noteId") == page.note_id
        and (requested_id is None or page.note_id == requested_id)
    )
    print(json.dumps({
        "stage": "mobile_acquisition", "id_matches": matched,
        "type": note.get("type"), "images": len(images),
        "live_photo_flags": sum(bool(item.get("livePhoto")) for item in images),
        "nonempty_streams": sum(bool(item.get("stream")) for item in images),
    }), flush=True)
    if not matched:
        raise RuntimeError("identity check failed")
    return requested_id or page.note_id


async def addresses(host):
    infos = await asyncio.wait_for(
        asyncio.get_running_loop().getaddrinfo(host, 443, type=socket.SOCK_STREAM), 5
    )
    values = tuple(dict.fromkeys(info[4][0] for info in infos))
    if not values or not all(is_public_address(value) for value in values):
        raise RuntimeError("unsafe media address")
    return values


def main():
    settings = Settings.from_env()
    raw_url = os.environ["XHS_PROBE_URL"]
    expected_id = asyncio.run(acquire(settings, raw_url))
    connection = HTTPConnection("127.0.0.1", 8000, timeout=25)
    try:
        connection.request(
            "POST", "/api/v1/xiaohongshu/parse",
            body=json.dumps({"url": raw_url, "refresh": True}),
            headers={"Content-Type": "application/json", "X-API-Key": settings.api_key},
        )
        response = connection.getresponse()
        body = response.read(2 * 1024 * 1024 + 1)
        if len(body) > 2 * 1024 * 1024:
            raise RuntimeError("API response too large")
        payload = json.loads(body)
        data = payload.get("data") or {}
        print(json.dumps({
            "stage": "api", "status": response.status,
            "success": payload.get("success"),
            "error_code": (payload.get("error") or {}).get("code"),
            "request_id": (payload.get("meta") or {}).get("request_id"),
            "id_matches": data.get("note_id") == expected_id,
            "images": len(data.get("images") or []),
            "videos": len(data.get("videos") or []),
        }), flush=True)
    finally:
        connection.close()
    if payload.get("success") is not True or data.get("note_id") != expected_id:
        raise RuntimeError("API did not return the requested note")
    if data.get("type") != "image" or not data.get("images"):
        raise RuntimeError("this diagnostic expects an image note")
    url = normalize_media_url(data["images"][0].get("url"))
    if url is None:
        raise RuntimeError("unsupported media candidate")
    host = urlsplit(url).hostname
    values = asyncio.run(addresses(host))
    with requests.Session(
        impersonate="safari184_ios", trust_env=False,
        curl_options={CurlOpt.RESOLVE: [f"{host}:443:{','.join(values)}"]},
    ) as session:
        media = session.get(
            url, headers={"Referer": "https://www.xiaohongshu.com/", "Range": "bytes=0-1023"},
            allow_redirects=False, verify=True, timeout=(5, 10), stream=True,
        )
        try:
            prefix = next(media.iter_content(chunk_size=1024), b"")[:1024]
            mime = media.headers.get("content-type", "").split(";", 1)[0].lower()
            magic_matches = (
                (mime == "image/jpeg" and prefix.startswith(b"\xff\xd8\xff"))
                or (mime == "image/png" and prefix.startswith(b"\x89PNG\r\n\x1a\n"))
                or (mime == "image/webp" and prefix[:4] == b"RIFF" and prefix[8:12] == b"WEBP")
            )
            print(json.dumps({
                "stage": "media", "host": host, "status": media.status_code,
                "content_type": mime, "bytes_examined": len(prefix),
                "magic_matches": magic_matches,
            }), flush=True)
            if media.status_code not in (200, 206) or not magic_matches:
                raise RuntimeError("representative image check failed")
        finally:
            media.close()


try:
    main()
except Exception as exc:
    print(json.dumps({"stage": "failed", "exception_type": type(exc).__name__}), flush=True)
    raise SystemExit(1)
PY
unset XHS_PROBE_URL
```

预期：`mobile_acquisition.id_matches=true`；本样本 `images=1`、动态计数为 0；API 为 `200/success=true/id_matches=true`；媒体为 `200` 或 `206`、符合图片 MIME 且 `magic_matches=true`。计数有变化或出现动态字段时，先核实完整性，不用静态结果替代。

输出保留为脱敏验收摘要即可。失败时只输出异常类型，结合前一阶段、API 错误码和 request ID 定位；不要打印带 URL 的完整异常堆栈或响应正文。该命令的两个解析请求各自有独立 20 秒期限，媒体探测另计，不是一次业务请求获得了额外期限。

## 3. 公网与调用方

- 用相同完整输入验证公网 HTTPS API。容器内成功但公网失败时检查 Nginx/Cloudflare 入站，不直接更改上游解析策略。
- 从真实调用方网络读取返回媒体，记录状态和文件类型。容器内媒体可读不代表客户端网络可读。
- 验证重复请求缓存、refresh、错误 JSON 和 request ID。不要在普通健康探针中循环访问小红书。
- 保留旧镜像引用。候选失败时恢复旧镜像与兼容配置，复查健康及代表请求；不要删除全部容器/镜像替代回滚。

以上实际 VPS 和调用方检查需在目标环境完成，仓库文档或本机测试通过不能将其标记为已执行。

## 4. 海外区域跳转回归（2026-11-06）

VPS 独立候选容器实测发现短链先跳到 `www.xiaohongshu.com` 详情，再跳至 `www.rednote.com` 相同详情。旧白名单在第二个目标前报 `INVALID_URL / unsupported host`。仅加入页面域名后，桌面 `/404` 会触发移动重试；从短链重放会耗尽三次共享跳转额度。候选修复允许精确海外详情域名，并只对海外详情的安全状态跳转重试已校验完整详情 URL；不增加总期限、尝试次数或跳转上限。

候选默认桌面策略及移动兜底已在独立容器中对授权样本返回 1 张图片、0 视频；`sns-i27.rednotecdn.com` 代表图片返回 HTTP 206、JPEG MIME 且文件头匹配，仅检查前 1024 字节。没有保留分享参数、页面内容或媒体地址。此结果不代表生产服务已更新，发布后仍须重新执行三层 API 验收。

生产切换后的连续验收发现图片域名在 `sns-i27.rednotecdn.com` 与 `sns-i11.rednotecdn.com` 间变化，单一图片主机不足以保证成功。补充仅支持 `sns-i<ASCII数字>.rednotecdn.com` 数字分片，继续拒绝其他子域、相似域、凭证及异常端口。

### 生产验收结果（2026-11-06 07:28 UTC 后）

经用户授权，生产已切换至镜像 `sha256:6c0ddd725b2679d168a37104fb617827e74bec54ef3bb67e3bba63a3b052140b`，Compose 保留 `parser-video:0.1.0` 标签及原配置。单实例容器 `51e00733536d` 处于 healthy。207 项离线测试、格式、lint、类型检查通过。

同一授权短链使用 `refresh=true` 连续执行两轮三层请求，均为 HTTP 200、1 张图片、0 视频；六个 request ID 均在新容器日志中确认为 `OK / cache=miss`。本机 Nginx 使用正确域名/SNI及显式源站证书信任，未关闭 TLS 验证。

| 层 | 第一轮耗时 / request ID | 第二轮耗时 / request ID |
| --- | --- | --- |
| 应用本机 8000 | 3.255s / `5f6f78b0-54c8-4950-97c6-ca064409ea39` | 2.345s / `af97784c-87bc-416e-8efd-ba2f7a6d7621` |
| 本机 HTTPS Nginx | 4.057s / `d9c01e19-b3c8-45e3-b64d-ab4c121562f6` | 2.459s / `c173cc35-8c2f-45c5-ab87-75a20bb25fc2` |
| 公网 Cloudflare | 3.240s / `3f20b970-f45f-4e4f-8e36-c7ea2d94892a` | 2.565s / `4a26a116-1c64-4b93-bc05-e15bf5995eb5` |

全部通过后，按用户要求删除旧版本及候选镜像引用，当前仅保留新版本 `parser-video:0.1.0`。旧镜像不再作为本机回滚来源；未执行 Git 写操作。
