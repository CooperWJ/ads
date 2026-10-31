# M0b｜真实 OpenCode、Playwright、Harbor 实测手册

> 下列命令是进入**已授权的独立执行环境**之后的实测步骤，不表示本发布已经运行过这些外部工具。先记录软件版本和身份信息；不得上传用户项目真实凭据或业务数据。

## 1. Playwright（首要阻断项）

```bash
python3 -m pip install 'playwright==1.57.0'
python3 -m playwright install chromium
python3 evaluator/calibrate.py --require-browser
```

`--require-browser` 需要参考解的 `real_chromium_user_journey=PASS`，且 `ui_crash` 不得通过；缺少二进制或浏览器策略禁止导航，整个校准 FAIL。不调整或规避公司/Runner 管理策略。

Playwright Test Agents 官方建议：在隔离项目执行 `npx playwright init-agents --loop=opencode`；它用于生成测试候选，最终参考评分器与隐藏预期应在另一权限域运行。

## 2. OpenCode 真正执行能力

先安装获准的 OpenCode 版本，执行 `opencode --version` 并记录版本、模型和权限配置。测试只面向虚构工程。

```bash
opencode agent list
opencode run --format json --agent build "仅阅读虚构工程，解释 app.py 中的入口与用户旅程，不修改文件。"
opencode session list --format json
```

会话中断恢复和子代理还需另行验证：实际保存/恢复同一 Session、进行任务型调用、核对工具调用证据和最终 Git diff；不能以命令返回 0 代替这些场景的验收。API 密钥通过组织规定的安全方式配置，不写入脚手架。依赖当前具体版本的 CLI `--help` 实测结果。

参考：https://docs.opencode.ai/docs/cli/

## 3. Harbor 评测任务

须提供已批准的隔离执行环境（Docker/Podman 或 Harbor 支持的其他 Runner），先验证：

```bash
harbor --version
harbor run --help
```

官方 `harbor run --path ./your-task --agent ... --model ...` 支持本地任务，但其 task schema、agent adapter、预算、隔离和数据集结构需按实际安装版本确认。不应把目前的 `evaluator/grade.py` 直接称作 Harbor 任务适配器。PoC 验收需要真实 Worker 运行参考和坏样例、保存任务日志和评分，并证明工作区不泄漏隐藏预期。

参考：https://github.com/harbor-framework/docs/blob/main/cli/run.mdx

## 4. M0b 完成判据

- Playwright `full` 的参考 PASS、UI 异常 FAIL，并保留 Trace。
- OpenCode 子代理、Session 恢复、权限错误、中断和重复副作用有真实事件记录。
- Harbor 真实 Worker 至少跑一个参考与一个故障案例；若不合适则记录不采用原因与替代方案。
- 受保护评分器与候选执行不共享身份与隐藏文件，按固定源/镜像版本重评。

任何一项缺失，M0b 不可标记全面 PASS。
