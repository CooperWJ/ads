# e2e 与 OpenCode 的真实产品旅程

本集成复用 tester-army/e2e 的浏览器、报告、MCP、技能和失败轨迹。ADS 只做项目配置和原生报告投影，不复制测试执行器。

## 在项目使用

需要 Node `^22.22.3 || >=24.8.0`。先安装固定依赖与 Chromium：

```bash
npm install --save-dev --save-exact e2e@0.22.0 @e2e-dev/web@0.15.4
npx --no-install e2e-web install --with-deps chromium
ads init --superpowers --e2e
```

保留项目已有 `e2e.config.ts` 和测试；没有配置时按安装包官方技能生成。`ads init` 对普通 `opencode.json` 只合并 OpenCode V2 的 `mcp.servers.e2e` 和 `skills` 数组，不安装依赖，不修改权限，不覆盖既有同名服务器或 Router。若项目使用 `opencode.jsonc`，当前 CLI 会 fail-closed 并要求手动在原文件合并 MCP 与 skills 配置；不会自动解析或改写 JSONC，也不会另建竞争配置。`ads init --superpowers --e2e` 同样遵守此限制。重启后实际验证 MCP 连接与 `e2e` 原生技能发现；配置存在不是兼容性结论。

OpenCode 负责开发与调用工具；Superpowers 提供复现、TDD 和完成前验证方法；e2e 负责操作实际应用并产出轨迹。已有 OpenSpec 要求不重复访谈。自愈可调整导航路径，关键预期仍由已确认要求给定。e2e MCP 不需要模型即可提供确定性工具，`agent.act/assert` 仍需要有额度的模型。

ADS 的 report-1 适配现会按用例投影低敏 Agent 事实：`agent.act`/`agent.assert` 数量、确定性 locator assertion 数量、动作数、模型调用/token/成本及缓存模式。摘要不复制 Agent 指令、turns、事件详情、屏幕或原始输出；模型标识仅接受安全字符集。只有报告同时观察到 `agent.act` 与确定性断言时才标记 `AGENT_PLUS_DETERMINISTIC`。缓存重放单独计数，不能冒充实时模型调用；成本或模型元数据不完整时保持 PARTIAL/NOT_REPORTED。当前 POC 的 `e2e.config.ts` 已设 `cache: 'off'`，避免模型评估被已录制动作重放掩盖；报告仍会单独记录缓存状态。该投影目前由确定性夹具验证，尚无真实 `agent.act` 模型运行，因此真实模型用量、失败诊断、代码修复与重验闭环仍未验证。

## 接入 ADS 的现有验证命令

在项目 Profile 增加一个检查（路径与测试由项目决定）：

```json
{
  "id": "browser-journey", "role": "dev", "effect": "IDEMPOTENT",
  "timeout_seconds": 180,
  "argv": ["npx", "--no-install", "e2e", "run", "--output", "{run_dir}/e2e"],
  "report": {"kind": "e2e", "path": ".ads/runs/{run_id}/e2e/report.json"}
}
```

然后运行 `ads verify`。原始报告必须写入当前新运行目录。用例机械定位是紧凑 JSON 数组字符串 `[testId,targetId,agent,repeat字符串]`，完整地消费报告身份，避免不同浏览器/Agent/重复轮次混淆。这里的定位不是人工需求编号。

此入口按完整配置的检查集合验证。过滤、跳过、未结束、flaky、运行级错误、未关闭的 `--last-failed` 遗留和清理失败不能折叠为 PASS；原生摘要与实际结果数量须一致。保留原始 JSON，再由既有义务映射核对必验集合。不要仅接 JUnit：上游将 flaky 写成 JUnit 通过，同时可能返回退出 0。

## 可重复运行的虚构案例

```bash
cd poc/e2e
npm ci --ignore-scripts --no-audit --no-fund
node node_modules/playwright-core/cli.js install --with-deps chromium
cd ../..
python3 poc/e2e/calibrate.py --out /tmp/ads-e2e-run
```

校准从冻结种子应用已知参考或坏补丁，在干净目录启动真实 HTTP/SQLite 应用：参考须完成保存、刷新、下载并读取 XLSX；假保存和缺导出列必须因相应产品断言失败。另运行真实无浏览器报告探针，证明正常、flaky、skipped 三种状态正确区分。基础设施错误不算故障检出成功。

`--reports-only` 只验证上游报告语义，不计浏览器通过。原始报告、日志、截图、下载和 Trace 留在输出目录的各例 `evidence/`。CI 上传同一批真实产物。案例只运行已知虚构变体，不接收任意不可信补丁；它不是 OS 沙箱或独立 QA 身份证明。原有容器外验收继续承担其已验证范围，当前不迁移或删除它。

## 实际来源与采用范围

- [e2e 官方仓库](https://github.com/tester-army/e2e)：采用已发布 CLI、web 引擎、MCP、原始报告和技能。Apache-2.0；依赖固定在 package-lock，不复制实现。
- [OpenCode MCP](https://opencode.ai/v2/docs/mcp-servers)：使用 `mcp.servers`、`protocol` 与官方连接 API。
- [OpenCode Skills](https://opencode.ai/v2/docs/skills)：V2 使用 `skills` 数组发现上游来源，避免套用 V1 `skills.paths`。
- [OpenCode ACP](https://opencode.ai/v2/docs/cli/acp)：保留宿主原生入口，当前不引入自研 Agent Loop；ACP 兼容不凭协议名称推定。
- [Superpowers 官方接入](https://github.com/obra/superpowers/blob/main/docs/README.opencode.md)：沿用已接入官方插件。
- [Karpathy 社区指南](https://github.com/multica-ai/andrej-karpathy-skills)：只吸收明确假设、最小实现、限定变更和可验证目标；不作为另一套工作流。
- [i-have-adhd](https://github.com/ayghri/i-have-adhd)：吸收成果可见与简洁交互原则，不默认安装持续注入插件，不推断使用者健康状况。

模型开发、真实浏览器、MCP 连接、技能发现和最终授权分别报告。本集成不把参考补丁冒充 OpenCode 开发，不通过其他账户或模型绕开额度。

## 已观察结果

首次真实旅程运行 41262125347 的参考通过，no_persistence 在刷新值断言失败，bad_export 在解析下载文件时因缺列失败；原始产物见对应 Actions Artifact。OpenCode 2.2.3 的 MCP 已连接，官方 e2e 技能被发现并显式激活。原生配置/连接是异步过程，立即读取空列表不能直接认定不支持；冒烟入口会有界等待真实状态。

```bash
python3 poc/e2e/native_probe.py --executable /绝对路径/opencode --out /tmp/ads-e2e-native
```

该入口隔离 XDG、不给模型发送提示，仅验证真实连接与显式技能激活。不要公开 native-private.log 或 private/，其中可能含服务临时凭据；CI 只保留 native-summary.json。首次结果索引见 docs/evidence/e2e-v0.6.7-first-validation.json。

同轮实际原始需求开发仍被匿名模型额度拒绝，0 工具调用且源码未变化，摘要见 docs/evidence/opencode-v0.6.7-attempt.json。本轮未把参考工程、模型配置或技能加载计为完整模型开发成功。


## OpenCode Console Agent profile

默认 `e2e.config.ts` 只执行确定性旅程。Agent 混合旅程位于独立的 `e2e.agent.config.ts`，避免普通 CI 在没有用户授权或模型额度时偷偷发起模型请求。

准备与运行：

```bash
cd poc/e2e
npm ci
npm run login:agent
npm run models:agent
ADS_E2E_OPENCODE_MODEL='<models 命令返回的精确模型 ID>' python3 calibrate.py --agent --out /tmp/ads-e2e-agent
```

该 profile 使用 e2e 官方 `opencode-console` OAuth provider；通过设备授权登录 OpenCode Console，并且只使用显式指定的模型。模型列表以 `npm run models:agent` 的实际结果为准；裸模型 ID 对应 OpenCode Zen，`go/` 前缀对应 OpenCode Go，后者需要 Go 订阅。部分 Zen 免费模型不向第三方客户端开放；如果当前模型不在列表中，不应尝试绕过限制，也不会自动切换到其他模型或账号。无可用模型、凭证缺失或额度不可达时，结果保持 BLOCKED。

Agent 只负责在 UI 中选择 Project Echo、输入指定内容并保存。保存后的状态、刷新后的持久化值、数据库记录和 XLSX 导出由确定性断言与独立 oracle 检查。Agent profile 继承 `cache: 'off'`，限制最大 8 步、12 次模型调用和 32k 输入 token。CI 只验证 profile 配置，不登录、不调用真实模型；真实执行结果必须由显式运行产生的 report 与模型用量证据确认。
