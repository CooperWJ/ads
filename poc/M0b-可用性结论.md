# M0b 当前可执行性结论

本地只读 `poc/probe.py` 提供环境探针。执行探针只能证明二进制/包是否存在，**不能证明会话恢复、代理协作或 Harbor Worker 已完成真实 PoC**。

- OpenCode：本环境无 CLI 且 npm registry DNS 不可用，因此 `Session/Subagent/权限/恢复` 均为 `NOT_RUN`。
- Harbor：本环境没有 Harbor 命令、容器运行时；PyPI 解析不可用；真实隔离 Worker 评测 `NOT_RUN`。
- Playwright：Python 包可导入，但配套 Chromium 二进制缺失，真实校准为 `NOT_VERIFIED`，strict 仍阻断。
- Node：已在独立进程运行候选 JS 和 HTTP 后端联通，但仅是有限 DOM 模拟，不可替代真实浏览器。
- 推荐在项目授权的 CI Runner 运行：`python -m playwright install --with-deps chromium` 和 `python evaluator/calibrate.py --require-browser`。此处不提供绕过系统安全策略的方法。
- 若需要 OpenCode/Harbor：先在可联网、具备容器权限的隔离工作站按官方固定版本安装，并记录版本、时间、任务、真实退出码、日志及模型费用。未提供 LLM 凭据时，只能验证 CLI 版本和无模型操作，不声称 Agent 开发可靠性。
