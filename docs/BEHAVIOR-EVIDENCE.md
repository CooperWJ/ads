# OpenCode 行为证据

ADS 在 `ads develop --execute` 完成后，从 OpenCode `run --format json` 的 JSONL 事件流生成 `behavior.json`。该投影只保留低敏事实：完成的工具调用数、工具名计数、明确的 Skill 工具调用、测试命令的顺序和可读取的进程退出码。

## 当前可观察项

- systematic-debugging、test-driven-development、verification-before-completion 是否通过原生 `skill` 工具被调用。
- 是否观察到测试命令、直接 `write/edit/apply_patch` 工具调用。
- 测试命令是否早于第一次直接编辑工具调用。
- 是否观察到“非零测试命令 → 直接编辑工具 → 后续零退出码测试命令”的顺序。

## 不能据此推断

- Skill 被调用不等于 Agent 遵循了 Skill 的全部指导。
- 测试命令不证明测试正确、失败是业务红灯或通过代表需求正确。
- 当前只能识别直接编辑工具；经 shell、子代理、IDE 或其他工具发生的修改可能无法识别。
- `run --format json` 是事件流投影，不是完整的持久会话审计记录；事件缺失或格式变化会降低证据完整度。
- 未观察到某行为不等于该行为没有发生；可能由宿主版本、工具链或输出协议造成。

因此报告使用 `OBSERVED` / `NOT_OBSERVED` / `INDETERMINATE`，不提供“行为合规 PASS”。原始事件流与 stderr 留在运行目录的私有文件中；对外摘要不复制提示词、命令、源代码和工具输出。

## 复核方式

```bash
python3 -m unittest tests.test_behavior_evidence -v
python3 -m unittest tests.test_develop_execution -v
```

必须结合源代码/测试差异、独立 `ads verify`、真实 e2e 结果和人工介入记录判断交付。行为证据仅帮助复盘 Agent 实际做了什么，不能替代交付正确性证据。
