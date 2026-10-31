# ADS-M2-001｜OpenCode V2.2.3 Session 恢复最小真实实验

**目的：**验证 OpenCode 在客户端退出和重新打开后，是否能继续同一个 Session、保留会话记录，并在恢复时避免重复执行已经发生的副作用。

**不验证：**工具执行过程中被强制终止、OpenCode 服务端崩溃、断电、网络断连、生产环境幂等协议。这些必须使用独立故障注入，不能以本实验的 PASS 替代。

## 1. 准备

在 ADS 仓库的 `feat/m2-opencode-session-resume-v0.5.6` 分支下（本实验前不要再修改/提交文件）：

```bash
python3 poc/recovery_poc.py init
```

记录输出的 `run_dir`，形如 `/tmp/ads-oc-recovery-xxxx`，下文用 `<RUN_DIR>` 代替。它**只能**指向脚本创建的临时目录，不涉及真实业务、凭据和 Git 项目文件。

## 2. 第一阶段：产生一次受控副作用

在仓库根目录运行 `opencode`，**新建会话**，输入：

```text
/ads-recovery-phase1 <RUN_DIR>
```

Agent 应实际通过 shell 调用 `python3 poc/recovery_poc.py apply`；返回 `APPLIED`、`attempts=1` 后停止。此时在另一个终端执行：

```bash
opencode session list --max-count 10 --format json
opencode session export <SESSION_ID> > /tmp/ads-recovery-before-private.json
```

将真实 Session ID 记录下来。**不要上传或提交未脱敏 Session 文件**：即使为新会话也可能含工具输入、路径或其他上下文。

## 3. 客户端退出、重新进入同一 Session

正常退出 OpenCode **客户端**（不要删除 Session；确保第一阶段已完成），再从仓库根目录执行：

```bash
opencode --session <SESSION_ID>
```

在恢复后的会话中输入：

```text
/ads-recovery-phase2 <RUN_DIR>
```

第二阶段只允许 `verify`，**不得再次执行 `apply`**。应返回 `PASS`、`attempts=1` 和 `baseline_drift=false`。

退出客户端后导出同一 Session：

```bash
opencode session export <SESSION_ID> > /tmp/ads-recovery-after-private.json
```

## 4. 独立证据审计

```bash
python3 poc/recovery_poc.py audit \
  /tmp/ads-recovery-before-private.json \
  /tmp/ads-recovery-after-private.json \
  <RUN_DIR>
```

严格要求：两次导出 Session ID 一致；Project ID 一致；旧消息 ID 保持；有新增用户/Agent 消息；第一阶段工具调用确实包含 `apply`；恢复后的新事件包含 `verify` 而不再包含 `apply`；临时目录真实计数等于 1 且基线未漂移。任何证据不足都返回 `NOT_VERIFIED` 和非零退出码，不能冒充 PASS。

只把该脚本输出的**简短审计 JSON**发给审查方。原始两个 Session 文件保留本机，不上传 GitHub；审计器不会输出原始提示词、shell 命令、Session ID 或工具内容。

## 5. 核验边界与清理

- `PASS` 只说明**同一个 OpenCode Session 的客户端退出后恢复，并保持受控一次性副作用不重复**。
- 它不证明“执行到一半断电后也不会重复”；不证明其他副作用（数据库、远程调用）存在幂等保护；不证明全程无工作区写入。
- 检测到 `BASELINE_DRIFT` 时停止，不应修改基线来得到 PASS。
- 实验结束且保留审计输出后，可以人工删除对应 `<RUN_DIR>` 临时目录；脚本不会自动删除。
- 官方 V2 命令参考： https://dev.opencode.ai/v2/docs/cli/commands/
