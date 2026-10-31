# ADS M1 v0.5.0 实施及测试报告

日期：2026-10-31。基线：独立 `ADS v0.4.0` 源码；未改动旧 ai-dev-template，未覆盖既有版本。

## 实际新增

- 从受评测方保护的 M1 原始来源审查中提取新增两个需求：`menu-route-accessible`（菜单进入页面）、`page-error-state`（项目请求失败显示明确错误状态）。
- 增加独立的 `evaluator/m1_acceptance.json`，精确约束来源、义务 ID、验证方式；必须由 CLI `--acceptance-bundle m1` 显式选择，不改写原有 M0 18 项验收范围和审核材料。
- 新增可重建补丁：`reference_m1` 实现菜单 `/board`、可访问的 `role=alert` 与真实 404 显示；`m1_missing_menu`、`m1_silent_error` 为人为故障注入，均由冻结基线重新构建。
- HTTP 菜单检查不只看文本，还会请求真实 `/board`；错误检查要求明确的独立告警及真实 HTTP 404。Node 只采用受限 DOM 模拟，并不等于浏览器。
- 增加 Playwright `full` 验收的菜单导航及实际 404 交互。没有可运行 Chromium 时保持阻断。
- `delivery_verdict` 汇总 M0 18 项与 M1 2 项，缺少真实 Chromium 证据即为 `NOT_VERIFIED`；`--require-delivery` 必须非零退出。原来源比对的 GAP 仍保留为历史差异，新增 `source_discovery.acceptance_closure` 报告 M1 的独立验收进度。
- CI 自测模板新增 M1 严格浏览器正反例校准。**模板存在不意味着已有受保护的 CI。**

## 本轮实测

| 项目 | 实际结果 | 结论 |
|---|---|---|
| 旧测试 + 新增专项 | **75/75 PASS** | 自动化测试范围通过 |
| 从发布 ZIP 重新解压复验 | **75/75 PASS** | ZIP 解压后执行结果一致 |
| M0 旧后端/Node 校准 | **14/14 符合预期** | 不改变既有校准行为 |
| M1 Node/HTTP 校准 | **5/5 符合预期** | 参考实现 PASS、四类空解/旧解/故障解 FAIL |
| M1 真实浏览器校准 | 参考实现 `BLOCKED`，两个错误变异 `FAIL` | **NOT_VERIFIED**，不计入全链路通过 |
| M1 严格浏览器校准 | 退出码 1 | 按设计 fail-closed |
| 正确 M1 参考实现的 integration Profile | `PASS` | 只代表所选 Node/HTTP Profile |
| 同一实现的完整交付 | `NOT_VERIFIED` | 缺少完整浏览器执行证据 |

证据文件：`artifacts/unittest-v050.txt`、`artifacts/calibrate-v050-m0-stdout.json`、`artifacts/calibrate-v050-m1-stdout.json`、`artifacts/calibrate-v050-m1-strict-stdout.json`、`artifacts/calibration-summary.json`、`artifacts/m1-calibration-summary.json`（普通模式最终状态）。

## 尚未完成，不得宣称 PASS

1. **真实 Chromium**：受当前运行环境浏览器访问/安装限制，无法验证 M1 真实浏览器正例。严格校准会失败，不能用 Node Fake DOM 代替。
2. **受保护执行**：评分器仍只通过临时目录隔离候选，缺少 OS/容器隔离与外部可信身份。执行不可信自定义补丁存在风险。
3. **真实 OpenCode/Harbor**：未在当前环境安装与运行，因此 Session/Subagent/Worker PoC 均未完成。
4. **真实 QA 流程**：此参考项目只使用评测方虚构 QA 结果，不能视为独立 QA 测试 Excel 的验收能力。
5. **更复杂原始资料**：PRD/Excel/SVG 适配仍限于虚构受控样本；尚未证明通用 PDF/DOCX/Figma/录屏覆盖完整。

## 下一步建议

- 在具有许可浏览器及容器权限的 CI Runner 上运行 M0 + M1 的 `--require-browser` 正反例，随后增加产物版本绑定。
- 用相同可校准用例完成 OpenCode/Harbor 的真实工作区隔离、长任务/子代理恢复与权限边界 PoC。
- 进入 M1 下一切片：复杂原始文件适配和 QA 独立来源反馈；优先复用成熟解析器而不是自写 OCR 或工作流平台。

**当前阶段结论**：M1 两项来源缺口已在虚构项目中形成可执行功能切片和独立 Node/HTTP 正反例验收，完整产品交付因真实 Chromium 未验证而仍为 `NOT_VERIFIED`。
