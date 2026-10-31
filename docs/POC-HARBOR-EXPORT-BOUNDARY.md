# Harbor 独立导出验收最小集成

## 目标与信任边界

这是 A04 的最小工具集成校准。固定 Harbor 0.25.0，使用内置 oracle 执行可信参考/故障脚本，不调用 AI 模型、不需要模型凭据。

候选容器只包含虚构应用种子、采集器和运行 ID。oracle 将既有补丁生成的候选放入该容器，通过 HTTP 保存备注并下载 XLSX。Harbor 随后把数据产物交给新的独立 verifier 容器。评分器复用既有字段和值契约，只解析 ZIP/XML/JSON，不运行候选 Python/JS。

| 案例 | 预期 reward | 意义 |
|---|---|---|
| reference | 1 | 真实 HTTP 导出符合原有 XLSX 契约 |
| bad-export | 0 | 缺列导出被拒绝 |
| gate-tamper | 0 | 缺列候选在自己容器创建假的评分脚本和奖励文件，仍不能通过外部验收 |

全部原生 trial 完成、无异常、明确 separate verifier、结果与预期一致、任务指纹和运行 ID 不变时，校准才通过。基础设施报错不能冒充负例被检出。

## 执行

在有 Docker 的 Linux Runner 上：

```bash
python3 -m pip install 'harbor==0.25.0'
docker pull python:3.12.12-slim-bookworm
image_ref=$(docker image inspect python:3.12.12-slim-bookworm --format '{{index .RepoDigests 0}}')
python3 poc/harbor_export/prepare.py /tmp/ads-harbor-run --image "$image_ref"
harbor run --path /tmp/ads-harbor-run/tasks --agent oracle --env docker --n-concurrent 1 --job-name boundary --jobs-dir /tmp/ads-harbor-run/jobs
python3 poc/harbor_export/check_results.py /tmp/ads-harbor-run /tmp/ads-harbor-run/jobs/boundary --out artifacts/harbor-boundary-summary.json
```

目标目录必须不存在；新一轮使用新目录。CI 入口 `.github/workflows/harbor-boundary.yml` 保留 manifest、依赖清单和原生结果。基础镜像在每批解析为 digest，保证同批一致；跨批比较必须核对摘要，尚无全依赖 lock。

本地无 Docker 时只做配置与标准测试，不把它升级成隔离运行 PASS。原生配置校验命令：

```bash
python3 -m unittest discover -s tests -p 'test_harbor_export.py' -v
```

## 采用决策与后续

采用 Harbor 原生任务、Docker、oracle 和 separate verifier；ADS 只提供任务生成与严格结果投影。删除自研评测调度平台的必要性假设。

当前只校准数据产物边界。artifact 可被候选伪造，因此 XLSX 通过不能证明实际应用正确、持久化可靠、UI 可用或 AI 完成任务。采集记录属于受控校准观测，不是一般受信遥测。

完整开发切片仍需 OpenCode 真正实施、测试与调试。完整 UI/API/DB 外部验收需要测试器访问隔离服务的独立拓扑，不能简单把候选代码复制进评分容器后执行。PR 自测的评分器仍随 PR 可改，必须与发布级受保护策略分开。

依赖链：本候选基于 PR #4，未授权合并时保持独立可审查；不覆盖或重写该候选。
