# 4D 拆解管线 — Claude Code 执行指令

> 将以下指令复制到 Claude Code 对话中，或将本文件放到 `.claude/commands/4d-analyze.md`
> 触发：在 Claude Code 中说 "4D 拆解《书名》"

---

## 执行前检查

1. 确认 `config.yaml` 存在且 `llm.api_key` 已填写
2. 确认 `paths.books_dir` 下有目标 EPUB 或 `full_text.txt`
3. 如果没有，先用 book_downloader 下载：`python book_downloader/book_downloader.py search "书名"`

## 阶段零：预处理

用 Claude Code 的 `Task` 工具启动一个子 Agent：

```
Task goal: "预处理全书文本"

全文文本路径: {BOOKS_DIR}/{book}/full_text.txt

执行以下操作（只做结构化提取，不做任何分析性判断）：
1. 章节分段：识别章节边界，输出 [章序号, 章标题, 起始段, 终止段, 字数]
2. 关键术语索引：提取明确定义的术语和高频专有名词（≥5次），标注位置和频次
3. 书型分类：论证型/叙事型/混合型/参考型，附置信度

输出为 strict JSON（必须能被 json.load 解析），保存到 {BOOKS_DIR}/{book}/analysis/preprocess_output.json

**禁止**：不要输出"本书核心思想""作者主要观点"等分析性内容。
```

等待完成，记下预处理产物路径。

## 阶段一：四维并行拆解

用 Claude Code 的 `Task` 工具**同时启动 4 个子 Agent**（Claude Code 支持并行 Task）：

### Agent A — 骨架拆解

```
Task goal: "骨架拆解"

预处理产物: {BOOKS_DIR}/{book}/analysis/preprocess_output.json
全书文本: {BOOKS_DIR}/{book}/full_text.txt

只用 MECE 和金字塔原理做结构分析，禁止使用心理学/哲学/叙事学术语。

步骤：
1. MECE 全书结构——将全书主题归入互斥且穷尽的维度
2. MECE 章内结构——每章提取核心主题+子主题
3. 金字塔归约——章结论→篇结论→全书核心结论
4. 结构完整性自检——覆盖矩阵

输出 strict JSON，保存到 {BOOKS_DIR}/{book}/analysis/agent_a_skeleton.json
```

### Agent B — 思想拆解

```
Task goal: "思想拆解"

预处理产物 + 全书文本同 Agent A。

只用第一性原理和概念本体做思想分析，禁止使用"第X章""作者认为"等结构表述。

步骤：
1. 底层假设提取——逐章追问"作者默认了什么没说的前提"
2. 核心概念提取——识别作者原创或重点使用的概念
3. 概念本体建模——定义 is-a / part-of / causes / depends-on / contradicts 关系
4. DIKW 层级标注——每个概念标 D(数据/事实) I(信息) K(规律) W(智慧)

输出 strict JSON，保存到 {BOOKS_DIR}/{book}/analysis/agent_b_thought.json
```

### Agent C — 论证拆解

```
Task goal: "论证拆解"

预处理产物 + 全书文本同 Agent A。

只用论证映射和 Bloom 认知层级做逻辑分析，禁止讨论概念含义/叙事技巧。

步骤：
1. 论证链路提取——[前提]→[推理类型]→[结论]
2. 论证质量评估——逻辑谬误检测、证据充分性、前提可验证性
3. Bloom 认知层级分布——每章标记忆/理解/应用/分析/评价/创造
4. 关键论证链——识别支撑全书核心结论的承重墙论证

输出 strict JSON，保存到 {BOOKS_DIR}/{book}/analysis/agent_c_argument.json
```

### Agent D — 叙事修辞拆解

```
Task goal: "叙事修辞拆解"

预处理产物 + 全书文本同 Agent A。

只用框架分析和修辞三角做表达分析，禁止讨论概念定义/论证有效性。

步骤：
1. 框架分析——识别核心隐喻和认知框架，统计频次
2. 叙事语法——识别叙事弧（平衡→打破→冲突→转折→新平衡）
3. 修辞三角——每章 Ethos/Pathos/Logos 比例
4. 框架一致性检查——同一框架跨章使用是否稳定

输出 strict JSON，保存到 {BOOKS_DIR}/{book}/analysis/agent_d_narrative.json
```

## 阶段二：汇总验证

等四个 Agent 全部完成后：

```
Task goal: "汇总验证四维拆解产物"

四个产物路径:
- {BOOKS_DIR}/{book}/analysis/agent_a_skeleton.json
- {BOOKS_DIR}/{book}/analysis/agent_b_thought.json
- {BOOKS_DIR}/{book}/analysis/agent_c_argument.json
- {BOOKS_DIR}/{book}/analysis/agent_d_narrative.json

**只做对比/打分/标注，不修改原始产物。矛盾标注"需人工裁决"不自行仲裁。**

指标：
1. 覆盖率 = 被≥1维覆盖的术语 / 总术语数，目标 ≥ 90%
2. 交叉一致性 = 1 - (矛盾数 / 对比总数)，目标 ≥ 0.85
3. 冗余度检测，目标 ≤ 20%
4. 交叉验证增强——被≥2维独立验证的发现，置信度提升
5. 矛盾标注——不抹平

输出到 {BOOKS_DIR}/{book}/analysis/summary_verification.json
```

## 验证

全部六份 JSON 生成后，先运行产物验证器（Phase 2）：
```bash
python 4d_pipeline/validate_analysis.py {BOOKS_DIR}/{book}/analysis --write-manifest
```
验证器检查每份 JSON 文件的完整性和可解析性，生成 `analysis_manifest.json`。

然后用 preload_analysis.py 检查预读摘要：
```bash
python deepread/scripts/preload_analysis.py --book "{book}" --mode compact
```
