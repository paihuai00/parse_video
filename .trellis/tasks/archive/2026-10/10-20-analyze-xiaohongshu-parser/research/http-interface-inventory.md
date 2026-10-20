# 当前 HTTP 接口清单

## 1. 对外接口总览

当前 FastAPI 应用只注册 3 个业务路由（`app/api/routes.py:23-77`）：

| 方法 | 路径 | 鉴权 | 用途 |
| --- | --- | --- | --- |
| `GET` | `/healthz` | 无 | 仅检查本地服务进程能否响应 |
| `POST` | `/api/v1/xiaohongshu/parse` | `X-API-Key` | 旧版兼容入口，只解析小红书 |
| `POST` | `/api/v1/parse` | `X-API-Key` | 统一入口，自动识别小红书或抖音 |

`app/main.py:34-40` 明确关闭了 FastAPI 自带的 `/docs`、`/redoc` 和 `/openapi.json`，因此它们不是部署后的公开 HTTP 接口。`deploy/nginx.conf.example:17-50` 也只使用精确 `location = ...` 转发上述 3 条路径，不代理媒体文件。

## 2. `GET /healthz`

用途：进程级存活检查。

请求：

```http
GET /healthz
```

成功响应：

```json
{"status":"ok"}
```

特征：

- 不要求 `X-API-Key`（`app/api/routes.py:23-25`）。
- 不访问小红书或抖音，不验证匿名解析、缓存、DNS、浏览器或媒体直链是否正常。
- Nginx 读取超时为 5 秒（`deploy/nginx.conf.example:17-21`）。

## 3. `POST /api/v1/xiaohongshu/parse`

用途：保留给旧调用方的小红书专用接口。

请求：

```http
POST /api/v1/xiaohongshu/parse
Content-Type: application/json
X-API-Key: <部署方配置的 API key>

{
  "url": "https://www.xiaohongshu.com/explore/<24位note_id>?xsec_token=...",
  "refresh": false
}
```

请求字段：

| 字段 | 必填 | 约束 | 语义 |
| --- | --- | --- | --- |
| `url` | 是 | 完整 HTTP(S) URL，最长 4096 字符 | 支持小红书详情长链、`xhslink.com` 和精确 `xhslink.cn/o/<token>` 短链 |
| `refresh` | 否 | boolean，默认 `false` | 跳过本服务成功结果缓存；仍受鉴权、限流、并发、排队和总时限限制 |

额外 JSON 字段会被拒绝，因为 `ParseRequest` 继承 `StrictModel(extra="forbid")`（`app/models.py:56-62`）。应用请求边界和 Nginx 均限制请求体最大 8 KiB（`app/main.py:20,75-116`、`deploy/nginx.conf.example:9`）。

这个入口不会自动识别抖音：它省略 `platform` 参数，固定使用 `ParseService.parse` 的默认 `xiaohongshu`（`app/api/routes.py:33-38`、`app/services/parse_service.py:50-60`）。

成功 envelope：

```json
{
  "success": true,
  "data": {
    "note_id": "<24位十六进制ID>",
    "title": "...",
    "type": "image 或 video",
    "images": [],
    "videos": [],
    "cover": null
  },
  "error": null,
  "meta": {
    "request_id": "...",
    "parsed_at": "...",
    "cache": {"hit": false, "expires_at": "..."}
  }
}
```

图文时 `images` 非空、顶层 `videos=[]`、`cover=null`；Live Photo MP4 位于所属图片的 `live_video`。普通视频时 `images=[]`、`videos` 恰好一个、`cover` 可空。

## 4. `POST /api/v1/parse`

用途：当前推荐的统一解析入口。

请求形状和鉴权与旧入口相同：

```http
POST /api/v1/parse
Content-Type: application/json
X-API-Key: <部署方配置的 API key>

{"url":"<一条受支持的小红书或抖音链接>","refresh":false}
```

差异：

- 路由先调用 `detect_platform(raw_url)`，根据精确主机和路径选择小红书或抖音适配器（`app/api/routes.py:57-66`、`app/parser/adapters.py:60-68`）。
- 小红书请求与旧入口进入同一个 `XiaohongshuAdapter`，可共享内部缓存和同 key 在途任务。
- 成功响应使用 `UnifiedParseSuccess`，`note_id` 允许小红书 24 位十六进制 ID 或抖音 18–20 位十进制 ID（`app/models.py:125-174`）。
- 错误 envelope 结构不变，但公开文案使用“小红书或抖音/内容平台/作品”等中性表达（`app/api/error_handlers.py:24-39`）。

建议调用方新接入时使用该入口；旧入口的价值主要是维持既有小红书客户端兼容性。

## 5. 通用请求与响应约束

### 请求头

- 两个解析接口必须发送 `X-API-Key`；它是本服务访问密钥，不是小红书账号、Cookie 或 token（`app/api/auth.py:12-20`）。
- JSON 请求应发送 `Content-Type: application/json`。
- 调用方不需要发送 `X-Request-ID`；应用会为每次调用生成新的 request ID。Nginx 示例虽然向上游传递自身 `$request_id`，但当前 FastAPI 中间件仍自行生成 UUID（`app/main.py:48`）。

### 响应头与 envelope

- 每个响应携带 `X-Request-ID`，值与 JSON `meta.request_id` 相同。
- 成功固定为 `success=true, error=null`。
- 失败固定为 `success=false, data=null`，错误对象包含 `code`、`message`、`retryable`。
- 限流或繁忙错误可能携带 `Retry-After`。

### 主要状态码

| HTTP | 典型错误码 |
| --- | --- |
| 200 | 成功 |
| 400 | `INVALID_REQUEST`、`INVALID_URL` |
| 401 | `UNAUTHORIZED` |
| 404 | `NOTE_NOT_FOUND`、`ROUTE_NOT_FOUND` |
| 405 | `METHOD_NOT_ALLOWED` |
| 413 | `INPUT_TOO_LARGE` |
| 422 | `UNSUPPORTED_CONTENT` |
| 429 | `RATE_LIMITED` |
| 500 | `INTERNAL_ERROR` |
| 502 | `UPSTREAM_BAD_RESPONSE`、`PARSE_FAILED`、`MEDIA_NOT_FOUND` |
| 503 | `BUSY`、`UPSTREAM_LOGIN_REQUIRED`、`UPSTREAM_ACCESS_RESTRICTED`、`UPSTREAM_RATE_LIMITED` |
| 504 | `UPSTREAM_TIMEOUT` |

## 6. 对上游发出的 HTTP 请求

对外 API 之外，小红书适配器会发起出站 HTTP GET，但没有调用固定的“小红书 JSON API 接口”：

1. GET 调用方提交的、经过校验的小红书详情页或短链。
2. 遇到 301/302/303/307/308 时，读取 `Location`，重新执行 URL、DNS 和公网地址校验后，再 GET 下一跳。
3. 最终只接受受支持的小红书详情页并读取 HTML 中的 `window.__INITIAL_STATE__`。

出站请求配置位于 `app/parser/client.py:97-186`：关闭自动重定向和环境代理、启用 TLS 校验、使用 `CurlOpt.RESOLVE` 固定已验证 IP，发送 HTML `Accept`、中文优先 `Accept-Language` 和 `Referer: https://www.xiaohongshu.com/`，并限制总时限、跳转数和 HTML 大小。

返回给调用方的 CDN URL 不会由 API 服务主动请求或代理；调用方拿到临时直链后直接访问上游 CDN。

## 7. 已发现的接口文档问题

`POST /api/v1/parse` 在 `docs/openapi.json` 中复用 `ParseRequest`。该 schema 的 `url` 字段描述仍写成“单个完整 HTTP(S) 小红书笔记链接”，没有列出抖音 URL；但接口 operation 的描述和实际代码都支持小红书与抖音。

这不会影响运行时解析，却会误导根据 OpenAPI 生成文档或 SDK 的调用方。若后续进入修复阶段，建议为共享字段使用中性描述，或为旧入口与统一入口拆分请求 schema，同时保持线上 JSON 形状不变。
