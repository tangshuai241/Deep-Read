# 四阶段对话流程（详细版）

## 阶段 0：初始化

1. 解析用户指定的阅读范围（哪本书、哪章、哪节）
2. 运行 `extract_epub.py --chapter N --json` 提取原文
3. 读取 `reading-notes.md` 获取进度
4. 如有微信读书 API 且启用：调 `/book/getprogress` 补充进度
5. 首次读某书：确认书名/作者/学科 → 写入 reading-notes.md
6. 确认目标："理解 / 应用 / 批判 / 教学？"
7. 告知字数、核心议题梗概（一句话）
8. 超过 8000 字 → 提示"这章较长（约X字），建议分次读。要拆开还是整章一起？"
9. 建立学习契约：
   - 从原文中提取 A/B/C/D 知识地图
   - `A_core` 为本节必须掌握的核心机制
   - `B_important` 为重要概念/表现/对比
   - `C_evidence` 为实验、例子、数据、作者论据
   - `D_application` 为现实应用、个人经验、反例、边界条件
   - 运行 `learning_contract.py init --book ... --chapter ... --section ... --goal ... --A_core ... --B_important ... --C_evidence ... --D_application ...`
10. 更新状态到 `init` → 询问是否进入阶段1

## 阶段 1：费曼输出

**目标**：用户用大白话复述核心观点，直到清晰无术语。

- "请用最简单的话，把这节的核心观点讲给我听"
- 检测：术语不解释 / 逻辑跳跃 / 遗漏前提 → 追问
- "你提到'XX'，它到底是什么？能否完全不使用这个词，重新解释一遍？"
- 至少追问两轮再判断是否清晰；每轮后运行 `learning_contract.py update --point ... --status covered|unclear --evidence ...`
- 阶段切换前运行 `learning_contract.py check --stage feynman`
- 若 A 类核心点不足 80% 或缺少用户自己的解释证据，不进入阶段2，继续追问缺口
- **→ 判断清晰后**：运行 `write_note.py create` 创建笔记草稿（阶段1结束）
- 更新状态到 `feynman` → 问："理解到位了，进入深化讨论还是继续追问？"

## 阶段 2：苏格拉底式深化

**目标**：触及理解的边界。

从以下角度选 1-2 个发起提问：

**基础追问**：
- **前提批判**："这个观点成立需要什么前提？什么情况下会失效？"
- **反例寻找**："能想象一个矛盾的例子吗？"
- **边界追问**："能用到什么领域？绝对不能用到哪？"
- **推理链还原**："作者怎么得出这个结论？跳过什么步骤？"

**穿透追问**（基础追问不够深时使用）：
- **削弱型追问**："作者的结论依赖哪些没明说的隐含前提？如果要削弱这个结论，哪个前提最容易被攻破？"
- **概念辨析**："文中用的类比主要映射的是属性、动作还是功能？这个类比在哪一步会因为属性不匹配而失效？"

**推理漏洞检测**（自动应用，不直接指出，用 Socratic 方式追问）：
- 偷换概念 / 因果倒置 / 相关性≈因果性 / 幸存者偏差
- 不可证伪的陈述 / 模糊词遮蔽逻辑跳跃

**→ 触及边界后**：运行 `write_note.py update --section 我的理解` 覆盖更新理解

阶段2契约要求：
- 深挖过的 A/B 点用 `learning_contract.py update --point ... --status passed --evidence ...` 标记
- 完成边界或反例追问后记录 `--event boundary_or_counterexample`
- 完成现实应用追问后记录 `--event application_probe`
- 阶段切换前运行 `learning_contract.py check --stage socratic`；不通过就继续补对应缺口

**必须同时沉淀个人联想**：阶段2里只要用户给出法律、工程、投资、工作、生活等个人化例子，且例子不是单纯复述原文，就必须运行 `write_note.py append --section 让我想到` 追加为可复用联想。不要把这类例子只压缩进 `我的理解`。例如：
- 法律中的罪行强度 vs 惩罚强度 → 记入 `让我想到`
- 工程现场里系统1何时是资产/负债 → 记入 `让我想到`
- 新人第一次进入工地建立判断基准线 → 记入 `让我想到`

更新状态到 `socratic` → 问："继续深化还是进入联想阶段？"

## 阶段 3：强制联想

**目标**：将新知识嵌入已有知识网络。

**先搜后问**：
1. 运行 `search_vault.py --query "当前概念 + 用户回答 + 章节摘要" --mode hybrid --scope core --include-wiki` 搜索核心知识库和 LLM-Wiki
2. 先看 Wiki 枢纽和概念卡，再看读书笔记和“我的思考”，按“核心机制/具体表现/应对方法/个人经验”挑 1-3 个高质量候选
3. 引用具体旧笔记："你在《XXX》的「YYY」里写过：'……'。这和现在这段内容有什么关系？"
4. 生活联想："用你本周的真实经历，重新解读这个道理"
5. 如果关键词未命中但语义相关，仍要使用候选；只有混合检索也无结果时，才说"没找到相关旧笔记，你自己能联想到什么？"

**→ 每有 1 条有价值的联想**：运行 `write_note.py append --section 让我想到`
同时更新契约：
- 关联旧笔记后记录 `learning_contract.py update --event old_note_connection --evidence ...`
- 用户给出现实经验后记录 `learning_contract.py update --event personal_association --evidence ...`
- 写入 `让我想到` 后记录 `learning_contract.py update --deposit associations --evidence ...`
- 阶段切换前运行 `learning_contract.py check --stage associate`

联想质量要求：
- 优先保留用户原始场景和关键表述，不要只写抽象结论
- 每条联想应有小标题或清晰第一句，例如“工程现场中的系统1资产与负债”
- 自动旧笔记链接只能作为补充，不能替代用户自己的联想内容

更新状态到 `associate` → 问："联想差不多了，要收尾还是继续？"

## 阶段 4：收尾

1. 运行 `learning_contract.py check --stage wrapup`；未通过时说明缺口，让用户决定补学或带着缺口收尾
2. 运行 `learning_contract.py report --json` 生成覆盖报告
3. 将未覆盖 A 类核心点写入 `待探索`，不要假装已经掌握；每条必须归入 `【理解缺口】`、`【应用缺口】`、`【连接缺口】` 三类之一
4. 运行 `write_note.py finalize` 补全 frontmatter + 待探索
5. 运行 `search_vault.py --suggest-links --note-path ... --scope core --include-wiki` 查看候选链接
6. 运行 `write_note.py compile` 整理整篇笔记为 Obsidian 三段式成品，并自动插入少而准的正文链接和延伸链接
7. 生成 LLM-Wiki 增量编译建议（不静默改 Wiki；DeepRead 不直接执行 Wiki 更新，真正更新交给独立 Wiki 维护流程）
8. 更新 reading-notes.md：进度、待探索问题
9. 每完成一章：更新认知画像
10. 告知用户笔记路径和契约覆盖报告摘要
11. 更新状态到 `idle`
