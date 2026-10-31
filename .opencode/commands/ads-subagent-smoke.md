---
description: "验证 OpenCode V2 Build → Explore 真正的子会话调用（只读）"
agent: build
---

你正在执行 ADS 的 OpenCode V2 Subagent 最小实测，标识：ADS-OPEN-V2-EXPLORE-SMOKE-001。

必须实际使用内置 `subagent` 工具委派给 agent ID 为 `explore` 的子代理，不能只由 Build 自己搜索后冒充委派成功。

给 Explore 的完整任务：
- 只读检查当前 ADS 仓库中 `AGENTS.md`、`.opencode/commands/opsx-apply.md` 和 `.opencode/skills/openspec-apply-change/SKILL.md`。
- 报告这些文件的绝对路径，简述 OpenSpec apply 的入口如何引用或关联 SKILL；如引用关系不明确，明确写“未确认”。
- 不运行修改工作区的命令；不创建、编辑、删除任何文件；不展示凭据或隐私内容。

委派返回后，Build 只输出：
1. 是否观测到实际 `subagent` 工具调用：未证实时写 `NOT_VERIFIED`，不要凭模型表述宣称通过。
2. 子代理 ID（应为 `explore`）、返回的子会话 ID（若工具确实提供）、找到的文件路径和简短结论。
3. 若调用失败或受权限阻断，保留原始错误类型，不要回退为 Build 独立完成后声称成功。
4. 不要修改任何文件；最终验收以独立会话导出中的工具事件为准，不能只以这段文本为准。
