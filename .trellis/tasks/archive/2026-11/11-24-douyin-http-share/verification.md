# 本机验收记录

2026-11-24 在本机 Docker Desktop 的 `linux/arm64` 环境重建 Compose API，`127.0.0.1:8000/healthz` 返回 200。所有 Postman 请求经本机执行，结果未发布到共享工作区。

| 验收项 | 实测结果 |
| --- | --- |
| 离线质量检查 | Ruff 检查和格式、mypy、compileall、OpenAPI 与 Postman JSON 检查通过，403 项 pytest 通过 |
| Postman 基础检查 | 健康、缺少 API 密钥和无效域名 3 项断言通过，退出码 0 |
| Postman 抖音视频 | 两条授权视频都通过统一接口解析与独立 GET，4 项断言通过，退出码 0 |
| 纯 HTTP 路径 | 从最终容器调用真实适配器，替换浏览器入口为立即失败后，两条视频都解析成功 |
| 完整视频 | 原目标从 `v5-se-bjtc-cold.douyinvod.com` 下载 6,925,849 字节，H.264 与 AAC 完整解码。新增样本从 `v9-chc.douyinvod.com` 下载 1,338,582 字节，视频完整解码 |
| Postman 小红书 | 三条新的授权短链在统一入口与旧入口均为 HTTP 200，其中两条视频、一条图文，6 项断言通过，退出码 0 |
| 抖音动态图文 | 授权链接落到移动 `/share/slides/`，按同 ID 进入现有图文流程，HTTP 422 `UNSUPPORTED_CONTENT` |

静态抖音图文与浏览器回退由离线用例验证。VPS 网络和目标客户端的媒体可达性留待部署时复测。真实作品 ID、分享口令、API 密钥及媒体签名 URL 未写入此记录。
