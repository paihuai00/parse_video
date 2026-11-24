# 抖音普通视频移动分享页设计

## 接口与运行边界

使用现有 FastAPI、Docker 和 `ParseService`。统一入口按 URL 识别平台，继续返回 `UnifiedParseSuccess`。视频的作品 ID 位于 `data.note_id`，下载地址位于 `data.videos[0].url`。`X-API-Key`、`refresh`、缓存、错误响应和旧小红书路由沿用现有契约。

```text
POST /api/v1/parse
  → 平台识别与 ParseService
  → 小红书适配器，或抖音适配器
  → 抖音普通视频通过移动分享页取得 CDN 直链
  → InternalNote / InternalVideo
  → data.videos[0].url
  → 调用方独立 GET CDN
```

## 抖音采集与回退

1. 用 `parse_douyin_url` 校验输入。对短链逐跳校验后确定作品类型和 ID，保留有效查询参数。已识别的图文走现有浏览器，使用已验证的落地链接和同一作品 ID。
2. 对视频使用仓库锁定的 `curl_cffi`。每次采集建立独立访客会话，访问 `www.iesdouyin.com` 首页接收访客 Cookie，随后在同会话读取 `/share/video/<id>/`。Cookie 的使用范围限于分享站采集。
3. 在有界响应内读取 `window._ROUTER_DATA`，从约定的数据路径选择匹配目标 ID 的作品。若 `play_addr` 指向 `aweme.snssdk.com` 的已验证播放路径，手动处理重定向并保留其原始参数。最终地址须通过精确 CDN 白名单与现有 MP4 识别规则，再进入媒体归一化。
4. 在分享页安全但缺少可用状态或媒体候选时，可在原 `Deadline` 的剩余时间内调用既有浏览器一次。已确定的作品 ID 贯穿回退流程。合法短链若安全结束但尚未建立 ID，旧浏览器入口仍负责判断该短链。ID 不匹配、不安全跳转、明确登录要求、验证、限流和总期限耗尽按现有领域错误处理。

## 约束与兼容

- HTTP 使用精确主机与路径，验证 TLS、逐跳校验公网 DNS，并绑定实际连接地址。沿用现有时限与响应大小约束，关闭自动重定向和环境代理。已证实的播放入口与最终 CDN 分别维护精确白名单。
- 首个全量验证的 CDN 主机为 `v5-se-bjtc-cold.douyinvod.com`。按实际文件可读证据新增主机。浏览器现有 CDN 优先级沿用。
- 视频字段只使用可归属于最终候选的元数据。原作品和带水印媒体的尺寸、时长可能不同，无法确认的字段保持 `null`。运行时 `verification` 保留 `not_checked` 语义，调用方在验收阶段验证文件。
- `refresh: true` 可绕过结果缓存。缓存 `expires_at` 表示服务端缓存期限，`url_expires_at` 仅在掌握真实到期时间时填写。

## 风险与回退

上游移动分享页布局和 CDN 可能随时间及部署网络变化。先在本机 Docker 验证冷启动请求和完整媒体。后续 VPS 使用实际出口网络复验。如果新策略引入回归，可退回原解析路径或原镜像，调用方继续使用同一接口。
