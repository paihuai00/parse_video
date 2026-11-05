# 最终规划核查

日期：2026-11-04。用户要求检查是否还有需要确认的问题，并规划下一步执行。结论：无待用户决定的阻塞问题；剩余VPS媒体、长链和完整API检查纳入明确验收，不扩大探索范围。

## 仓库可回答的问题

- 版本差异已核实：git cat-file能找到VPS报告的be32fc77671d7334b759bf9617abd3117271c19d；git merge-base --is-ancestor返回成功；该提交到本地75b3b62的app/tests/scripts/requirements.lock/requirements-dev.lock/pyproject.toml/Dockerfile/compose.yaml/deploy差异为空。期间日志为Trellis归档和journal记录。此前“基线未知”对这些产品文件已经解决；完整镜像溯源仍归发布验收。
- select_note位于app/parser/state_reader.py:146，仅支持桌面noteDetailMap；新增移动分支有明确边界，无需让用户决定字段布局。
- app/parser/media.py:223后的桌面normalizer会跳过无效普通图片槽位，见244-246和253。新的移动完整性要求需在移动分支提前验证全部槽位，避免顺手改变桌面旧行为，或产生部分成功。
- _is_live_photo在app/parser/media.py:215会组合livePhoto、非空stream和其他视频URL证据。VPS只报Live Photo计数0仍需检查stream；该检查可以纳入验收，无需凭截图询问用户内容类型。
- 公共路由、模型与共享ParseService已有清晰边界，客户端内部组合获取策略可保持外部协议与adapter调用契约。

## 已收敛的执行边界

- 首版只对安全详情页的精确同站点/404状态跳转做一次iOS兜底；不对所有INVALID_URL或PARSE_FAILED重试，不对安全拒绝、限流/挑战、超时或任意路径兜底。
- 保持原始期限和parse级有界重试/重定向，不以新会话重新领取预算。
- 移动首版仅承诺已验证的静态图文；逐槽位检查完整性与动态证据。视频/Live Photo的桌面已有支持不退化。
- 不新增登录Cookie、浏览器、付费供应商、媒体主机泛化或公开诊断接口；不自动部署VPS。

## 交付与未决技术验收

prd.md已重写为最终需求/验收结构，design.md记录触发条件及边界，implement.md明确文件、顺序、验证、发布与回滚，两份JSONL为真实规范/研究引用。待执行的质量门使用支持的Python3.12，不将之前Python3.15实验冒充运行时验收。

VPS媒体Range、PC完整长链、stream内容、完整API及调用方读取都有明确后续步骤。若媒体失败或出现动态schema差异，按证据修正实现/范围，不提前宣称成功；这些未知不要求再做一轮账号或浏览器产品决策。

本轮没有运行task.py start、修改产品代码、创建远程部署或声明代码验证通过。
