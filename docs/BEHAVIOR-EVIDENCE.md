# OpenCode 行为证据

ADS 在 `ads develop --execute` 完成后，从 OpenCode `run --format json` 的 JSONL 事件流生成 `behavior.json`。该投影只保留低敏事实：完成的工具调用数、工具名计数、明确的 Skill 工具调用、测试命令的顺序和可读取的进程退出码。

## 当前可观察项

- systematic-debugging、test-driven-development、verification-before-completion 是否通过原生 `skill` 工具被调用。
- 是否观察到测试命令、直接 `write/edit/apply_patch` 工具调用。
- 测试命令是否早于第一次直接编辑工具调用。
- 是否观察到“非零测试命令 → 直接编辑工具 → 后续零退出码测试命令”的顺序；只有事件流无解析错误且末尾出现 `step_finish: stop` 时才给出顺序结论。

## 不能据此推断

- Skill 被调用不等于 Agent 遵循了 Skill 的全部指导。
- 测试命令不证明测试正确、失败是业务红灯或通过代表需求正确。
- 当前只能识别直接编辑工具；经 shell、子代理、IDE 或其他工具发生的修改可能无法识别。
- `run --format json` 是事件流投影，不是完整的持久会话审计记录；事件缺失、格式变化或缺少终止事件时，顺序结论降为 `INDETERMINATE`。
- 未观察到某行为不等于该行为没有发生；可能由宿主版本、工具链或输出协议造成。

因此报告使用 `OBSERVED` / `NOT_OBSERVED` / `INDETERMINATE`，不提供“行为合规 PASS”。原始事件流与 stderr 留在运行目录的私有文件中；对外摘要不复制提示词、命令、源代码和工具输出。

## 复核方式

```bash
python3 -m unittest tests.test_behavior_evidence -v
python3 -m unittest tests.test_develop_execution -v
```

必须结合源代码/测试差异、独立 `ads verify`、真实 e2e 结果和人工介入记录判断交付。行为证据仅帮助复盘 Agent 实际做了什么，不能替代交付正确性证据。

## 与独立验证运行的绑定

每次 `ads develop --execute` 都有唯一 `run_id`，并在 `.ads/latest-development.json` 写入摘要与 `behavior.json` 的 SHA-256。`ads verify` 开始时读取当前代码/来源/契约快照，将最新开发运行绑定到同一验证记录：

- `MATCHED`：开发输出快照与验证输入快照完全一致，且摘要、行为证据哈希和内容相互核对。
- `STALE`：开发后输入发生变化；验证仍可独立执行，但不得声称验证覆盖了该次开发输出。
- `INVALID`：开发摘要或行为证据缺失、格式错误或哈希不一致。
- `NOT_LINKED`：没有可关联的 ADS 开发运行。QA 责任运行不继承开发行为声明。

验证记录固定引用开发 `run_id` 和两份证据哈希。`ads verify` 后再修改行为文件，会使 `ads status` 在加载该验证记录时阻断。若开发后代码变化，新的验证会保留 `STALE` 关系，而不是把旧开发声明嫁接到新代码上。此关联只证明同一输入版本的对应关系，不证明 Skill 指导被遵循或业务需求已正确实现。

## 原生错误的低敏诊断

OpenCode 原生 error event 会投影有限的结构化字段：错误类型、HTTP 状态码、格式受限的错误代码和 Provider ID。原始 `message`、请求内容、响应正文及凭据不会写入公开摘要；原始事件仍只保存在本地私有运行目录。

分类规则保守处理：`provider.free-limit`/quota 代码为 `MODEL_QUOTA`，HTTP 429 但无配额代码为 `RATE_LIMITED`，401/403 为 `AUTH_OR_PERMISSION`，408/504 为 `UPSTREAM_TIMEOUT`，5xx 为 `UPSTREAM_FAILURE`，其他为 `UNKNOWN`。分类只辅助诊断，不自动重试、不切换模型/账户，也不更改权限。未知字段不会被猜测。

## 原生 Session 续接确认

当调用方显式提供 `--session` 时，ADS 不仅记录传入参数，还核对 OpenCode JSONL 事件中的原生 `sessionID`：出现目标 ID 才标记 `CONFIRMED`；出现其他 ID 标记 `MISMATCH` 并阻断；没有可观察 ID 标记 `NOT_OBSERVED` 并阻断。未请求续接时标记 `NOT_REQUESTED`。这可防止 CLI 忽略或未能确认续接时，ADS 仍将本轮报告为已续接。该确认依赖原生事件流，不能证明远程副作用恰好一次。

## 开发变更范围

每次开发摘要从执行前后的 Git 仓库快照计算 `change_set`，仅记录 Git 跟踪及未被忽略的文件中的新增、修改、删除路径及计数，不复制文件内容；忽略文件不在此清单的覆盖范围内。覆盖范围标记为 `git-tracked-and-unignored-files`。快照不可读取时标记 `UNKNOWN` / `UNAVAILABLE`，不把空集合冒充无变更。该清单是实际改动事实，不自动判定改动是否超出需求；开发摘要哈希被验证绑定后，`ads verify` 记录也会携带同一份 `change_set`，便于把变更范围与任务、需求义务和测试覆盖一起审查。
