---
description: "ADS OpenCode 同一 Session 跨客户端恢复实验：第二阶段检查已执行副作用"
agent: build
---

这是 ADS-OC-RECOVERY-001 第二阶段，必须在 **退出并重新打开 OpenCode 客户端的相同 Session** 中使用。

实验目录参数：$ARGUMENTS。你必须基于原有会话识别这是恢复后检查，不允许重复执行第一阶段。

必须使用真实 `shell` 工具执行：

```bash
python3 poc/recovery_poc.py verify "$ARGUMENTS"
```

此阶段**严禁调用 apply**，不得在失败时补做、重试副作用或修改项目文件。只允许返回真实 `status`、`attempts`、`baseline_drift` 和 `marker_valid`。如结果不是 `PASS`，直接报告失败并停止；后续由独立审计器读取两个时点的 Session 导出验证。
