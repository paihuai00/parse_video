# 暂停、恢复与回滚交接（2026-10-20）

## 关闭方式

本任务由用户明确要求暂停并归档。归档是为了停止当前推进、保留上下文，不表示 P4 目标 VPS 验收通过。归档时已知的生产阻塞是：目标 VPS 上 Chromium 可以启动，但抖音作品获取在 60 秒独立诊断期限内仍触发 `UPSTREAM_TIMEOUT`。

## Git 锚点

- `04037bd2340b802bc1938e74a9b35ffd8b60750a`（`merge xhs\dy`）：抖音解析、统一入口、受控浏览器、容器约束、测试和文档的主体实现。该提交只有一个父提交，不是 Git merge commit。
- `be32fc77671d7334b759bf9617abd3117271c19d`（`fix dy parse bug`）：为只读容器增加可写 `/home/app` tmpfs 及 HOME/XDG 配置，解决原生 Linux 上 Chromium Crashpad `SIGTRAP`。
- `8ffe3aeeef0d8a273bb98c105e5a0c6e03348cab`：抖音主体实现之前的仓库锚点。

如需只撤销容器 HOME 修复，可 revert `be32fc7`，但目标 VPS 会重新出现 `chrome_crashpad_handler: --database is required` 和 `SIGTRAP`。如需完整撤销本任务，按新到旧顺序 revert `be32fc7`、再 revert `04037bd`，并单独删除 VPS Nginx HTTPS server 中新增的精确 `/api/v1/parse` location。回滚前应从当前分支创建备份分支或标签，且不要用 reset 覆盖其他后续提交。

## 已验证结果

- 本地受限容器中，普通抖音视频可自动返回主 MP4，静态图文可返回完整有序正文图片；动态图文样本按范围返回 `UNSUPPORTED_CONTENT`。
- 统一入口 `POST /api/v1/parse` 支持小红书与抖音；旧 `POST /api/v1/xiaohongshu/parse` 保留。
- 本地最终检查通过 132 项测试、Ruff、mypy、依赖检查、OpenAPI/JSON、Compose 和受限 Chromium 启动。
- 容器继续使用非 root UID/GID 10001、Chromium sandbox、seccomp、只读根、512 MiB 内存、256 PID、64 MiB `/tmp` 和 16 MiB `/home/app` tmpfs。

## VPS 已知状态

1. HTTPS Nginx 已增加 `/api/v1/parse` 并转发到 `127.0.0.1:8000`；统一入口解析小红书成功。
2. 初次抖音请求返回 502。VPS 复现 Chromium 在 Crashpad 初始化时退出：`chrome_crashpad_handler: --database is required`、`SIGTRAP`。
3. `be32fc7` 后容器内 HOME/XDG 均指向 `/home/app`，目录所有者为 `app:app`、模式 0700；Chromium 取得 `LAUNCH_OK`、`PAGE_OK`、退出码 0。D-Bus 缺失日志不是启动失败。
4. 启动问题修复后，公网请求改为 504；直接在容器内以 60 秒 `Deadline` 调用 `DouyinBrowser.fetch_detail` 仍得到 `Douyin browser timed out`。因此 Nginx 不是这一轮超时的根因，也没有据此修改现有 20 秒对外期限。
5. 下一步应运行已准备的分段诊断，分别记录受控代理启动、浏览器启动、导航 commit、`DOMContentLoaded` 和最终页面位置，以区分 CONNECT/DNS/TLS、页面脚本挂起与详情捕获问题。

## 恢复时先做

1. 从归档目录读取本文件、`prd.md`、`design.md`、`implement.md` 和 `docs/douyin/implementation-evidence-2026-10-20.md`。
2. 确认部署代码包含 `04037bd` 和 `be32fc7`，并确认 VPS 实际使用的 Compose 配置仍挂载 `/home/app`。
3. 保持浏览器并发 1，不先提高 20 秒对外期限，也不移除 sandbox、seccomp、主机白名单或公网 DNS 校验。
4. 先完成分段导航诊断，再决定是修复 CONNECT 地址选择、将导航等待拆成 commit/DOM 两阶段，还是记录 VPS 出口限制。
5. 轮换曾在排障会话中公开粘贴的 API Key；日志和仓库中不得记录新值、Cookie、签名媒体 URL 或完整样本 token。

