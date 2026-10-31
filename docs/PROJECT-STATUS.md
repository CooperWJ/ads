# ADS 当前进展与下一阶段任务（2026-10-31）

**基线：**以 GitHub `CooperWJ/ads` 当前主分支为事实源；本文的 v0.5.6 内容为功能分支候选，不得在实际 Mac Mini 运行之前宣称恢复 PASS。

## 已获得可复核的结果

| 能力 | 状态 | 证据或边界 |
|---|---|---|
| M0a 虚构基准正反例校准 | PASS（已测范围） | 真实 HTTP/SQLite/XLSX/Node、故障变异 |
| M0/M1 真实 Chromium | PASS（已测范围） | GitHub Ubuntu 24.04 Runner；M0/M1 严格参考+坏变异测试 |
| OpenCode 2.2.3 Build → Explore 原生调用 | PASS | 用户本机独立父子 Session JSON 分析；工具和目标结构化核对 |
| Explore 子会话真实只读工具事件 | PASS | 用户本机检查器报告，已与父会话 ID 关联 |
| OpenCode 跨客户端会话恢复 | NOT_VERIFIED | v0.5.6 新增可执行 PoC；本机真实运行尚未完成 |
| 工具执行中途崩溃恢复 / 幂等 | NOT_VERIFIED | 与客户端重启分开验证；不得混同 |
| 子代理全过程无工作区写入 | NOT_VERIFIED | 已有只读操作事件，不代表完整安全审计 |
| 受保护独立评分 CI | NOT_IMPLEMENTED | 现有仓库 Action 是自测；主分支尚未启用保护 |
| Harbor 隔离 Worker | NOT_TESTED | 未在具备 Harbor/容器权限的环境运行 |
| Playwright Test Agents → OpenCode | NOT_TESTED | 仅浏览器原生 E2E 校准通过，不代表 agents 通过 |
| M1 多源真实需求发现 | PARTIAL | 虚构 MD/SVG/多 Sheet XLSX；未覆盖通用 PDF/Figma/视频 |
| M3 独立 QA | NOT_IMPLEMENTED | 尚无真实多 Sheet QA 独立执行与缺陷回流 |
| M4 发布/部署身份 | NOT_IMPLEMENTED | 无生产环境发布/冒烟 |
| M5 三轴对照 | NOT_STARTED | 缺盲测和新鲜案例 |

## 下一阶段执行优先级

| 优先级 | 任务 ID | 下一个可独立验收的最小结果 | 依赖 |
|---|---|---|---|
| P0 | A06 / C04-a | OpenCode 同一 Session 客户端退出→恢复、单次副作用不重复 | v0.5.6 PoC、用户本机执行 |
| P0 | E01-a | `main` 的受保护分支规则、必需 CI 检查、未授权自改检查失败 | GitHub 管理权限 |
| P0 | A04 | Harbor 真实 Docker Worker 运行参考/坏变异、证据与资源报告 | Linux Runner + 容器许可 |
| P1 | C04-b | 工具中途终止/重试/输入基线漂移，负例 fail-closed | C04-a PASS 后 |
| P1 | A05 | Playwright Test Agents 在 OpenCode 生成/修复测试，外部 Oracle 不可更改 | 真实受信评分边界 |
| P1 | D03 | QA 多 Sheet 输入→质量校验→差异→自动化执行→结果回填 | M1 收敛与测试 Adapter |
| P1 | B01–B05 | 多源提取能力、真实遗漏与人工争议闭环 | 素材解析器 PoC |
| P2 | A07/A08 | GSD/HelixHarness/Open SWE 对照、复用 ADR | 基础恢复与隔离 |
| P2 | D02/D04/E02/E03/F01/F02 | API/DB、证据身份、部署、注入、盲测与迁移 | 上述核心闭环 |

## 研发边界

1. 先证明现有 OpenCode 原生能力，缺口再用极少量确定性脚本补充；不建第二套 Agent Loop。
2. Browser PASS 不等于 Harbor PASS；普通 GitHub CI PASS 不等于受保护外部评分 PASS。
3. README/AGENTS 只陈述当前能力，新增版本记录仅进 CHANGELOG。
4. 每次新迭代递增版本，以最新主分支增量开发，旧发布可追溯。
5. 无真实业务代码、业务 SQL、凭据、真实验收输入进入公共模板。
