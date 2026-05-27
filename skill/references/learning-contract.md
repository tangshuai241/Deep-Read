# 章节学习契约

学习契约是 DeepRead 的外部教学控制层。模型负责怎么问，契约负责问什么、覆盖到哪、何时可以进入下一阶段。

## 使用时机

- 阶段 0 提取原文后，必须建立或刷新契约：
  - `python scripts/learning_contract.py init --book ... --chapter ... --section ... --goal ...`
  - 同时给出 A/B/C/D 知识地图；如果一时无法完整判断，先填 A 类核心点和少量 B/D 点。
- 每轮用户回答后，必须把真实理解证据写回契约：
  - `update --point ... --status covered|unclear|passed --evidence ...`
- 阶段切换前，必须检查契约：
  - `check --stage feynman|socratic|associate|wrapup`
- 阶段 4 收尾前，必须生成报告：
  - `report --json`

## 知识点分级

- `A_core`：本节必须掌握的核心机制。阶段 1/2 必须覆盖，不能只靠模型总结替用户通过。
- `B_important`：重要但可抽样讨论的概念、表现、对比。
- `C_evidence`：实验、例子、数据、作者论据，用来支撑理解，不强制逐条展开。
- `D_application`：现实应用、个人经验、反例、边界条件，阶段 2/3 至少触发 1-2 个。

## 阶段通过标准

### 阶段 1：费曼输出

- A 类核心点至少覆盖 80%。
- 已覆盖的 A 点必须有用户自己的解释证据。
- 用户只复述术语、照搬原文、只说“我懂了”，不能算通过。

### 阶段 2：苏格拉底深化

- 至少深挖 2 个 A/B 点，并标记为 `passed`。
- 至少记录 1 个 `boundary_or_counterexample` 事件。
- 至少记录 1 个 `application_probe` 事件。
- 如果用户暴露明显误解，相关知识点标记为 `unclear`，不要推进。

### 阶段 3：强制联想

- 至少记录 1 个 `old_note_connection` 事件。
- 至少记录 1 个 `personal_association` 事件。
- 个人联想必须写入 `让我想到`，并用 `deposit=associations` 记录已沉淀。
- 自动旧笔记链接不能替代用户自己的真实联想。

### 阶段 4：收尾

- 调用 `report` 生成覆盖报告。
- 未覆盖 A 点进入 `待探索`，不能在最终笔记中假装已经掌握。
- 报告用于辅助 `write_note.py finalize/compile`，但契约不直接写 Wiki。

## 两端对齐原则

Claude Code skill 和飞书 Agent 不需要逐字同问，但必须共享同一份契约：

- 同一章节/小节的 A/B/C/D 知识地图应一致。
- 阶段通过条件一致。
- 用户个人例子的沉淀规则一致。
- 允许不同模型用不同语气、顺序和追问方式。

## 与 Wiki 的边界

学习契约只属于 DeepRead 学习控制层。它可以读取 LLM-Wiki 成果来辅助联想，但不执行 Wiki 更新。

阶段 4 如需更新 Wiki，只生成建议；真正更新交给独立 LLM-Wiki 维护流程。
