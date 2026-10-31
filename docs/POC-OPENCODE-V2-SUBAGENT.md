# OpenCode V2.2.3 子代理与会话实测

## 验证范围

来自实际 `opencode debug agents` 输出的已注册 Agent：`build`、`plan` 为主要 Agent；`explore`、`general` 为可见子代理；`compaction`、`summary`、`title` 为隐藏内部 Agent。本 PoC 只验证 **Build → Explore 的真实子会话调用及证据可复核性**。

`explore` 权限中 `subagent: * → deny` 属于正常的单层委派限制，不等于 Build 无权调用 Explore。不要新增自定义 Agent 或第二套代理运行时。

## 本机执行（需要已经登录并能正常使用模型的 OpenCode）

在 ADS 仓库根目录，切换到包含此文件的分支或合并后的版本，执行：

```bash
opencode --version
opencode debug agents
opencode
```

在 OpenCode TUI 中输入：

```text
/ads-subagent-smoke
```

该命令使用 `agent: build` 作为父 Agent，并显式要求通过 `subagent` 工具调用 `explore`。请不要使用 `--auto` 来绕过交互式权限检查。无需添加模型密钥或自定义 Agent 配置。

完成后在同一仓库的终端查看实际 Session：

```bash
opencode session list --max-count 10 --format json
```

从结果中找到此次会话 ID，再执行（请将占位符替换为真实 ID）：

```bash
opencode session export <session-id> --sanitize > /tmp/ads-opencode-v2-subagent-sanitized.json
```

**导出可能包含路径、提示词、工具结果或其他上下文。即便使用 `--sanitize`，仍请检查内容后再分享；不要提交原始会话或凭据到 GitHub。** 可将审阅后的脱敏 JSON 发给评审方单独分析。


## 用本地证据分析器检查已导出的会话（v0.5.3）

上传完整会话之前，可先在 Mac Mini **本地**运行：

```bash
python3 poc/check_opencode_session.py /tmp/ads-opencode-v2-subagent-sanitized.json
```

该命令仅打印 Agent 类型、工具名称及次数、委派目标是否经结构化输入确认、关联的子会话 ID 是否存在、以及分项判定；**不打印会话正文、提示词、工具参数原文或工具输出**。

某些 OpenCode 脱敏导出会将 `state.input` 和 `state.metadata` 整体替换为 `redacted`。即便工具事件名称为 `subagent`，无法独立确认目标 Agent 或子会话时仍给 `NOT_VERIFIED`。这不是失败，而是证据不足。

如果脱敏导出使目标丢失、希望本地进一步核对，可以在**你的电脑上**另外导出未脱敏文件并仅在本地检查（**不要上传、不要提交到 GitHub**）：

```bash
opencode session export <session-id> > /tmp/ads-opencode-local-private.json
python3 poc/check_opencode_session.py /tmp/ads-opencode-local-private.json
```

把检查器打印的短 JSON 发送给评审即可。请在分享前再次检查其中的工具名称不包含内部信息。仅有本地检查器的输出，依然不能独立证明所有子会话读操作与没有写入；`overall_verdict` 保持 `NOT_VERIFIED`，直到额外关联子会话事件以及 Git 工作区快照证据。

本工具仅用 Python 标准库，不需要外部依赖。可运行：

```bash
python3 -m unittest discover -s tests -p 'test_opencode_session.py' -v
```


## 证据与判定

| 证据 | PASS 条件 |
|---|---|
| Agent 发现 | `opencode debug agents` 中存在 `build`、`explore`，且 Explore 为 Subagent |
| 父调用 | 会话结构化工具事件真实显示父 Agent 调用了 `subagent`，目标为 `explore` |
| 子执行 | 存在独立子会话 ID 或可关联的子会话运行记录，并能看到 Explore 对上述文件进行只读检查 |
| 结果关联 | 子代理返回文件路径/分析结果，父 Agent 使用该结果完成回复 |
| 安全边界 | 过程中没有修改项目工作区；如发生非预期写入，判定 FAIL |

**只有文本中写了“我调用了 Explore”、只存在 Agent 注册记录、或者只有文件路径总结，都不能算子代理执行 PASS。**

判定 `PASS` 表示上述真实调用已被证据证实；`FAIL` 表示发生了确定的权限、路由、结果或写入违例；`NOT_VERIFIED` 表示没有足够结构化会话证据；`BLOCKED` 表示本机模型、服务或权限无法运行。若脱敏导出移除了必要证据，应标为 `NOT_VERIFIED`，而非推定通过。

## 下一轮，不属于本次 PASS

本次不验证 `general` 并行执行、父子任务隔离、会话中断续跑、幂等副作用或 OpenCode SDK/服务 API 真实集成。这些需要单独的任务与负例；不可使用本次 `explore` 只读验证代替。

官方依据：

- https://dev.opencode.ai/v2/docs/agents/
- https://dev.opencode.ai/v2/docs/tools/
- https://dev.opencode.ai/v2/docs/cli/commands/
- https://dev.opencode.ai/v2/docs/commands/
