# 下一步执行计划

状态：本地实现、独立复核与用户Postman验收完成。用户明确要求归档并自行提交Git；候选VPS检查移交部署阶段，以下未完成项保留真实状态。AI不提交、不推送、不操作VPS。

## 1. 开始前的执行准备

- [x] 核对VPS报告的Git与本地基线：be32fc7为当前75b3b62祖先，产品代码/测试/依赖/部署文件无差异；后续仅Trellis记录。
- [x] 收集本机两种输入的iOS数据与代表图片证据、VPS短链iOS获取证据。
- [x] 完成PRD收敛、design及implement/check上下文清单。
- [x] 按Trellis实现阶段加载backend规范；在支持的Python3.12建立锁定依赖验证环境。此操作可本地完成，不需要用户提供服务器密码或Cookie。

## 2. 传输及错误分类

主要文件：app/parser/url_rules.py、app/parser/client.py；仅在内部错误类型确需共享时调整app/errors.py。

- [x] 复用/提取现有协议、精确主机、凭证和端口校验；不扩大调用者可提交的笔记URL范围。
- [x] 对已校验详情页的精确同站点/404跳转，生成可识别的内部获取失败类别，不请求错误页，不推断-510001语义。
- [x] 精确登录目标保持登录错误；任意其他路径、外站/相似域、私网DNS和不安全目标仍拒绝。不存在明确缺失证据时不返回NOTE_NOT_FOUND。
- [x] 在客户端内部仅对上述/404类别调用一次safari184_ios策略，保留完整原始URL、独立匿名会话及TLS/DNS/地址绑定；不全局改XHS_IMPERSONATE。
- [x] 两策略共享原始Deadline、准入及parse级重试/跳转预算；检查已有桌面重试与移动兜底的组合上限，不新建完整期限或独立跳转额度。超时、取消和预算耗尽及时清理。

## 3. 移动状态与静态图片适配

主要文件：app/parser/state_reader.py、app/parser/media.py；只有边界编排需要时调整app/parser/adapters.py。

- [x] 保留桌面选择分支，新增精确noteData.data.noteData选择，校验hasError、字段类型及目标noteId；继续使用有界状态解码器。
- [x] 新增H5_DTL与有明确详情语义的直接图片URL候选；复用现有精确CDN和HTTPS规范化，拒绝仅有H5_PRV的预览结果。
- [x] 移动普通静态图文要求所有图片槽位均有效，保留顺序、数量和尺寸；不因跳过损坏槽位而返回部分成功。
- [x] 检查livePhoto、stream及已识别动态字段。首版移动视频/动态内容缺乏验证，不允许静态降级；已有桌面视频、Live Photo和抖音行为保持兼容。

## 4. 离线回归与文档

主要文件：tests/test_url_rules.py、test_client.py、test_state_reader.py、test_media.py、test_api.py、test_contract.py；按影响补充test_parse_service.py/test_logging.py及合成fixture。

- [x] 覆盖桌面/404→移动成功、移动失败、相对跳转、精确登录/未知错误及最终错误语义。
- [x] 覆盖输入/重定向/DNS安全拒绝时零兜底，原始期限与总请求预算、超时/取消清理。
- [x] 覆盖移动ID错配、hasError异常、结构/深度/大小限制、空列表、非法/缺失图片槽位、顺序、尺寸、未知媒体主机及预览唯一候选。
- [x] 覆盖动态标记与非空stream不能静态伪成功，桌面图文/视频/Live Photo、两路API契约及共享服务预算不退化。
- [x] 更新README、docs/technical-design.md、docs/deployment.md和backend/service-contract.md。只有公开说明需要变化时更新OpenAPI描述，不改变请求/响应schema。
- [x] 交付可在运行容器执行的内联脱敏诊断命令；当前镜像仅COPY app，不能要求执行不存在的/app/scripts/probe.py。优先复用现有宿主机probe，不引入额外诊断服务或公开接口。

Python3.12质量门：

```sh
ruff format --check app tests scripts
ruff check app tests scripts
mypy app
pytest -q
python -m compileall app tests scripts
python -m json.tool docs/openapi.json >/dev/null
```

常规测试完全离线，使用合成ID/媒体URL，不保存真实输入、页面、Cookie或签名URL。

## 5. 候选镜像与VPS验收

本地代码实现与离线验证完成后，交付可审阅差异、测试结果和发布/回滚步骤。实际生产切换不包含在本轮自动执行范围。

- [ ] 给候选代码和镜像使用可追溯版本/digest，保留旧镜像与配置，验证目标原生x86_64镜像运行。
- [ ] 通过VPS执行端在实际容器出口补PC完整长链及手机短链验证；完整参数保留在内存，不传占位文字。
- [ ] 检查当前样本每张图片的stream内容与动态标记。之前只得到Live Photo计数0，不等于已审查stream。
- [ ] 在同一诊断进程中取得页面、选择媒体并立即完成一次有界Range检查；明确允许为补验收重新获取一次，不因前次遗漏永久跳过。最多检查两文件，当前静态样本检查一张即可。
- [ ] 用真实产品API验证短链和长链，要求目标ID匹配、所有已支持图片完整、error=null。再验证公网入口和真实调用方CDN读取。
- [ ] 检查refresh/缓存、并发、失败JSON、request_id及安全日志。healthz/构建通过或PARSE_FAILED变成另一错误码均不算完成。
- [ ] 若验收失败，按网络/上游状态/schema/媒体分层记录与修复；证据不足时不转向账号、浏览器、代理或付费服务。新的技术/产品范围再单独评估。

## 6. 完成与回滚

- [x] 全部相关离线门和本地真实验收有明确结果；用户确认本地正常，剩余外部检查由VPS执行端负责，不宣称已上线成功。
- [x] 变更与规范一致且已独立复核。按用户指示以--no-commit归档和记录会话；代码及记录由用户自行提交。
- [ ] 移动策略/状态适配与错误分类可独立回退；发布失败恢复已保留的旧镜像和兼容配置，再验证健康和代表请求。无需清理全部容器/镜像。
