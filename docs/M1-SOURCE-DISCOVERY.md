# M1 原始资料发现：多来源完整性 PoC

## 完成范围

- 从 `fixtures/project_board/raw/` 独立枚举所有文件，不依据开发 Agent 已登记的需求列表反推来源。
- 当前确定性适配器：UTF-8 Markdown 的标题/段落/列表、SVG 中可枚举的 `text` 节点、XLSX 中全部 Sheet 和非空行（保留公式文本，不执行公式）。
- 基于原始字节 SHA-256、来源定位 `Lx`/`Sheet!Rx`/`text[n]`、片段 SHA-256 建立稳定可回溯的来源清点。
- 利用评测方独立保存的 `evaluator/source_review.json` 逐项核对来源决策，不存在未经说明的 `EXCLUDED`/`CONTEXT` 功能片段。
- **与既有 M0 18 项基准交叉比较**：新增 PRD 中的「菜单可访问」和「请求失败提示」尚无可信产品验收，明确 `GAP`，而非虚报全部交付完成。
- `grade.json` 同时输出选定 Profile 状态、原始来源清点状态和独立交付结论。

## 真实执行

```bash
# 当前工作目录为工程根目录
python3 -m discovery.cli --inventory-only   # 原始枚举，退出码 0，不代表审阅通过
python3 -m discovery.cli                    # 预期退出码 2：存在两个新验收缺口
python3 -m unittest discover -s tests -p 'test*.py' -q
python3 evaluator/calibrate.py
python3 evaluator/grade.py --candidate reference --profile backend --out /tmp/ads-m1-grade
```

`source_discovery.coverage_dimensions` 分开报告 `material_inventory`、`source_extraction`、`source_decisions`、`accepted_obligation_verification`。前三个 PASS 不代表第四个 PASS。

## 不得冒充的能力

1. 这套适配器仅在**受控虚构材料**上有效。它不代表对任意 DOCX、PDF、截图、录屏、Figma 的自动完整语义识别。
2. 抽取到片段不等于已经理解业务规则；尤其是 XLSX 公式仅作为来源字符串，不能充当独立 Oracle。
3. `source_review.json` 是**虚构基准评测方编制的固定审阅样本**，文件内 reviewer 为校准来源标识，并非身份认证或业务人员真实批准。
4. 当出现新格式、不可读文件、额外 Sheet/片段、源文件指纹漂移或无法匹配审阅时，评测阻断；不得把缺失资料算作 0 个要求。
5. 真实项目需要候选提取 → 对歧义/冲突/排除人工确认 → 已确认义务绑定独立验收；**不应照搬本基准的逐行人工签字方式**。
6. 只有 M0 的真实浏览器、外部可信 CI/OS 隔离、OpenCode/Harbor 真实集成通过后，才能宣称对应能力已验证；本轮没有补齐这些环境要求。

## DEV/QA 边界

本轮是独立需求发现能力的第一个小切片；没有修改 QA 的真实用例审批、测试追踪或发布验证。今后 QA 应独立读取原始来源、实际产品与历史缺陷，不以 DEV 提取清单作为唯一范围；需要在 M3 将此能力连接到 QA 多 Sheet 案例和反向遗漏发现。

## 向成熟项目演进

后续按已确认的 ADS-ARCH-003 PoC 计划评估 Docling 处理复杂 PDF/DOCX、Figma API 处理组件与界面节点，以及成熟 XLSX 读取工具的公式、日期、外链和大文件策略；不是永久维护此简化解析器。未得到真实权限、运行环境和样本之前不称为已集成。
