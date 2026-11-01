# ADS：AI 开发与交付证据适配系统

ADS 面向多项目复用，连接原始需求、OpenCode 开发、专业测试器、独立 QA 和构建出处。它提供薄 CLI 与确定性核对，不替代 OpenSpec、Agent Loop 或测试执行引擎。

项目包含两部分：可安装的 `ads` CLI，以及完全虚构的工程校准基准。基准通过不能代表 ADS 在真实项目中已证明收益。

## 当前可用能力

| 入口 | 职责 |
|---|---|
| `ads init` | 生成项目 Profile 和 OpenCode 原生薄入口，保留已有路由和 OpenSpec 命令 |
| `ads discover` | 清点来源、页/Sheet/节点及无法读取区域 |
| `ads compile` | 从 OpenSpec 基线与既有测试设计映射生成只读义务视图 |
| `ads reconcile` | 核对独立来源决策与交付义务，识别遗漏、冲突及未知 |
| `ads route` / `ads context` | 缺陷优先路由与多仓/来源/知识指纹失效 |
| `ads develop` | 单次调用 OpenCode 原生 CLI，记录执行事实、可观察的 Skill/TDD 行为和阻断；行为证据边界见 [说明](docs/BEHAVIOR-EVIDENCE.md) |
| `ads verify` / `ads status` | 运行项目测试器，消费 JUnit/Playwright 报告、核对必验集合，并绑定对应开发运行及行为证据 |
| `ads qa` | 多 Sheet/CSV 质量检查、候选关联、既有 QA 决策与独立执行结果核对 |
| `ads gate` / `ads attest` / `ads smoke` | 实际分支保护读取、标准出处校验、部署端点身份核对 |
| `ads benchmark` / `ads doctor` | 三轴配对结果与成本比较、真实依赖可用性探测 |

## 安装

真实浏览器旅程可复用上游 e2e；使用 `ads init --superpowers --e2e` 配置原生入口。固定依赖、项目检查与可运行校准见 [e2e 接入说明](docs/E2E-JOURNEY.md)。模型额度不足时仍可运行确定性旅程；模型执行与独立验收分别报告。

```bash
python3 -m venv /tmp/ads-env
/tmp/ads-env/bin/pip install '.[sheets,pdf]'
/tmp/ads-env/bin/ads --help
```

项目接入、命令、数据格式与退出码见 [CLI 使用指南](docs/CLI-GUIDE.md)。业务来源、领域 Oracle 和项目配置由项目自身维护；ADS 核心不包含真实业务公式、数据、环境凭据或生产发布权限。

## 已验证范围

- 真实 HTTP/SQLite/XLSX/Node/Chromium 的参考与故障变体校准。
- Harbor 独立 verifier 的导出产物隔离，以及候选篡改评分文件的拒绝。
- 候选 Docker 服务与容器外浏览器/API/数据库检查；候选不获得评分器或 Docker socket。
- 通用 CLI 的真实测试进程、标准报告、代码/来源漂移、QA 必验集合，以及 Python 与 Node 的多仓接入。
- PDF 文本层与结构化导出只读适配；未读取图像、附件和不支持格式保持 UNKNOWN。

详细命题与证据见 [能力矩阵](docs/IMPLEMENTATION-MATRIX.md) 和 [当前状态](docs/PROJECT-STATUS.md)。GitHub 自测不是受保护外部评分。QA 适配测试不是独立 QA 责任人的正式验收。

## 当前外部限制

OpenCode 原生模型调用已实际执行，但匿名模型额度被拒绝，因此完整 AI 开发切片尚未验证。Playwright 三个 Agent 配置已被原生 CLI 识别，实际 MCP/模型生成和修复仍未验证。分支保护、独立 QA 身份、生产部署与新鲜盲测效果需要相应外部权限和运行条件。

本机执行、来源语义确认、QA 独立性、构建出处与发布授权分别报告。`DEV_VERIFIED_LOCAL` 不升级为发布授权，有限材料也不能证明绝对需求完备。

## 开发与校准

```bash
python3 -m unittest discover -s tests -p 'test*.py' -v
python3 evaluator/calibrate.py
python3 evaluator/calibrate_m1.py --require-browser
python3 -m ads --help
```

本地临时目录不是安全沙箱。自定义候选应通过 [外部容器旅程入口](docs/POC-OPENCODE-DEVELOPMENT-SLICE.md) 执行。`evaluator/grade.py` 的旧本机模式仅用于可信校准；其 QA 和证据输入是合成样本。

历史变更见 [CHANGELOG](CHANGELOG.md)。
