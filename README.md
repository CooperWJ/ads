# ADS 工程验证基准与原始需求发现 PoC

这是面向完全虚构项目的 **AI 软件工程评测基准**，不是实际业务代码，也不是新开发完成的全部 ADS 平台。根据 ADS-ARCH-003 的 M0a/M0b 计划构建，旧 ai-dev-template 保持独立。

## M1 独立验收闭环

- 可选择 `--acceptance-bundle m1`：在旧 18 项冻结义务之外，单独验证来自虚构 PRD 的菜单入口和 HTTP 失败提示。
- `reference_m1` 是新增功能切片的参考实现；`m1_missing_menu`、`m1_silent_error` 是刻意注入的缺陷。Node 真实 HTTP 检查与真实 Chromium E2E 严格分开。
- `python3 evaluator/calibrate_m1.py` 校准 M1 的 Node/HTTP 正反例；`python3 evaluator/calibrate_m1.py --require-browser` 缺少真实浏览器校准必须失败。
- 完整说明参见 [M1 验收闭环](docs/M1-ACCEPTANCE-CLOSURE.md)。当前没有受保护 CI，不能将本地校准升级为可信外部交付证明。

## 新增 M1 多来源发现能力

- 对受控的虚构 PRD、SVG 和多 Sheet XLSX 进行**独立来源枚举**，并使用评测方持有的固定审核样本核对每个来源片段。详见 [M1 设计与边界](docs/M1-SOURCE-DISCOVERY.md)。
- `python3 -m discovery.cli --inventory-only` 只负责枚举；`python3 -m discovery.cli` 发现与原先 18 项验收不一致的新增要求时**退出码为 2（GAP）**。
- 参考案例实际发现菜单入口和失败提示两项新要求，但尚无相应独立验收，故**不能称为完整交付**。公式只提取不计算、不自动成为业务 Oracle。
- 多来源片段发现不代表自动理解任何 PDF/Figma/录屏，也不取代对真正业务争议的人工确认。评测方 review 仅为虚构校准样本，不是真实人类审批证据。

## 原始需求完整性审计与两种 PASS（当前行为）

- 评测方私有的 `evaluator/raw_obligations.json` 基于本例**虚构原始资料**编制，检查 `wireframe.svg` 全部 13 项文本和 `brief.md` 六句需求是否映射到 18 项交付义务。漏掉整项按钮、字段或非 UI 业务规则，检查应拒绝；这只是格式已知案例的来源枚举，**不是通用的 PRD 语义提取或独立确认**。
- `evaluator/requirements.py` 在运行候选前检查来源枚举与义务完整性；运行后将每项义务与专业测试、独立 QA 和当前源码证据关联。
- `grade.json.status` 表示**本次选择的 Profile 检查**；`grade.json.delivery_verdict.status` 才表示**18 项义务的全层级验收**。Backend/Node 通过但浏览器未执行时，`delivery_verdict=NOT_VERIFIED`，不可宣传交付完毕。
- `python3 evaluator/grade.py --candidate reference --profile backend --require-delivery --out /tmp/ads-grade` 会以状态码 2 拒绝将后台 PASS 认定为完整交付。正式交付必须使用 `--profile full --require-delivery` 并在获准的 Chromium 环境中执行。
- 此版本评分器和隐藏 rubric 必须部署在与开发 Agent 不同权限的受保护执行方；本地打包里提供 rubric 供审查，**不等于已有真正的隐藏测试服务**。

## 已实现的验证层级

| 层级 | 命令 Profile | 验证范围 | 能否代替真实浏览器 |
|---|---|---|---|
| Backend | `backend` | HTTP、七项数据字段、HTML 源结构、SQLite、XLSX、QA 合成状态、证据摘要 | 否 |
| Node integration | `integration` | 上述项目 + 真实候选 JS、有限 DOM 模拟、真实 HTTP / 保存 / 刷新 | 否 |
| Real browser | `full` | 上述项目 + Playwright 浏览器用户旅程、真实下载、Trace | 是（适用于本参考案例） |

Node 集成不是安全沙箱。虚构参考案例评分依赖独立受保护的期望值；这些期望不能放给受测 Agent。当前软件包为可检查的开发/评测工具集，不具备生产信任身份隔离。

## 本地复现

要求 Python 3.10+ 与 Git；`integration` 额外需要 Node.js 20+。`full` 额外需要 Playwright + 获准的浏览器运行环境。

```bash
python3 -m unittest discover -s tests -p 'test*.py' -v
python3 evaluator/calibrate.py                         # 14 项后端 + Node 校准；浏览器另列 NOT_VERIFIED
python3 evaluator/grade.py --candidate reference --profile integration --out artifacts/reference-integration
python3 evaluator/grade.py --candidate ui_crash --profile integration --out artifacts/js-error-integration
python3 evaluator/grade.py --candidate reference --profile backend --require-delivery --out artifacts/strict-local  # 非零退出属预期
python3 poc/probe.py
```

在**允许浏览器访问本地受测服务**的独立 Runner 中运行严格校准：

```bash
python3 -m pip install 'playwright==1.57.0'
python3 -m playwright install chromium
python3 evaluator/calibrate.py --require-browser
```

该命令要求真实 Chromium 参考解 PASS 且 UI 运行异常 FAIL。如果浏览器缺失、阻断或执行失败，严格校准应非零退出。参见 `.github/workflows/m0-selftest.yml`（**自测模板，不等于受保护外部评分服务**）。

不要在开发 Agent 可改写、可读取隐藏测试及评分器的同一权限环境中声称结果具有独立可信性；正式评测需将评测器及预期与候选代码隔离。**不可信自定义补丁必须使用真正的 OS/容器安全隔离**；CLI 的本地确认开关不提供隔离。

## 文件职责

- `fixtures/project_board/raw/`：虚构原始资料，与需求实现分离。
- `fixtures/project_board/base/`：刻意未完成的初始版本。
- `fixtures/project_board/patches/`：参考解、等价解、错误变异（仅供可信评测方访问）。
- `evaluator/grade.py`：运行服务与评分，明确区分所选 Profile 与完整交付判定。
- `evaluator/raw_obligations.json`、`evaluator/requirements.py`：评测方的原始资料清点、18 项交付义务和独立判定。
- `evaluator/js_runtime_check.cjs`：轻量 JS/DOM/HTTP 辅助检查。
- `evaluator/calibrate.py`：校准案例，支持严格浏览器判定。
- `tests/`：评测器反例和进程测试。
- `poc/probe.py`：外部依赖可用性，只读检测。
- `docs/TRUST-MODEL.md`：威胁模型、CI 信任边界与下一步。

## 当前边界

- 本机真实浏览器全链路尚未通过，工具/管理策略限制是 `BLOCKED`，不是 PASS。
- Harbor Worker、OpenCode Session/Subagent、Playwright Test Agents、真正受保护 CI 仍未进行本机真实集成验收。
- `check_evidence()` 是合成错误输入校准，不是第三方签名/attestation；`check_qa()` 是合成 QA 状态，不是独立 QA Excel 接入。
- 完整 ADS 的需求理解、AI 开发可靠性、真实交付可信性功能尚需 M1～M5 实施。

历史版本变化详见 CHANGELOG；测试结果详见 REPORT。
