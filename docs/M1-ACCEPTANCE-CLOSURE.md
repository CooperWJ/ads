# M1 来源缺口到可执行验收的闭环

## 目标

在原始 PRD 中独立发现的两项新交付义务：`menu-route-accessible`（导航菜单打开页面）和 `page-error-state`（项目请求失败时显示明确错误）不应被旧 M0 的 18 项测试静默吞掉。本轮不修改受保护的原始 PRD、原始来源审核样本或原有 18 项冻结验收义务。

## 最小实现

- `tools/build_variants.py` 从冻结的虚构初始代码生成 `reference_m1`、`m1_missing_menu` 和 `m1_silent_error` 补丁。
- `evaluator/m1_acceptance.json` 是评测方控制的新增验收契约，仅接受与原始审查中新发现两项 ID 精确一致的版本、来源原文和检查方式，不能由候选代码修改。
- 运行 `--acceptance-bundle m1` 才会读取新增契约；默认 `m0` 完整兼容上轮，仍报告发现的新增需求 GAP。
- `menu_route_accessible` 检查真实 HTTP 返回的菜单链接与 `/board` 页面，而不是只检查文字是否存在。
- `request_error_state` 用 Node 的轻量 DOM 模拟执行真实候选 `app.js`，触发对真实 HTTP 404 的处理，并验证独立可访问错误提示；先通过服务返回的 HTML 校验 `role=alert` 和隐藏初始状态。
- 完整 `full` Profile 在真实 Chromium 中单独执行：从导航菜单进入页面、检查字段、保存导出、刷新，再发出真实 404 并检查用户可见 alert。

## 可复现命令

```bash
python3 -m unittest discover -s tests -p 'test*.py' -q
python3 evaluator/calibrate_m1.py
python3 evaluator/grade.py --candidate reference_m1 --profile integration --acceptance-bundle m1 --out /tmp/ads-m1
python3 evaluator/grade.py --candidate m1_missing_menu --profile integration --acceptance-bundle m1 --out /tmp/ads-m1-menu-fault
python3 evaluator/grade.py --candidate m1_silent_error --profile integration --acceptance-bundle m1 --out /tmp/ads-m1-error-fault
# 只能在获准的真实浏览器 Runner 上执行完整交付验证
python3 evaluator/calibrate_m1.py --require-browser
python3 evaluator/grade.py --candidate reference_m1 --profile full --acceptance-bundle m1 --require-delivery --out /tmp/ads-m1-full
```

## 正反例与证据边界

| 候选 | Node + HTTP | 完整 Chromium | 结论 |
|---|---|---|---|
| reference_m1 | PASS | 必须独立运行 | Node PASS 不等于完整交付 |
| m1_missing_menu | FAIL | 必须失败 | 不能只靠页面文字冒充菜单 |
| m1_silent_error | FAIL | 必须失败 | 不能静默吞掉 HTTP 失败 |
| reference（旧实现） | FAIL | 未满足新增要求 | 旧 M0 PASS 不能覆盖新 PRD |
| empty | FAIL | 未满足原有要求 | 空实现不允许通过 |

`source_discovery.status=GAP` 是“相对原 M0 义务”的差异记录。M1 选择后，`source_discovery.acceptance_closure` 才是独立新增义务的验证状态；缺少真实 Chromium 时仍为 `NOT_VERIFIED`，`delivery_verdict` 也不得为 PASS。`grade.json.status` 是所选 Profile 的结果，不能被宣传为产品完整交付。

测试预期仍属于评测器侧。评分器只有本地工作区隔离，候选 Python/JS 并无 OS 级安全沙箱；未接入受保护 CI、OpenCode Session/Subagent 或 Harbor 的真实执行环境。新版本只是完成从独立来源缺口到执行检查的 M1 垂直切片。
