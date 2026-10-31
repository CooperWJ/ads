# 恢复证据修复验收记录

基线提交：fc9098f14ad6f6bc2d79b016f5dc4d043cd2c52a。发布候选版本由 VERSION 指定。

## 修复命题

旧审计可把 echo、另一个实验路径和被改写历史消息识别为恢复通过。本轮仅修复本地材料一致性检查，不声称获得独立受信执行或原生工具崩溃恢复能力。

## 已执行验证

- `python3 -m unittest discover -s tests -p 'test*.py' -v`：115 项通过，包含真实跨 Python 进程的持久化与重复 apply 拒绝。
- `python3 evaluator/calibrate.py`：14 项后端/有限 Node 真实 HTTP 校准通过；浏览器缺依赖，NOT_VERIFIED。
- `python3 evaluator/calibrate_m1.py`：5 项 integration 正反例匹配；本地 full 未校准。
- `git diff --check`：通过。

反例覆盖：phase1/phase2 echo、错误脚本、错误实验、shell 复合命令/重定向、历史正文变化、重复/缺失 ID、缺失/跨实验/失败回执、布尔 attempts、额外 shell、重复 apply、基线漂移、符号链接、损坏尝试记录。

## 保留限制

1. OpenCode 导出结构只支持本项目明确处理的形态；stdout 必须是 JSON 回执，未知形态拒绝，不能猜测通过。
2. 导出可被整体伪造；本地一致性不是独立 attestation。必须保留 `LOCAL_EXPORT_CONSISTENCY_ONLY`。
3. 更严格的协议需要用户实际 OpenCode 宿主复测，旧 v1 PASS 不自动升级。
4. 当前环境没有 OpenCode、Harbor 或 Docker 可执行文件；不因此把相应集成标记通过。真实 Chromium 由 PR 工作流另行执行。
5. 原始需求到完整开发切片、独立 QA、第二项目接入与效果对照尚未交付。

本轮没有新增通用崩溃执行器、Agent Loop、业务代码或额外需求权威。
