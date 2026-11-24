# 实施与验证计划

## 实施顺序

1. 在 `app/parser/douyin/` 增加有界 HTTP 采集。复用抖音 URL 规则、`Deadline` 和公网地址校验。把状态读取、媒体跳转与归一化放在既有 parser 层。
2. 在 `DouyinAdapter` 接入普通视频 HTTP 优先及明确回退条件，复用现有 Chromium 和调度限制。通过已有 `InternalNote` 和 `InternalVideo` 输出，保持统一 API、旧小红书入口和健康检查兼容。
3. 增加脱敏离线样本和测试，覆盖访客 Cookie 隔离、短链和视频页、目标 ID、签名查询、MP4 CDN 白名单、DNS 与重定向拒绝、分享页空数据回退及明确权限或限流错误。回归抖音静态图文、动态图文和小红书 API。
4. 在 `docs/postman/` 交付可导入 Collection，包含统一接口、抖音直链 GET 和输入错误验证。使用本地变量填写 API 密钥与授权样本。更新 README、Docker 验收说明及 Trellis 服务契约。核对静态 OpenAPI 与现有响应一致。

## 验证顺序

### 离线质量检查

```sh
ruff format --check app tests scripts
ruff check app tests scripts
mypy app
pytest -q
python -m compileall app tests scripts
python -m json.tool docs/openapi.json >/dev/null
```

### 本机 Docker 和 Postman

1. 在仓库根目录检查 Compose 配置，构建并启动现有 `api` 服务，访问 `127.0.0.1:8000/healthz`。
2. 在 Postman 中用授权小红书链接和抖音目标短链各测一次 `POST /api/v1/parse`。指定 `refresh: true`，抖音返回目标作品 ID，确认该次采集走纯 HTTP。
3. 从响应取得 `data.videos[0].url`，用独立 GET 拉取完整文件，检查 `video/mp4`、文件头和字节数，再对保存的 MP4 做音视频解码检查。
4. 验证抖音视频详情页、抖音静态图文、旧小红书入口和无效域名。记录脱敏证据及 Postman 请求数、断言数和退出码。

## 评审与回退点

方案评审后进入实施。重点核对新出站连接的地址绑定、回退错误边界和直链签名。切换策略前保留原解析镜像作为运行回退点。阶段完成以验收和规范同步为准，Git 写操作由用户负责。
