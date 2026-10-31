# OpenCode 完整开发切片与外部验收入口

## 当前事实

本轮已安装并运行 `@opencode/cli@2.2.3`。匿名 `opencode/glm-5.3-flash-free` 返回 `provider.free-limit` / HTTP 429，CLI 退出 1。没有发生候选代码生成，完整开发切片维持 BLOCKED。低敏记录见 `docs/evidence/opencode-v0.5.9-model-probe.json`。

Harbor 0.25.0 的内置 OpenCode 安装器使用 `opencode-ai`；该包未提供 2.2.3。暂不声称它与用户的 V2 宿主兼容。保留 Harbor 已验证的独立导出评分，开发改用原生 V2 CLI；不新增 Agent Loop。

## 在已配置模型的宿主执行真实开发

从本候选仓库根目录准备工作区：

```bash
python3 poc/development_slice/workspace.py prepare /tmp/ads-slice-run
cd /tmp/ads-slice-run/workspace
opencode
```

在 OpenCode 中选择你已有权限的模型，输入：

```text
读取 TASK.md 和 raw/ 全部资料，按 TASK.md 完成开发、自测和故障修复。只报告实际结果和未验证项。
```

该工作区只有种子、原始资料和开发说明，没有评分器、答案或参考补丁。它是输入隔离，不是 OS 沙箱；在本机执行时仍沿用宿主权限。TASK.md 要求新测试放在 dev_tests/，交付代码限制为既有三文件；拒绝改原始资料降低预期。

完成后退出 OpenCode，回到 ADS 仓库根目录导出：

```bash
python3 poc/development_slice/workspace.py export /tmp/ads-slice-run /tmp/ads-slice-candidate
```

输出 candidate.patch 与候选摘要。导出从最初基线计算，包含 Agent 已提交的变更；只导出允许的三文件。原始资料变化、越界新增或符号链接会阻断。导出不运行候选代码，不据此认定模型执行或自测通过。原始 Session 留在本机，不能直接提交公共仓库。

## 容器外全旅程验收

在 Linux Docker Runner 上，配置 Git、Node 和 Playwright 1.57.0/Chromium。基础镜像解析为摘要后：

```bash
docker pull python:3.12.12-slim-bookworm
image_ref=$(docker image inspect python:3.12.12-slim-bookworm --format '{{index .RepoDigests 0}}')
python3 poc/development_slice/docker_grade.py \
  --candidate /tmp/ads-slice-candidate/candidate.patch \
  --image "$image_ref" --profile full --out /tmp/ads-slice-acceptance
```

候选应用代码仅进入只读容器镜像。评分器和 Chromium 在候选容器之外；数据库单文件挂载到一次性工作区，容器不获得评分器、框架 Git 仓库或 Docker socket。运行后读取真实 Docker 配置，校验只读根、内部网络和挂载边界；没有 Docker 时绝不回退本机进程。

这仍是同一 Runner 上的开发验证拓扑，不是生产级受保护 CI：评分规则随 PR 可改、内核共享、QA 仍用合成校准输入。grade.json 的完整义务 PASS 只在本虚构契约范围内解释，不能升级为独立 QA、生产交付或 ADS 有效性证明。

## 如何认可完整切片

必须联合查看：固定来源/种子/模型/预算、OpenCode 原生工具及开发执行记录、候选源码摘要、实际测试/失败/修复、外部真实全旅程结果、人工介入和成本。工作区、补丁、参考解校准或自然语言报告任一单独存在都不够。

`.github/workflows/development-slice.yml` 只校准验收拓扑：参考实现须全旅程通过，缺菜单和静默错误两个变体须检出。该工作流不调用模型，不能将成功当作 OpenCode 已完成开发。
