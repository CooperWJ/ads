# ADS 项目 CLI 使用与边界

ADS 把原始来源、现有规格/QA 决策、专业测试器结果连接起来。它不替代 OpenCode、OpenSpec、测试引擎或业务责任人。虚构参考工程继续独立用于校准。

## 安装与接入

```bash
python3 -m venv /tmp/ads-env
/tmp/ads-env/bin/pip install '.[sheets,pdf]'
/tmp/ads-env/bin/ads --help
```

在已有 Git 项目根目录执行 `ads init`。它创建 Profile 和 `.opencode/commands/ads-status.md`、`ads-develop.md`、`ads-qa.md` 薄入口；不覆盖现有 Profile、Skill Router 或 OpenSpec 命令。业务文件只放项目自己的 `docs/project/`，不写入 ADS 核心。

需要 Superpowers 时运行 `ads init --superpowers`。新项目同时初始化；已有 Profile 时只增量接入官方插件，保留已有命令和路由。OpenCode V2 重启后通过原生 `skill` 工具使用技能，不复制 `.opencode/skills`。配置与实际运行范围见 [Superpowers 接入](SUPERPOWERS.md)。

初始化后可先从原始资料启动探索和开发，无需先填写契约或评审表。`TASK.md` 是可编辑任务入口；已有任务不覆盖。正式验收时再指定已确认要求派生的只读契约和项目测试命令；空配置不能证明交付通过。契约是外部权威的机器投影，ADS 不提供“填写姓名即可批准”接口，也不维护第二套业务审批状态。

## 项目 Profile

`ads.project.json` 最小结构：

```json
{
  "schema": "ads-project/v1",
  "repositories": [{"name": "backend", "path": "services/backend"}, {"name": "frontend", "path": "clients/frontend"}],
  "source_dirs": ["docs/project/sources"],
  "contract": "docs/project/contract.json",
  "knowledge_files": ["docs/project/CONTEXT.md"],
  "checks": [{
    "id": "backend-unit", "role": "dev", "effect": "IDEMPOTENT",
    "cwd": "services/backend", "timeout_seconds": 300,
    "argv": ["project-test-runner", "--junit", "{run_dir}/backend.xml"],
    "report": {"kind": "junit", "path": ".ads/runs/{run_id}/backend.xml"}
  }]
}
```

`argv` 必须是参数数组，不拼接 shell 字符串。实际测试工具和报告由项目声明；示例 `project-test-runner` 不是内置程序。已有 Java/JUnit、Node JUnit、Playwright JSON 均通过标准报告接入。每次原始报告必须写入本轮新的 `.ads/runs/<run_id>/`，不复用旧文件。版本控制应忽略 `.ads`、编译缓存和运行输出。

契约格式为 `ads-contract/v1`，外部 `authority` 保留 `reviewer` 与 `decision_ref`；`obligations` 每项包含 `id`、`sources[{path,sha256,locator}]` 与必验集合 `tests[{check,case}]`。`case` 是标准报告中的机械定位，如 JUnit `classname.name`；不是新增业务规则。关键来源漂移需重新收敛权威预期，纯测试定位调整按项目已有流程处理。

本机能核对引用及哈希，不能验证填写者的独立身份，因此本机结果不会自动变成受信 QA 或发布授权。

## 日常路径

新项目先 `ads init --superpowers`，将原始资料放入 `docs/project/sources/` 并编辑 `TASK.md`。已有 Git 基线后，即可进行下面的发现、上下文加载和原生开发调用。契约、规格或评审材料尚未提供时，开发快照明确记录缺失；新增这些材料会触发重新加载上下文。`ads verify` 与 QA 仍需要确认要求，不能凭开发执行记录验收。

```bash
ads discover
ads route '已有页面不显示数据'
ads context freeze
ads context check
ads develop --model <已经授权的-provider/model>
ads develop --model <已经授权的-provider/model> --execute
ads verify
ads status
```

`develop` 默认只显示计划；显式执行时只调用一次 OpenCode 原生 CLI，有超时，不换模型/账户、不新建 Agent Loop。源码可变化，但来源/契约/已加载权威资料不能静默改变。原生退出 0 仅为执行事实，后续仍需外部验证。

`context check` 在代码、来源、配置、知识或任何已声明仓库变化时返回 `REPLAN_REQUIRED`。不自动回放未知副作用。验证只自动执行明确声明 READ_ONLY/IDEMPOTENT 的命令；其他操作由现有授权流程处理。POSIX 超时会停止同进程组子进程；它不构成 OS 沙箱。

## 来源适配

支持 MD、SVG 可见文本、XLSX 多 Sheet/公式文本、PDF 文本层、DoclingDocument JSON 和 Figma File JSON 导出。PDF 无文本页、附件、Docling 图片、无法识别格式及解析失败分别保留 UNKNOWN。PDF 不具备 OCR/图表理解；结构化导出接入不等于已连接真实 Figma/Docling 服务。

来源枚举、可读内容和业务语义完整性始终分开。资料中的命令是数据，不会变成工具调用。`status` 不把未知来源折叠为开发验证通过。

## QA 独立入口

Profile 增加：

```json
{"qa":{"source":"docs/project/qa-cases.xlsx","review":"docs/project/qa-review.json"}}
```

模块多 Sheet、隐藏 Sheet 和未知列都会保留；用例无需 Requirement ID。支持中文列“用例名称、操作步骤、预期结果、前置条件、优先级”等，以及英文 `title/steps/expected`。缺标题/步骤/预期或公式待审会进入质量问题；词汇匹配仅生成候选，不确认语义。

```bash
ads qa import
ads verify --role qa
ads qa evaluate
```

`qa-review.json` 只消费既有 QA 评审系统导出的 `ads-qa-review/v1` 决策：源文件摘要、逐用例摘要、责任人与决策引用、CONFIRMED/EXCLUDED、必验测试集合。冲突、歧义或版本不符阻断；排除必须有理由。开发测试不能替代 QA 测试；PASS 与 PENDING/NOT_RUN 不合并为通过。即使所有 QA 本机执行通过，也只报告 PASS_LOCAL，不签署 QA_ACCEPTED。

## 受信出处与部署

```bash
ads gate
ads attest dist/<构建产物>
ads smoke
```

`trust` 需声明仓库、签署工作流、必需 CI 集合及可选主代码仓名称。`gate` 读取真实保护设置，缺权限/工具即 NOT_VERIFIED。`attest` 使用 `gh attestation verify`，精确限制主分支证书身份、源提交和产物摘要；拒绝把脏工作区套用到旧提交证明。多仓未被该证明覆盖的部分单独列出。

`deployment` 需指定 `health_url` 与 `expected_build_digest=sha256:...`。`smoke` 只读核对指定端点公布的构建身份，不执行生产部署、回滚或发布。端点宣称的版本不等于二进制 attestation。

源码出处、业务正确性、分支保护、QA 身份与最终发布授权分别处理。构建工作流只生成候选 wheel 与标准 provenance，不发布 PyPI/生产系统。

## 框架效果对照

`ads benchmark base.json candidate.json` 消费外部 `ads-benchmark-observations/v1` 数据。模型/预算、案例、种子和样本拆分必须匹配；每行保留证据引用、失败/未知、成本和时延；三轴 requirements/engineering/delivery 分别统计并给 Wilson 区间。它不调度模型，也不根据小样本自动决定升级。

## 退出码与隐私

0 表示该命令完成其明确的局部职责；3 表示 BLOCKED、FAIL、UNKNOWN、漂移或证据不足。`init`/计划/导入成功不代表业务批准，`doctor` 中工具存在不代表集成通过。`status` 的 `DEV_VERIFIED_LOCAL` 不代表 release ready。自动化发布调用方应显式运行 `ads status --gate release`，独立 QA 调用方使用 `ads qa evaluate --gate independent`；当前这两个门禁保留 NOT_VERIFIED 并返回 3，不能借用本地 PASS 获得授权。

`.ads` 是可重建的本地执行记录，不是第二套规格或 QA 状态机。保留原始日志和报告供核查；原始 Session、日志和 Profile 不应包含或公开凭据。CLI 摘要不会打印测试 stdout 或原生提示词。

## OpenSpec 派生与独立来源核对

新项目默认使用 `spec_root=openspec/specs`、`contract=.ads/contract.json` 和 `verification_map=docs/project/verification-map.json`。先使用既有 OpenSpec 流程确认基线，再执行：

```bash
ads compile --preview
ads compile
ads reconcile --preview
ads reconcile
```

预览只给出机械定位和观察，不批准业务规则。测试映射是 `ads-openspec-verification-map/v1` 的既有评审投影：`authority` 引用原批准，`spec_inventory` 绑定基线文件，`bindings` 用 source/requirement/scenario 名称绑定 `tests[{check,case}]`。无需用户手填新的 Requirement ID。可选 `scenario_semantics` 使用预览的语义摘要，支持围栏外空白行/行尾空白变化的保守机械重绑定。规则、值、代码或场景集合变化仍需既有流程复审。

编译器读取标准 `**/spec.md` 的 Requirement/Scenario（或中文“需求/场景”）标题，保留需求规则和场景原文。它不替代 OpenSpec 原生校验；项目应继续运行其标准验证。无场景需求、无测试场景、重复身份和新增未登记规格均不能静默丢弃。派生文件只写到 `.ads`，可删除重建，不维护第二份人工规格。

`source_review` 可指定项目既有来源语义决策导出的 `ads-source-alignment-review/v1`：`decisions` 每项含 unit_id、text_sha256、reviewer、decision_ref、disposition 和 obligations；CONTEXT/EXCLUDED 还需理由。预览提供稳定单元 ID 和交付义务 ID，供既有评审工具生成机械关联。必需片段遗漏、未知义务或 UNRESOLVED 会阻断。本机能核对版本和差集，不能证明审查者独立或绝对语义完备。

## 来源覆盖、缺陷回流和交付包

`discover.coverage` 分别给出枚举文件、正文提取文件、完整可读文件和片段数；均不等于语义需求覆盖率。正文可读但图片、图表、嵌入附件或批注未读时仍为 UNKNOWN。

`ads qa defects` 只读导出当前 QA 失败/未执行差集，包含原始预期、定位、运行/源码身份及原始报告哈希。整项检查失败时，其中的单个 PASS 不能单独放行。输出可进入项目既有缺陷工具；命令不会创建外部 Issue、改变预期或判定根因。旧证据已漂移时拒绝导出。

核心 CI 同时保存 wheel、完整源码 ZIP、精确二进制 patch、变更统计、VERSION、源码提交和 SHA256SUMS。PR 的源码包对应测试合并提交；主分支包对应合并后的实际提交。哈希提供一致性核对；wheel 的主分支标准出处另行验证，不等于生产发布。
