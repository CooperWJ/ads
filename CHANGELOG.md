# Changelog

## v0.6.20 — OpenCode CLI 原生模型接入

- 增加本机 OpenCode CLI 的 LanguageModelV4 适配器，复用用户已有 CLI 登录与模型配置；不复制凭证、不另建认证协议。
- 每次模型调用在临时项目中启动 `opencode --standalone --pure run`，避免复用用户共享服务；要求 CLI v2.2.3+。
- 模型调用前执行 `opencode debug config`，检查实际解析配置中的插件/MCP 为空，且工具、MCP、Skill、Plugin 策略最终保持 deny；无法读取或无法证明时阻断。该检查不能覆盖系统管理员策略，也不声称替代真实主机验证。
- 限制 CLI stdout/stderr 各 8 MiB；严格绑定单一 step、单一 assistant 响应、session、Provider/model ID；指定工具调用必须恰好一次。通过 session export 校验 Token 和成本，随后删除 session 与临时目录。
- 增加 fake CLI 回归，覆盖 effective-config 检查路径、全局策略 allow 冲突、工具调用边界、图像附件、身份错配、导出失败、非零退出、session 缺失及清理失败。Fake CLI 通过不代表真实 OpenCode 主机隔离已通过。
- `calibrate.py --agent` 默认使用本机 OpenCode CLI；官方 OpenCode Console OAuth 保留为可选后端。两条路径均无模型/账号自动回退。
- CI 只执行 fake CLI 与配置测试；真实模型执行仍需用户本机可用模型额度，额度错误保持 BLOCKED。

## v0.6.19 — OpenCode Console Agent 验证配置

- 增加独立、显式启用的 e2e Agent profile，直接使用 e2e 0.22.0 官方 OpenCode Console OAuth provider；不自建模型协议、不复制 OpenCode 凭证。
- 新增混合旅程：Agent 仅负责通过 UI 编辑并保存，后续 UI、刷新持久化、数据库和 XLSX 导出由确定性断言及独立 oracle 验证。
- Agent profile 继承 `cache: 'off'`，并限制 steps、model calls 和输入 token；默认 CI profile 仍只运行确定性旅程，不调用模型。
- `calibrate.py --agent` 仅在显式配置模型与完成 OAuth 登录后运行；不自动切换模型或账号。
- 投影 e2e Agent 的安全错误代码，区分凭证/模型不可达等 BLOCKED 与模型输出无效、定位/动作失败等 FAILED；不复制错误原文。
- CI 只验证配置与错误分类，不声称真实模型执行已通过。OpenCode Console 可用模型需以实际模型列表为准。

## v0.6.18 — e2e Agent 行为证据投影

- 从原生 report-1 按用例投影 Agent 操作/判断、确定性断言、动作数、模型调用/token/成本和缓存模式；仅输出低敏计数及安全模型标识，不复制指令、对话、事件详情或屏幕内容。
- 明确区分 Agent 操作与确定性断言同测、缺少确定性断言、缓存重放和真实模型调用；模型用量或成本字段不完整时不补零、不声称完整。
- 修复普通 attempt 中失败 step 或缺失 steps 被外层 passed 状态掩盖的可能性；串行组继续核对成员步骤和清理状态。
- 当前新增的是报告证据投影和确定性夹具，不声称真实 Agent 模型执行或完整自主修复闭环已经验证。

## v0.6.17 — 同快照本地交付就绪核对

- `ads status --gate release` 只读汇总开发义务与 QA 用例执行，要求两条轨道引用完全相同的当前项目快照。
- 本地就绪还要求开发运行绑定真实 OpenCode Session、全部已确认义务通过、QA 必验用例通过；缺少任一证据均阻断。
- 原生开发绑定还要求执行退出码为 0、无错误、输入未漂移、观察到 OpenCode Session、事件流完整且包含最终 stop；失败或不完整运行不能满足开发轨道。
- 运行记录加载时重新核对 Profile 中完整检查集合、进程退出、失败分类、用例结果、报告/日志路径与摘要状态，拒绝不一致的 PASS。
- 拒绝同一 QA 用例重复绑定同一测试；本地就绪不授予独立 QA 身份、语义完备、出处签名或发布授权。

## v0.6.16 — QA 用例与执行证据精确关联

- 每条已确认 QA 用例输出原始 Sheet/行定位、用例内容哈希、原始预期、审查者/决策引用及逐条执行结果。
- 每个唯一测试匹配绑定 QA run、输入快照、check/case ID 和原始报告 SHA-256。
- 缺失或重复测试匹配分别为 MISSING/AMBIGUOUS 并阻断；非 PASS 检查中的 PASS 用例标记 CHECK_FAILED。
- 不提升为独立 QA 身份或 QA_ACCEPTED；本地执行和哈希不替代独立责任主体。

## v0.6.15 — 需求义务与验证结果精确关联

- `ads verify` 决策为每项已确认义务输出预期结果、实际观察状态及精确测试报告引用。
- 每个引用绑定本次验证 run ID、输入快照 SHA-256、检查 ID、用例 ID、报告路径和报告 SHA-256。
- 缺失或重复用例映射分别标记 MISSING/AMBIGUOUS 并阻断；检查失败、断言失败和未运行状态不被折叠为 PASS。
- 保持 OpenSpec 与既有测试设计映射为唯一需求权威，不新增审批状态机；本地哈希引用不冒充签名或独立 QA。


## v0.6.14 — 测试进程结果透明化

- 行为证据按退出码分别统计可识别测试命令的 exit_zero、nonzero、unknown。
- 未知退出码不会计入成功；字段只描述进程结果，不推断测试发现数、断言质量或业务正确性。
- 将退出结果计数同步投影到 `ads verify` 的哈希绑定低敏行为摘要。
- 增加非零、零和未知退出码的确定性回归。

## v0.6.14 — 验证回执展示低敏行为摘要

- `ads verify` 的开发绑定携带哈希校验后的低敏行为摘要：Skill 激活、工具计数、测试/编辑计数、TDD 顺序与最后编辑后验证状态。
- 不复制提示词、命令、源代码、工具输出或原始错误消息；原始事件仍保留在本地私有开发目录。
- 增加验证回执字段及敏感字段不泄露的确定性回归。

## v0.6.13 — 最后编辑后的验证观察

- 从 OpenCode 原生事件顺序观察最后一次直接编辑后是否还有可识别的测试命令及其退出码。
- 区分 OBSERVED、FAILED、NOT_OBSERVED、INDETERMINATE；只有解析无损且观察到最终 stop 事件才给出结论。
- 增加最后测试失败、测试后再次编辑、无测试/编辑和缺少终止事件的回归。
- 该启发式不证明测试意图、需求覆盖或所有间接编辑；OpenCode JSONL 缺少最终 step_finish 时保持 INDETERMINATE。

## v0.6.12 — 开发变更范围事实记录

- 从执行前后 Git 快照计算新增、修改、删除文件路径及计数，覆盖 Git 跟踪及未忽略文件；忽略文件不在覆盖范围内。
- 不复制文件内容；仅覆盖 Git 跟踪及未忽略文件，快照不可读取时标记 UNKNOWN 且计数为 null。
- `ads verify` 的开发绑定携带同一份变更清单，保持开发范围与验证记录关联。
- 增加确定性回归覆盖无变更、单文件修改和新增文件；变更清单只记录事实，不自动裁定需求范围合规。

## v0.6.11 — 原生 Session 续接身份确认

- 显式 `--session` 后核对 OpenCode 原生 JSONL 的 sessionID；匹配才确认续接，其他 ID 或缺失身份分别阻断。
- 摘要区分 CONFIRMED、MISMATCH、NOT_OBSERVED 和 NOT_REQUESTED，避免仅凭参数已传递推断宿主实际续接。
- 增加合成子进程回归，覆盖匹配、错配和无身份事件；不证明远程副作用恰好一次。

## v0.6.10 — OpenCode 原生错误低敏分类

- 从原生 error event 提取格式受限的错误类型、状态码、错误代码与 Provider ID，不复制原始 message 或响应正文。
- 区分模型额度、限流、认证/权限、上游超时、上游故障和未知错误；不自动重试或切换账户/模型。
- 增加 429 配额、403、503 与敏感消息不进入摘要的确定性回归。

## v0.6.9 — 开发与验证证据精确绑定

- 为每次原生开发运行分配唯一 run ID，写入开发摘要/行为摘要哈希及最新运行索引。
- `ads verify` 将开发运行与当前验证输入快照比较，记录 MATCHED、STALE、INVALID 或 NOT_LINKED；QA 运行不继承开发行为声明。
- `ads status` 重新校验被引用的开发摘要和行为文件，篡改或丢失会使旧验证记录失效。
- 新增确定性回归覆盖同版本绑定、开发后代码漂移及行为证据篡改；不将关联关系提升为 TDD 合规或业务正确性证明。

## v0.6.8 — OpenCode 行为证据投影

- 从 OpenCode `run --format json` 原生事件流投影低敏行为事实：工具调用、Superpowers Skill 调用、测试命令与直接编辑工具的可观察顺序。
- 记录可观察的 test-before-edit 与 fail/edit/pass 顺序；只有解析无损且收到最终 stop 事件才给出顺序结论，不把启发式证据认定为 TDD 合规或业务正确性。
- 将行为摘要与单次原生开发运行绑定；原始事件和 stderr 限制为 POSIX 私有权限，摘要不复制提示词、命令、源代码或工具输出。
- 修正原生 OpenCode error event 使用 `error.name` 时被误归类为通用错误的问题。
- 增加确定性事件夹具回归；模型调用与真实 Agent 行为改善仍须在可用模型额度下实测。

## v0.6.7 — 上游 e2e 真实旅程与 OpenCode 薄接入

- 固定 e2e 与 web 引擎版本，用真实浏览器覆盖虚构项目的保存、刷新、SQLite 持久化及下载内容，保留正确参考和故障变体。
- 消费原生 report-1，保留 flaky、skipped、局部重跑遗留、串行组与清理失败；复用原有执行与证据机制，不新增审批流程。
- `ads init --e2e` 注册已安装的官方 MCP 与技能来源，保留用户服务器、权限和 Skill Router；可与官方 Superpowers 插件合用。
- 精简合入 Karpathy 开发原则与成果优先的输出约定，不叠加第二套开发循环或全局风格插件。
- 浏览器、原生连接、模型开发分别记录实际结果；不把配置或参考解校准当成真实模型开发通过。

## v0.6.6 — 原生会话续接与异常收尾

- QA 原始用例可先导入并检查质量，缺少契约时单独报告需求对照 BLOCKED，不伪造审批或验收通过。

- `ads develop --session` 将明确选择的原生 Session 交给 OpenCode，继续复用宿主历史，不新增会话引擎或自动重放。
- 摘要提供单一原生 Session ID，便于下一次明确续接；客户端中断、启动错误和执行后上下文不可读也保留本轮摘要。
- 修复非对象原生错误事件导致报告丢失的问题。中断记录与原生会话参数不代表模型恢复或远程副作用恰好一次已经验证。

## v0.6.5 — 原始需求可直接启动开发

- 初始化提供可编辑 TASK.md，保留用户已有任务；不要求先编写验收契约才能探索需求和调用 OpenCode。
- 开发上下文记录尚未提供的契约、规格和评审文件，并在新增或变化时失效；正式 verify、QA 与交付判断继续核对确认要求。
- 未增加审批或执行器，沿用原生 OpenCode 与 Superpowers。

## v0.6.4 — 官方 Superpowers 原生接入

- 新增 `ads init --superpowers`：用 OpenCode V2 官方插件配置接入固定上游提交；已有项目只增量配置插件，保留 Profile、用户路由、OpenSpec 入口、模型和权限。
- 复用 systematic-debugging、test-driven-development 与 verification-before-completion；已有明确规格不重复需求访谈，不复制技能、不新增执行循环或审批流程。
- 虚构开发切片也使用同一官方插件与原生技能路径；补充真实 OpenCode 的插件注册和无模型技能激活测试，复用现有 CI。
- 模型实际调用仍被 provider.free-limit 阻断；原生注册和显式激活不冒充模型自主使用或完整开发通过。

## v0.6.3 — 按最终交付目标收敛后续工作

- 将三项目标写入 Agent 操作说明：理解正确、开发可靠、独立证据证明满足确认要求。
- 将完整开发切片及同一切片的独立 QA 提至后续工作首位；暂停无关通用门禁和审批扩展。
- 明确成熟开源与宿主原生能力优先，最小集成后仅补实际缺口，删除被替代的重复实现；本次仅调整操作说明和计划，不新增门禁或声称外部集成完成。

## v0.6.2 — 修复原生开发调用执行阻断

- 修复 `develop(..., execute=True)` 布尔参数遮蔽进程函数造成的 TypeError；保留 CLI 与 Python 调用接口。
- 增加真实子进程回归：CLI 单次调用与落盘摘要、非零退出、超时阻断、预览不执行。修复前已复现成功路径失败及异常路径 TypeError。
- 测试使用明确标记的合成原生工具，不调用模型。成功执行仍为 EXECUTED_UNVERIFIED，不升级为开发完成、独立 QA 或发布授权。

## v0.6.1 — 同条件对照输入校验修复

- 双方预算均拒绝布尔值、空值、非正值和非有限值，避免 true 与 1 的隐式相等导致非法配对。
- 种子必须为整数，案例与模型身份不能为空；补充实际拒绝反例和正常配对测试。
- 保存 v0.6.0 的精确 CI、交付包和标准构建出处索引；独立 QA、模型、权限与生产条件仍单独验收。

## v0.6.0 — 可安装项目 CLI、来源差集与独立 QA 适配

- 补齐来源正文与未读附件的独立覆盖计数、QA 缺陷证据回流，以及源码 ZIP / patch / 统计 / SHA256SUMS 构建产物。

- 从已验证并合并的主线增量搭建可复用 ads 包与 console CLI，基准与项目适配分离。
- 来源适配扩展到 PDF 文本层、Docling/Figma 结构化导出；未知页面/附件/格式不默认为空。
- 从已确认 OpenSpec 与既有测试设计映射生成只读契约；独立来源审查投影识别整片遗漏，不新增审批状态机。
- 统一缺陷路由、上下文/多仓失效、单次原生 OpenCode 调用与有界进程清理。
- 运行标准 JUnit/Playwright 测试，绑定本轮原始报告、日志、代码与输入；拒绝提交后漂移、缺失/旧报告和 skipped/flaky 假绿。
- QA 多 Sheet/CSV、隐藏 Sheet、未知列、质量/一致性分离；消费既有决定，DEV 不能代替 QA，PASS+PENDING 阻断，无需手填 Requirement ID。
- 新增真实保护设置读取、标准构建 attestation 校验、部署身份只读探测与三轴配对结果适配。保留 QA 独立身份、模型额度、保护权限和生产授权外部边界。
- 引入 wheel 构建、冷安装与主分支标准 provenance 工作流；不发布 PyPI 或生产系统。

## v0.5.9 — 开发切片输入与外部容器旅程验收

- 新增独立虚构开发工作区，只有原始资料、未完成代码和开发协议，不交付评分器或参考补丁。
- 导出以最初 Git 基线覆盖已提交与未提交变更，拒绝来源篡改、符号链接和交付白名单越界；补丁存在不证明 OpenCode 执行。
- 复用原评分器，增加可注入服务工厂与受限 Docker 服务适配；真实浏览器、API 和 SQLite 检查在候选容器外执行。
- 容器只挂载一个一次性数据库文件，使用只读根目录、内部网络、能力移除与资源限制；实际拓扑由 Docker inspect 核对。
- 实测 OpenCode 2.2.3 正确包为 @opencode/cli；Harbor 内置适配仍使用 opencode-ai，记录版本不匹配，不伪装兼容。
- 匿名模型真实调用返回 provider.free-limit/429，未生成候选代码，完整开发切片维持 BLOCKED；外部验收入口由 CI 单独校准。

## v0.5.8 — Harbor 独立导出验收最小集成

- 依赖恢复证据修复候选，新增 Harbor 0.25.0 原生任务生成适配器与 Docker CI，自身不实现任务调度。
- 候选容器运行现有虚构 HTTP 服务并生成 XLSX；独立 verifier 只解析数据，不执行候选程序，复用现有冻结字段与值契约。
- 参考导出、缺列导出、候选篡改评分脚本/奖励文件三类校准，缺结果、基础设施错误、共享 verifier 和旧运行绑定均不放行。
- 基础镜像先解析 digest；记录任务文件指纹、运行 ID、原生 trial 结果、阶段时间及依赖清单。
- 本地全量 122 项测试通过；GitHub Docker 运行 41208957430 三例校准通过，同提交 M0/M1 浏览器 CI 成功。此能力不证明完整交付、OpenCode 开发切片或发布级受保护评分。

## v0.5.7 — 恢复证据判定纠偏与产品闭环优先级

- 修复恢复审计通过命令子串误认 echo、其他脚本和错误实验目录的问题；仅认可直接 Python 调用与同一实验的结构化回执。
- 比较历史消息完整内容并拒绝重复/缺失 ID；恢复阶段只接受一次匹配的 verify shell 调用。
- 增加已跟踪未提交差异与探针脚本指纹，拒绝实验文件符号链接和损坏尝试记录。
- 审计 schema 升级为 v2，显式标注本地导出一致性边界；旧 v1 PASS 不自动升级，真实 OpenCode v2 审计待重新实测。
- 统一 README、AGENTS 和状态文档，区分历史已观察现象、当前验收状态和未完成集成。
- 暂缓通用崩溃执行器；下一步先验证最小隔离边界，再完成原始需求到独立验收的 OpenCode 开发切片。

## v0.5.6 — OpenCode Session 客户端恢复与重复副作用 PoC

- 从主分支最新架构文档基线增量开发，补齐下一阶段任务全貌、实测范围与依赖。
- 新增 `poc/recovery_poc.py`：在系统临时目录建立虚构实验，记录唯一副作用尝试、Git HEAD + AGENTS 基线指纹；重复执行与基线漂移不能通过。
- 新增两个 OpenCode 原生命令 `/ads-recovery-phase1`、`/ads-recovery-phase2`，分两次进入同一个 Session 运行，禁止恢复后重新执行 apply。
- 新增父 Session 两时点导出审计：验证相同 Session/项目 ID、消息延续、真实工具执行、恢复阶段不重复 apply、临时副作用只执行一次；仅输出低敏摘要。
- 新增 10 项合成正反例及 1 项真实跨 Python 进程持久化/重复执行反例；文档明确客户端重启实验 **不等于**执行中途崩溃恢复，后者仍为 NOT_VERIFIED。
- 修补 CI 触发范围：PR 上的 OpenCode 原生命令、PoC、文档、版本变更须重新跑测试；这仍属于自测，不等于分支保护或独立评分。
- 修复 VERSION 与 CHANGELOG 不一致，以及旧手册残留的 OpenCode `agent list` 和 Chromium 未测描述；未新增第二套 Agent Loop、真实业务数据或外部凭据。


## v0.5.5 — OpenCode Session 严格证据门禁

- 记录用户提供的 v2.2.3 Build → Explore 本机实测摘要：独立委派及子会话只读工具事件 PASS，工作区全程只读和整体可靠性交付 NOT_VERIFIED。
- 修复诊断脚本可能被 CI 误用的退出码歧义：新增 `--gate invocation|child|overall`，要求证据缺失时退出 3、明确失败时退出 1，输入无效退出 2；默认 report 维持诊断兼容。
- 补充 5 项关于报告与严格门禁区分、失败目标、缺失证据和 CLI 退出码的测试。
- 仅发布脱敏摘要，不提交原始 Session 或含凭据的证据文件；提醒撤销此前检测到的疑似 GitHub Token。


## v0.5.4 — OpenCode 父子会话关联与凭据风险提示

- 检查器支持只读加载独立的子会话 JSON，通过父 `subagent` 工具元数据和子 `info.id` 精确关联。
- 子会话执行 PASS 还要求 Agent 为 Explore、存在已完成的只读工具事件；错误 ID、错误 Agent、错误父级引用按 FAIL 处理。
- 检出会话中疑似 GitHub Token 仅输出布尔风险与撤销提示，不输出凭据值；不收集、提交任何原始会话数据。
- 新增独立子会话、脱敏输入和凭据泄露反例；不将未验证的工作区只读声明包装为整体 PASS。


## v0.5.3 — OpenCode V2 会话证据检查器

- 增加只读、标准库实现的 `poc/check_opencode_session.py`，分析父 Session 中的结构化工具记录，不读取或输出提示词和工具结果。
- 严格区分真实 `subagent` 调用、目标 Agent、关联子会话及工作区只读证明；参数脱敏或仅有 Build 文本时维持 NOT_VERIFIED。
- 增加 7 项专项反例测试，覆盖 shell 误判、脱敏、错误目标、失败状态、父角色及子会话关联。
- 保留 `v0.5.2` 原生命令和独立版本记录；本版本不宣称已经拿到可复核的真实子代理执行证据。


## v0.5.2 — OpenCode V2 原生 Subagent 实测入口

- 基于本机 v2.2.3 `debug agents` 真实输出，确认 Build/Plan 为 Primary、Explore/General 为 Subagent；隐藏维护 Agent 不作为任务执行目标。
- 新增原生命令 `/ads-subagent-smoke`：只读 Build → Explore 委派，不增加自定义 Agent，也不修改 OpenSpec 既有工作流。
- 新增中文实测指南：说明真实子代理调用、子会话证据、脱敏导出与严格判定方法；没有运行证据时标为 NOT_VERIFIED。
- 同步 README 中 Chromium CI 实测已通过的现状；本版本未声称本机 OpenCode、Harbor 或受保护 CI 已验证。


## v0.5.1 — Chromium Runner 与 M0/M1 浏览器校准修复

- 将 `.github/workflows/m0-selftest.yml` 的 Runner 固定为 `ubuntu-24.04`，避免 `ubuntu-latest` 升级到当前 Playwright 不兼容的系统版本。
- 修复真实浏览器对只读 `<dd>` 错用 `is_editable()` 的断言；仍检查不可编辑语义，保存后等待导出按钮真正可用。
- 修复 M1 参考实现 `/board` 返回错误 Content-Type 导致真实浏览器无法加载；增强 HTTP 菜单检查并新增回归测试。
- M0/M1 不论彼此成功或失败都单独运行严格校准；失败时保留详细评分与 Trace 供复核。
- 保留原有 M0/M1 严格浏览器校准和验收要求，不修改评分或放行条件。
- GitHub Actions 实际执行结果以本版本修复分支的 CI 日志为准；不得把修复提交当作浏览器验收通过。

## v0.5.0 — M1 来源缺口到可执行验收闭环

- 新增评测方持有的独立 M1 验收契约，不覆盖 M0 冻结审查与 18 项基准。
- 增加菜单 `/board` 与真实 404 错误状态的功能切片，以及两个故障变异。
- 独立评分器增加 HTTP 菜单、可访问错误提示、Node/HTTP 故障路径与完整 Chromium 旅程检查。
- 新义务精确绑定原始来源，缺少浏览器时仍为 NOT_VERIFIED；加入 M1 独立校准及严格 CI 入口。
- 新增专项测试，旧 M0 默认行为保持不变。

## v0.4.0 — M1 多来源原始需求发现与独立验收缺口

- 新增 discovery 模块：独立枚举 UTF-8 PRD、SVG 可见文本、XLSX 多 Sheet 及公式文本，未知媒介/破损源 fail-closed。
- 增加虚构三 Sheet 字段与动作表和原始 PRD，独立审阅基准核对 4 个来源、44 个片段。
- 将原始资料清点、提取、独立审阅、验收缺口分开报告；发现旧 M0 基准没有覆盖的菜单入口和请求失败提示两项交付义务。
- 扩展 grade.json，保留原 M0 Profile 结果但拒绝将新发现的交付义务视为已验证。
- 增加 M1 正反例，包括整个 PRD 行遗漏、未登记来源、Excel 文件缺失、错误排除、指纹漂移、公式仅作为原始证据。
- 仍不声称浏览器、Harbor、OpenCode、容器和受保护 CI 已集成。

## v0.3.0 — 原始来源覆盖与交付判定分离

- 新增评测方持有的 `evaluator/raw_obligations.json`，对虚构原始线框图 13 个文本节点逐项清点，并为原始需求中的非视觉规则提供原文锚点；不让 Agent 自行增删验收范围。
- 新增 `evaluator/requirements.py`，独立检查来源枚举、义务 ID、来源引用与验证项映射，漏登记完整 SVG 项也直接拒绝。
- 评分报告将原有 profile PASS 与 `delivery_verdict` 分离；缺浏览器或 Node 证据会判为 `NOT_VERIFIED`。`--require-delivery` 为 CLI 严格模式。
- 强化只读字段（非 editable 结构/真实 Chromium 可编辑性）及页面必要文本的检查；新增负例测试覆盖漏登记、断言引用缺失、未运行浏览器、坏变异。
- 不将本地文件白名单/干净临时目录包装为可信容器；OpenCode、Harbor 和浏览器受阻继续明确报告。


## v0.2.0 — M0 评测基准可信度增强

- 新增 `integration` 评测档：Node.js 虚拟 DOM 执行实际候选 JS，通过真实 HTTP 验证字段、保存、导出 URL、刷新读回。它不是浏览器，也不是安全沙箱。
- 增加 `ui_crash` 的 Node 负例校准；校准案例从 10 项扩为 14 项（后端 + Node 集成）。
- 为 `calibrate.py` 增加 `--require-browser`，真实 Playwright 参考解与坏变异不满足要求时严格失败；报告单独显示 browser_calibration。
- 加固 Git patch 白名单：交叉检查 diff header、---/+++、`git apply --numstat`，拒绝二进制、重命名、模式变化，核对实际文件差异/符号链接。
- 自定义补丁在本机执行需显式 `--allow-untrusted-local-candidate`；仍不构成沙箱，不建议未经隔离运行不可信代码。
- 新增 GitHub Actions 浏览器校准自测模板（不宣称可信外部评分服务）；扩充定向正反例测试与信任模型文档。
- 保留 v0.1.0 全部代码和现有后端验证，未修改任何业务仓库或旧 ai-dev-template。

## v0.1.0 — M0 首批可运行基准

- 虚构原始需求、线框图、HTTP/SQLite/XLSX 参考项目与独立评分器。
- 正确/错误变体、合成 QA 必验状态、源码证据校准、浏览器脚本和工具探针。
