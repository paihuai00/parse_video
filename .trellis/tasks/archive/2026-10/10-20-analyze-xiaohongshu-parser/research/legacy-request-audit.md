# 旧请求逻辑存量审计

## 结论

当前仓库不存在一套“新接口之外、仍在生产目录中闲置”的旧小红书 HTTP 请求实现。

历史上的小红书页面请求代码没有被新代码复制后遗留，而是在新增统一接口时被包进 `XiaohongshuAdapter` 继续复用：

```text
/api/v1/xiaohongshu/parse ─┐
                           ├→ ParseService → XiaohongshuAdapter
/api/v1/parse（小红书 URL）─┘                    ↓
                                      XiaohongshuClient.fetch
```

删除 `app/parser/client.py`、`url_rules.py`、`state_reader.py` 或 `media.py` 中所谓“旧逻辑”，都会直接破坏两个目标接口的小红书解析能力。

## Git 历史证据

### `9132a09`：第一版小红书接口

该提交已经包含：

- `POST /api/v1/xiaohongshu/parse`
- `XiaohongshuClient`
- 小红书 URL/DNS 校验
- `window.__INITIAL_STATE__` 读取
- 小红书媒体归一化
- `scripts/probe.py`

当时没有 `/api/v1/parse`。

### `04037bd`：新增统一接口

该提交新增：

- `POST /api/v1/parse`
- `detect_platform`
- `XiaohongshuAdapter` / `DouyinAdapter`
- 抖音浏览器获取逻辑

原来的小红书客户端没有被复制；`XiaohongshuAdapter.parse` 直接调用现有 `XiaohongshuClient.fetch`，随后调用现有状态读取和媒体归一化函数（`app/parser/adapters.py:31-44`）。

因此当前形态是“新入口复用旧能力”，不是“新旧两套请求能力并存”。

## 当前代码分类

### A. 两个接口运行必需，不可作为遗留删除

| 代码 | 作用 | 删除影响 |
| --- | --- | --- |
| `app/api/routes.py` | 注册两个目标接口 | 对应接口消失 |
| `app/api/auth.py` | 两个解析接口的 API key 鉴权 | 失去鉴权或启动失败 |
| `app/services/parse_service.py` | 限流、缓存、合并、准入、适配器调用 | 两个平台均无法解析 |
| `app/parser/adapters.py` | 新接口到各平台实现的分流边界 | 两个平台均无法解析 |
| `app/parser/client.py` | 小红书实际 HTML 请求 | 两个接口的小红书解析失效 |
| `app/parser/url_rules.py` | 小红书 URL、DNS、SSRF 和缓存身份 | 小红书请求失去安全入口或无法运行 |
| `app/parser/state_reader.py` | 解析小红书页面状态 | 无法从 HTML 得到笔记 |
| `app/parser/media.py` | 生成小红书媒体结果 | 无法返回图片/视频 |
| `app/parser/douyin/*` | `/api/v1/parse` 的抖音获取与归一化 | 统一接口的抖音能力失效 |

### B. 保留两个接口时仍属兼容必需

以下代码看起来像“旧逻辑”，实际是 `/api/v1/xiaohongshu/parse` 独立契约所需：

- `ParseSuccess`、`ImageNote`、`VideoNote`、`to_public_note`：维持小红书 24 位十六进制 ID 约束。
- `MESSAGES` 与按路径选择文案：旧接口继续使用“小红书笔记/页面”措辞，统一接口使用“作品/内容平台”措辞。
- Nginx 中两个独立 exact location 和两套网关错误文案。
- 旧接口相关契约、API、日志和跨入口缓存测试。

如果用户明确要同时保留 `/api/v1/parse` 与 `/api/v1/xiaohongshu/parse`，这些都不能按“遗留”删除。

### C. 不参与服务运行，可选删除

`scripts/probe.py` 是唯一包含真实 HTTP 调用、但完全不被 FastAPI 服务导入的模块：

- `api_parse` 使用 `urllib.request` 调用部署后的 `/api/v1/parse`，可通过 `--legacy-xiaohongshu` 改调 `/api/v1/xiaohongshu/parse`。
- `check_media` 可选访问最多两个返回的 CDN 媒体，读取文件头或完整下载。
- 该脚本只用于人工部署验收和真实网络探测；删除不会改变任何服务端接口。

删除它的连带范围包括：

- 删除 `scripts/probe.py`。
- 删除 `tests/test_probe.py`。
- 清理 README、部署文档和质量规范中的 probe 使用说明。
- `curl-cffi` 不能随之删除，因为生产小红书客户端仍依赖它。
- `httpx` 不能随之删除，因为 FastAPI `TestClient` 测试依赖它。

是否删除 probe 属于产品/运维选择：收益是减少一个辅助脚本和相关文档；代价是失去脱敏的真实部署验收工具与媒体头检查能力。

### D. 不是旧业务请求逻辑

- Docker/Compose 健康检查中的 `urllib.request.urlopen('/healthz')` 只是容器健康检查，删除会影响容器健康状态，不是旧解析接口。
- Nginx 的 `proxy_pass` 是两个目标接口和健康检查的反向代理，不是旧出站请求。
- tests 中的 `TestClient`、fake session 和示例 URL 是离线回归，不参与生产网络请求。
- `.trellis/tasks/archive`、`docs/douyin` 中的“旧入口”文字是设计与历史记录，不是可执行请求代码。
- `__pycache__/*.pyc` 未被 Git 跟踪，不属于应提交的源码删除范围。

## 推荐删除边界

如果目标是只保留两个新接口及其后端解析能力，推荐：

1. 保留全部 `app/` 请求、解析和兼容代码。
2. 仅在不再需要部署后真实探测时删除 `scripts/probe.py` 及其测试/使用文档。
3. 不重写 Git 历史；旧实现的历史版本只存在于提交记录中，不影响当前产物。

如果真正目标是删除某个平台的上游抓取能力，则这不是“清理遗留代码”，而是接口功能变更，需要明确小红书/抖音哪个输入以后应返回什么结果。

## 最终决定

用户确认本次不删除代码。生产请求链路、兼容逻辑和 `scripts/probe.py` 均保持现状；任务在分析交付完成后直接归档。
