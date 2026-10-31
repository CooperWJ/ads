---
description: "ADS OpenCode 同一 Session 跨客户端恢复实验：第一阶段一次性副作用"
agent: build
---

只运行 ADS-OC-RECOVERY-001 的第一阶段。此命令是受控、虚构的 OpenCode Session 持久化实验，不是业务开发任务。

实验目录由用户通过 $ARGUMENTS 提供；它必须是先用 `python3 poc/recovery_poc.py init` 在系统临时目录产生的路径。

必须使用真实 `shell` 工具执行一次且仅一次：

```bash
python3 poc/recovery_poc.py apply "$ARGUMENTS"
```

只在返回 `status=APPLIED` 且 `attempts=1` 时报告第一阶段成功。遇到 `BASELINE_DRIFT`、`REPEATED_APPLY`、异常或不确定状态，报告原始状态并停止。**严禁为了让输出变绿重试 apply**。

不要修改项目源文件或测试。完成后立即停止，不要自行开始第二阶段。用户将退出客户端并使用相同 Session ID 恢复。
