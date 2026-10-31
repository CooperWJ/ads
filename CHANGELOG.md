# Changelog

## v0.5.1 — Chromium Runner 环境修复

- 将 `.github/workflows/m0-selftest.yml` 的 Runner 固定为 `ubuntu-24.04`，避免 `ubuntu-latest` 升级到当前 Playwright 不兼容的系统版本。
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
