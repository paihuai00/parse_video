# 技术设计索引

权威设计：[docs/douyin/technical-design.md](../../../docs/douyin/technical-design.md)。

2026-10-20 已确认调整：[以实际解析成功为目标的交付方案](../../../docs/douyin/delivery-plan.md)。允许受控服务端浏览器候选，先完成最小真实解析实现；规划复核未发现新的用户决策。

- 用户已确认统一入口 `/api/v1/parse`，保留旧小红书入口。
- 复用请求/媒体/envelope 与服务资源，独立平台 URL、状态和媒体规则。
- 旧入口保留严格 ID 与响应契约；统一入口适配抖音字符串 ID。
- 架构、数据流、缓存命名空间、错误文案、配置兼容及技术取舍在权威设计中维护，避免重复漂移。
- 证据：[复用分析](../../../docs/douyin/reuse-analysis.md)、[样本研究](../../../docs/douyin/sample-analysis.md)。
- 历史 P0 起点：[P0 实测](../../../docs/douyin/p0-data-loading-2026-10-19.md)确认初始状态只有目标引导信息。当前本地实现、完整作品读取、代表媒体可读性和基础容器运行已经验收，目标 VPS 验收仍待执行。
- 运行与回滚：[实施计划](../../../docs/douyin/implementation-plan.md)。

状态：本地实现与真实样本验收完成；统一入口、适配器、受控浏览器和容器交付已落地，目标 VPS 验收待执行。结果见[实现验收证据](../../../docs/douyin/implementation-evidence-2026-10-20.md)。
