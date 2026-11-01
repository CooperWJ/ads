# Superpowers：复用原生开发能力

ADS 使用 [官方 OpenCode 插件](https://github.com/obra/superpowers/blob/2ce8aa15d05bd57213e6f746f953aafb7ded7a8b/.opencode/INSTALL.md)，上游为 MIT 许可。当前固定 Superpowers 7.0.1 对应提交 `2ce8aa15d05bd57213e6f746f953aafb7ded7a8b`，使用 OpenCode V2（至少 2.0.4）的 `plugins` 配置。技能由上游维护和原生宿主注册。

## 接入已有项目

在项目根目录运行：

```bash
ads init --superpowers
opencode
```

已有 ADS Profile 时只配置插件；不覆盖 Profile、已有命令、OpenSpec、用户 Skill Router、模型或权限。新项目同时初始化 ADS。已有 Superpowers 版本保留，不强制升级。不自动改用户的全局安装。

若项目已有 `opencode.jsonc`，直接在该文件的 `plugins` 数组加入下面一项，保留注释和原配置。ADS 不另建竞争配置；V1 的 `plugin` 字段需要按官方说明迁移。

```json
"superpowers@git+https://github.com/obra/superpowers.git#2ce8aa15d05bd57213e6f746f953aafb7ded7a8b"
```

重启后让 OpenCode 使用原生 `skill` 工具列出并加载技能。已有项目的用户命令保持原样，可直接用下列提示进入实际工作：

```text
这是既有行为缺失。先加载 systematic-debugging，按原始资料复现问题；
用 test-driven-development 完成最小修复；完成前加载 verification-before-completion，
实际运行测试并报告结果。沿用现有 OpenSpec，不能修改预期换取通过。
```

| 任务 | 使用方式 |
|---|---|
| 缺失、错误、回归 | 优先 systematic-debugging，再做回归 |
| 实现已确认需求 | test-driven-development；需要时用 writing-plans 拆实现步骤 |
| 尚有关键需求歧义 | 按需 brainstorming；已确认规格不重复访谈 |
| 报告完成 | verification-before-completion，检查实际执行结果 |

不强制逐一执行全部技能；不叠加第二套规格、审批或 Agent Loop。Superpowers 的开发自测不替代独立 QA。

## 已实际验证的范围

OpenCode 2.2.3 已从固定 Git 依赖加载插件，原生 API 列出技能，并在会话中激活调试、TDD、完成核验三技能。激活使用 `resume=false`，不调用模型。真实模型请求返回 `provider.free-limit`，因此模型自主选用技能、调试和完整交付仍未验证。摘要见 [实际运行记录](evidence/superpowers-v0.6.4-native.json)。

复用现有测试与 CI，真实原生冒烟可单独运行：

```bash
ADS_OPENCODE_EXECUTABLE=/absolute/path/to/opencode \
  python3 -m unittest discover -s tests -p test_superpowers_native.py -v
```

测试启动一次性原生服务，读取官方插件状态、列出技能、激活技能并检查会话记录，随后停止服务。没有可执行文件时明确跳过；不输出原始会话或服务认证信息。现有开发切片 CI 安装固定 OpenCode 后执行此测试。
