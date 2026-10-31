# ADS-M0b｜开源能力 PoC 实测记录

> 本文件只报告当前容器真实观察结果，不把公开文档中的能力当作本地集成成功。

## 工具证据

运行 `python3 poc/probe.py`，完整输出见 `artifacts/tool-probe.json`。

| 候选组件 | 本环境 | 实际状态 | 下一步可复现实验 |
|---|---|---|---|
| Python 3.13 + SQLite（标准库） | 已安装 | **实测 PASS**，HTTP/SQLite/XLSX 评分器工作 | 保留为 M0 可移植最小案例 |
| Chromium 144 + Python Playwright 1.57 | 已安装 | **BLOCKED**，导航本地页面返回 `ERR_BLOCKED_BY_ADMINISTRATOR` | 在获准的浏览器测试 Runner 中重新校准 `full` 模式；报告 trace 和下载文件 |
| Playwright Test Agents（planner/generator/healer） | 未确认安装 Node 集成包 | **NOT_RUN**，不能将 Python runner 等同于官方 Test Agents | 在独立 Runner 安装受审的官方版本，使用 OpenCode 原生入口跑至少一个成功和两个误修复反例 |
| Harbor | CLI 未安装 | **NOT_RUN**，Docker/Podman 不可用 | 根据官方任务 schema 封装本 `project_board` 基准，运行实际隔离 Worker；先确认镜像和许可证 |
| OpenCode CLI / SDK | CLI 未安装 | **NOT_RUN** | 固定版本，真实调用 subagent / session / permissions / abort-resume，保存事件日志 |
| GSD、HelixHarness、Open SWE | 未配置 | **NOT_RUN** | 以同一冻结案例、相近上下文和工具预算进行恢复与任务可靠性对照，不叠加工作流 |
| 受保护 CI / 构建 attestation | 当前只有本地运行 | **NOT_IMPLEMENTED** | 将隐藏评分器与参考补丁存入受保护仓库，候选仅能提交补丁，由 Runner 以无凭据隔离权限执行 |

## 是否自主研发的决策（暂定）

- REUSE：Git patch、Python stdlib SQLite/HTTP、专业测试器 Playwright；不造新的 HTTP/测试执行器。
- ADAPT 待证实：Harbor 用于 agent 基准、Playwright Test Agents 用于测试候选生成和修复、OpenCode 原生 CLI/SDK 用于可恢复执行。
- BUILD：原始交付要求跨来源发现、外部只读验收、DEV/QA 对账。M0 评分器只作为小型标准案例，并非 ADS 生产级评分平台。
- STOP：在 Harbor/OpenCode/Playwright Agents 真实 PoC 完成前，不开发替代的 Agent Loop、浏览器测试生成器或完整 benchmark 调度器。

## 安全与权限事实

本地 `tempfile` 是工作目录隔离，不是安全边界。Agent 如果能够访问整个宿主文件系统，就仍可能读取评分器和参考补丁；不得把本地调通认为已抵抗恶意 Agent。未来 CI 需要按文件/容器/身份隔离、关闭不必要的网络、固定镜像与锁文件、外部重评并检查构建身份。
