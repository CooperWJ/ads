# ADS 能力搭建与验收矩阵

实现入口、已测命题和外部集成分别记录。局部通过不自动关闭整阶段。任务编号沿用 ADS-PLAN-003。

| 任务 | 当前入口或产物 | 已获得的证据 | 未完成或边界 |
|---|---|---|---|
| A00–A02 | 虚构原始来源、冻结种子、参考/空/故障变体 | M0/M1 真 HTTP、DB、导出、Node、Chromium 校准 | 历史业务材料仅作为问题背景，不复制入核心 |
| A03 | `poc/development_slice/docker_grade.py` | 候选内部容器、外部 UI/API/DB；参考通过，两类坏变体失败 | 不是受保护评分方；主机共享内核 |
| A04 | Harbor 原生任务与独立 verifier | 三例实际 Docker trial，0 异常，reward 1/0/0 | 只证明导出产物边界，不证明 OpenCode 内置适配兼容 |
| A05 | 官方 Playwright Test Agents initializer | 三个 Agent 被 OpenCode 原生识别 | MCP 状态未显示服务器，模型执行未验证；保留实际探测摘要 |
| A06 | 原生 OpenCode、Session 与恢复审计 | 历史父子 Session、本机重入观察、当前 CLI 实测 | 严格恢复协议本机复测和工具中途崩溃仍未验证 |
| A07–A08 | `ads benchmark`、生态采用决策 | 配对条件、三轴、成本/时延、失败与未知保留的测试 | 原生/旧框架/ADS 的实际盲测受模型额度阻断；不自动采用 |
| B01 | `ads discover` | MD/SVG/XLSX、真实 PDF 文本、Docling/Figma JSON 适配测试 | 无 OCR、真实 Figma API/视频语义；未读区域显式 UNKNOWN |
| B02/B04 | `ads reconcile` | 整片来源遗漏、未知义务映射、未决语义不能通过 | 语义裁决和审查者独立身份依赖外部权威 |
| B03 | `ads compile` | OpenSpec 原文与必验测试派生、整场景缺口、整规格新增失效 | 不提供第二套业务规格或审批；只读消费已确认基线 |
| B05 | 语义摘要与物理指纹分离 | 限定的空白行重绑定保留既有决定，规则变化需复审 | 不把复杂文本等价交给哈希猜测 |
| C01 | `ads route`、OpenCode 薄入口 | 缺陷优先、已有路由保留、初始化不覆盖测试 | 原生模型自动执行仍受额度阻断 |
| C02 | `ads context` 与多仓快照 | 新增未跟踪文件、提交、来源/配置/知识漂移均失效 | 来源正确性由项目权威确认 |
| 测试命令进程结果 | `behavior.json.test_command_process_results` | 分别统计可识别测试命令退出码为 0、非 0、未知的次数 | 不证明测试实际执行了断言、测试发现数或业务正确性 |
| 最后编辑后的验证观察 | `behavior.json.final_verification_after_last_direct_edit` | 比较最后直接编辑与最后可识别测试事件，记录成功/失败/未观察/不确定 | 不证明测试意图、需求覆盖或间接编辑 |
| 开发变更范围记录 | `ads develop` 的 `change_set` | 从执行前后 Git 快照记录跟踪及未忽略文件的新增/修改/删除路径及计数；快照不可读为 UNKNOWN | 不覆盖忽略文件，不自动判断改动是否超出需求 |
| 原始需求启动 | `ads init`、TASK.md、开发上下文 | 缺契约时实际子进程可启动；新增映射使上下文失效；正式 verify 仍拒绝缺契约 | 子进程适配测试不代表模型完成开发 |
| C03 | 项目 Profile、必验集合、多仓检查 | Python 与 Node 两个真实测试进程集成，多仓任一变化使证据失效 | 真实 AI 子代理完成并集成整个切片尚未证明 |
| C04 | 原生单次调用、超时进程组清理、漂移阻断 | POSIX 子进程中断试验，不自动回放未知副作用 | 不承诺远程/数据库操作的通用恰好一次 |
| 验证回执低敏行为摘要 | `ads verify` 的 `development_binding.behavior_summary` | 复用开发摘要中哈希绑定的技能/测试/编辑计数与顺序状态 | 不证明技能遵循、测试意图或业务正确性 |
| 开发行为证据与验证绑定 | `behavior.json`、`.ads/latest-development.json`、`ads verify` 的 `development_binding` | 唯一开发运行 ID、输出快照、行为证据与摘要 SHA-256 精确绑定；匹配、代码漂移、证据无效和无关联分别分类 | 只证明版本/证据关联，不证明 Skill 遵循、测试意图或业务语义正确 |
| 会话续接与异常收尾 | `ads develop --session`、本轮摘要 | 原生参数单次传递、真实 SIGINT 清理后落盘、契约损坏仍保留失败记录 | 不证明模型续接成功或远程副作用幂等 |
| C05 | 缺陷路由、执行错误与报告分类 | 真实断言失败、缺报告、超时、skipped/flaky 拒绝 | 因果调试由原生 Agent 和项目测试负责；没有第二个修复循环 |
| D01 | 容器外 Chromium 旅程 | 参考实际通过；菜单和错误状态故障被检出 | 虚构已确认范围，不推广为所有 UI 正确 |
| D02 | JUnit/Playwright 标准报告、真实 SQLite/API | 两栈和多仓进程、原基准 DB 写入/权限/API 测试 | Java/Testcontainers 由项目 Profile 接入，未声称已测试所有技术栈 |
| D03 | `ads qa import/evaluate/defects`、QA 独立 role | 多 Sheet/隐藏 Sheet、无 Requirement ID、缺预期、DEV 不能替代 QA、PASS+PENDING 阻断 | 只消费外部决策，不自签 QA_ACCEPTED；真实 QA 身份未提供 |
| QA 先导入 | `ads qa import` | 缺契约仍保留原始用例与质量结果，对照明确 BLOCKED；evaluate 不借导入成功通过 | 导入不是需求一致性确认 |
| D04 | 新运行目录、源码/输入/报告/日志绑定 | 旧报告、报告篡改、输入漂移、数量不符被拒绝 | 本地记录不是签名证明 |
| E01 | `ads gate` 与受信执行边界 | 配置缺权限不放行、真实保护设置适配测试 | 当前连接读取保护接口 403；未证明保护策略已启用 |
| E02 | `ads attest`、构建 provenance 工作流、`ads smoke` | 冷安装、真实 HTTP 身份反例、主分支标准 attestation 签署及精确来源/摘要验证（41215258915） | 无生产部署目标或发布授权 |
| E03 | 来源作为数据、路径/权限边界、独立评分容器 | 来源指令不执行、越界/符号链接/报告污染拒绝 | 原生模型提示注入红队与完整凭据审计未验证 |
| F01 | 三轴对照结果投影 | 相同模型/预算/案例/种子要求、Wilson 区间和成本保留 | 缺实际 holdout/fresh 盲测与独立效果结论 |
| F02 | 单一 CLI、只读派生视图、既有 QA 决策适配 | 不新建 OpenSpec/QA 状态机；原生路由保留测试 | 不自动删除外部项目的历史资料或签署迁移验收 |

## 必须保留的外部阻断

1. **模型调用额度**：实际 OpenCode 返回 `provider.free-limit` / 429。不能用参考解或本助手代写候选冒充原生开发。
2. **受保护策略权限**：连接读取分支保护返回 403。构建/CI 成功不能代替权限边界。
3. **独立 QA 与盲测身份**：代码已提供适配与拒绝机制，但实际责任主体和独立输入/运行不能由开发 Agent 自封。
4. **生产目标与发布授权**：已有只读探测和标准出处校验入口；不假设生产地址，不自动发布或部署。

当前不是“全部 ADS 验收完成”。本矩阵避免将安装、代码存在、合成测试和实际集成混为一谈。

## 已验证构建

核心源码提交 `d6971135869204a60e3291c00d9a2a0043f22959` 对应 171 项测试、四条 PR CI、主分支冷安装和标准 Sigstore 出处验证。完整索引见 [core-v0.6.0-validation.json](evidence/core-v0.6.0-validation.json)。wheel/源码 ZIP/patch/统计/哈希保存在运行 41215258915；验证只适用于记录中的准确产物和源码提交，后续文档提交不自动继承同一签名。

## 原生开发执行修复补充

`tests/test_develop_execution.py` 使用真实合成子进程覆盖 CLI 单次执行、摘要持久化、非零退出、超时与预览。修复前执行路径因布尔参数遮蔽函数而 TypeError；修复后调用共用有界执行器。此证据不包含真实模型、OpenCode 原生会话或独立 QA 验收。

## Superpowers 原生复用

官方固定提交通过 OpenCode V2 插件注册，不复制 Skills。`ads init --superpowers` 支持新旧项目增量接入；原生冒烟已验证插件 active、技能注册及三个技能的会话激活。使用 `resume=false`，不能将其计为模型自主技能调用。模型实测仍返回 provider.free-limit。复用官方技能替代自研调试/TDD/完成检查工作流，未新增审批或执行循环。详情与可重跑命令见 [Superpowers 接入](SUPERPOWERS.md)。

## 上游 e2e 接入

固定 e2e 0.22.0、web 0.15.4 实际运行原虚构案例的保存/刷新/DB/下载旅程，并复用 ads verify 消费原生报告；不自研另一套浏览器执行器。首次 CI 41262125347 参考通过、假保存和缺导出列失败；OpenCode 原生 MCP/技能发现与显式激活已本测。模型实际开发仍额度阻断。详见 [运行说明](E2E-JOURNEY.md) 与 [结果索引](evidence/e2e-v0.6.7-first-validation.json)。这是一条已确认范围的真实旅程，不升级为所有 ADS 能力或独立 QA 验收完成。
