# 抖音移动分享页证据

## 已取得的证据

- 在独立本机 Docker 中，用匿名纯 HTTP 访问分享站首页取得访客 Cookie，再访问移动分享页，成功从 `_ROUTER_DATA` 找到输入作品。直接请求分享页的对照只拿到页面外壳。
- 平台原始播放入口返回精确 CDN 主机上的短期地址。Postman 连续两轮使用独立请求下载目标作品，另用 curl 保存约 6.6 MB 的 MP4，完整解码通过。
- 分享页的作品元数据与下载文件的尺寸或时长存在差异。不可归属于实际媒体候选的字段留空。
- 证据来自独立验证服务。这一仓库的锁定 HTTP 传输和实际 Docker 网络仍需验收。真实样本与密钥在运行时由本地变量提供。

## 仓库接入位置

| 位置 | 用途 |
| --- | --- |
| `app/api/routes.py:52` | 统一入口和公共契约 |
| `app/parser/adapters.py:49` | 抖音采集策略选择 |
| `app/parser/douyin/url_rules.py:59` | 抖音 URL 和作品 ID 校验 |
| `app/parser/client.py:143` | 有界 HTTP、手动重定向和 DNS 绑定参照 |
| `app/parser/douyin/state_reader.py:16` | 有界状态读取和作品 ID 校验 |
| `app/parser/douyin/media.py:11` | 精确 CDN 和 MP4 归一化 |
| `scripts/probe.py:40` | 调用方媒体读取的独立验证 |

已验证链路使用平台原始播放入口，保留水印和参数。 [开源方案](https://github.com/FuzzyLogic112/douyin-downloader#工作原理)
