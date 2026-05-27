# DeepRead 开发日志

> 从个人 Claude Code Skill 到独立多后端 Agent 的完整演进

---

## 更新日志

### 2026-05-28 — v2.5.3 EPUB 容错解析增强

| 更新内容 | 说明 |
|------|------|
| 中文数字章节 | 支持 `第一章`、`第七章`、`一百零二章` 等目录识别 |
| 损坏资源容错 | `ebooklib` 解压失败时进入 zip 文本模式，跳过损坏图片/字体等非文本资源 |
| 多级目录兜底 | 目录解析顺序：NCX → EPUB3 `nav.xhtml` → OPF spine → 正文文件自动合成 |
| 路径兼容 | 支持 URL 解码、OPF 相对路径、basename 匹配、子目录递归找书、`.EPUB` 大小写 |
| 无章节前缀 | 目录标题不含“第几章”时，根据目录顺序自动编号 |
| 测试覆盖 | `test_extract_epub.py` 扩展至 11 个测试；全量 `100 passed` |

### 2026-05-28 — v2.5.1 历史脉络模式

| 更新内容 | 说明 |
|------|------|
| 新增阅读模式 | `historical_context` 历史脉络模式：时间线→人物关系→关键转折→制度背景→现实镜鉴 |
| Trial 可用 | Trial 体验版开放历史脉络模式，适合朋友试读《明朝那些事儿》这类历史叙事书 |
| 自动建议 | `明朝那些事儿`、`历史`、`王朝`、`传记`、`朱元璋` 等关键词可命中历史脉络模式 |
| 质量检查 | `note_quality.py` 增加历史模式检查：时间线/事件顺序、关键转折/制度背景、个人判断/现实镜鉴 |
| Skill 同步 | `skill/references/reading-modes.md` 增加历史脉络模式说明 |

### 2026-05-28 — v2.5 阅读模式接入 Agent

| 更新内容 | 说明 |
|------|------|
| `scripts/reading_modes.py` | 新增 140 行集中模式定义：8 种模式 + suggest/list/get/allowed + 快速名称表 + mode_hint_text |
| `cli.py` 重构 | 删除内联 READING_MODES dict（-90 行），改为 import 委托 |
| `learning_contract.py` | default_contract 增加 profile/book_type/reading_mode/mode_reason 字段；init 支持新参数 |
| `agent.py` 新工具 | `reading_mode` 工具（suggest/show/set/list）+ 系统提示注入模式判断规则 |
| `note_quality.py` | 模式感知检查：考试缺自测→WARN / 方法缺行动→WARN / 命题缺立场→WARN |
| Skill 同步 | 新增 `skill/references/reading-modes.md`，同步到 Claude Code skill 目录 |
| 不变部分 | concept_deep_read 保持四阶段流程不退；旧契约缺字段默认 concept_deep_read；personal 额外 4 模式可识别可契约 |

### 2026-05-28 — v2.4.1 收口版本

| 更新内容 | 说明 |
|------|------|
| 旧配置兼容 | 无 profile.name 自动识别为 personal，doctor 给出 1 WARN + 迁移提示 |
| concepts report 双源 | 同时统计用户 vault 概念卡 + Trial 基础包，Trial 用户无 Obsidian 也能看到基础包状态 |
| CLI 编码统一 | `sys.stdout.reconfigure(encoding='utf-8')` 解决 GBK 终端中文乱码 |
| doctor profile 检查 | 新增 Profile 健康项：Trial 检查基础包可用性、Personal 检查 LLM-Wiki 目录 |
| README 升级说明 | v2.4.1 旧用户无需重新初始化 |

### 2026-05-28 — v2.4 单仓库双发行形态 + IM-first + 概念卡体系

| 更新内容 | 说明 |
|------|------|
| P1 Profile 分发 | `profiles/trial/` + `profiles/personal/` 两套配置；`init.py --profile` + `install.ps1 -Profile` |
| P2 IM-first | `docs/手机端使用指南.md`；Trial 默认飞书入口、低依赖、不强制 Obsidian/Wiki |
| P3 阅读模式 CLI | `cli.py modes list/suggest/show`；8 种模式，Trial 开放 4 种；《被讨厌的勇气》→命题辨析，《一级建造师》→考试掌握 |
| P4 Web 运维页 | `/setup` `/modes` `/concepts` 三个页面 + API；定位为控制台非学习入口 |
| P5 概念卡基础包 | `profiles/trial/concepts/` 20 张卡（认知10+学习5+思维3+系统2）；`search_vault` 两级索引（用户卡优先→Trial 包 fallback） |
| Bot 管理 | `cli.py bot status/start/stop/restart`；Web API `/api/bot/*` |
| Doctor 增强 | 28→30 项检查；`--deep` 模式（LLM 连通性/飞书 CLI/笔记质量抽样） |
| 笔记质量检查器 | `scripts/note_quality.py`；`cli.py quality <path> [--json]`；Web 笔记详情页一键检查 |
| 概念卡别名 | `search_vault.load_concept_index()` 扫描 aliases/alias/别名；正文双链支持 `[[光环效应\|晕轮效应]]` |
| 安装脚本 | `install.ps1` / `start.ps1` / `start-bot.ps1`；新手一键部署 |

### 2026-05-27 — v2.3 语义链接 + Web 控制台

| 更新内容 | 说明 |
|------|------|
| Web 控制台 | FastAPI `server.py`，8 个页面模板；`templates/dashboard.html` 工作台首页 |
| 混合检索 | `search_vault.py` 轻量语义扩展 + Wiki 路由 + 虚拟概念候选 |
| 智能双链 | `write_note.py compile` 正文只链接概念卡，弱相关放入延伸阅读；链接类型优先级排序 |
| 渐进式写入 | create(阶段1)→update(阶段2)→append(阶段3)→finalize+compile(阶段4) |
| 工作台首页 | 4 功能入口卡 + 当前阅读任务 + 知识积累 + 系统状态 + 过滤后最近活动 |
| 飞书 Bot 增强 | 锁文件元数据（cmd/reply/notes_dir）；消息去重+命令白名单完成 |

### 2026-05-27 16:41:31 +08:00 — Obsidian 正文概念链接与排版优化

| 更新内容 | 说明 |
|------|------|
| 正文概念链接优先 | `我的理解` / `让我想到` 的正文内链只链接 `概念（抽象概念）` 下的概念卡，例如 `[[光环效应]]` |
| 延伸阅读边界 | 读书笔记、我的思考、Wiki 枢纽不再进入正文内链，统一放入 `### 相关旧笔记 / 延伸阅读` |
| 概念卡召回增强 | `search_vault.py` 提高 `concept_card` 权重，`suggest_links` 扩大候选池，避免已有概念卡被读书笔记挤掉 |
| 重点句加粗 | `write_note.py compile` 会给 `我的理解` / `让我想到` 中一级 bullet 的第一句适度加粗，作为 Obsidian 回看锚点 |
| 规则同步 | `skill/references/note-format.md` 明确“概念卡进正文，旧笔记/我的思考进延伸阅读”的 Obsidian 链接规则，并同步到 Claude Code skill |
| 测试覆盖 | 补充正文只链接概念卡、非概念候选进入延伸阅读、重点句加粗的回归测试 |

### 2026-05-26 23:27:08 +08:00 — 章节学习契约与两端对齐

| 更新内容 | 说明 |
|------|------|
| 新增学习契约层 | 新增 `scripts/learning_contract.py`，支持 `init/show/update/check/report`，用于记录 A/B/C/D 知识地图、理解证据、阶段事件和笔记沉淀 |
| Agent 工具接入 | `agent.py` 新增 `learning_contract` 工具；系统提示加载 `learning-contract.md`，阶段切换前可检查学习契约 |
| 多用户隔离 | Agent 调用 `state.py` 和 `learning_contract.py` 时携带 `user_id`，飞书多用户不会共用同一份契约 |
| CLI 入口 | `cli.py` 新增 `contract` 命令，并把 `learning_contract.py` 纳入 doctor 脚本自检 |
| Skill 规则同步 | 新增 `skill/references/learning-contract.md`，更新 `SKILL.md` 与 `dialogue-flow.md`，并同步到 `C:\Users\唐帅\.claude\skills\deep-read` |
| 阶段通过标准 | 阶段1要求 A 类核心点 80% 覆盖；阶段2要求深挖、边界/反例、应用追问；阶段3要求旧笔记关联和个人联想；阶段4输出覆盖报告 |
| 测试覆盖 | 新增 `tests/test_learning_contract.py`；补充 Agent 工具参数顺序回归测试 |
| 验证结果 | `python -m pytest -q`：57/57 全绿 |

---

## 起点

用户唐帅有一套个人深度阅读工作流：

```
手机微信 → IM桥接 → Claude Code → deep-read Skill → Obsidian 笔记
```

核心是 `SKILL.md`（387 行）——一个费曼学习法 + 苏格拉底追问 + 强制联想的四阶段阅读教练。问题是所有路径硬编码、EPUB 解析靠 AI 手搓、只有自己能跑。

---

## 阶段 1：个人可移植版（v1.0）

**目标**：换一台电脑也能部署

| 产出 | 说明 |
|------|------|
| `config.yaml` | 所有路径/模板/集成开关配置化 |
| `extract_epub.py` | EPUB → 结构化 JSON，38 章全识别，小节拆分 |
| `state.py` | 5 阶段 FSM，状态持久化 + 归档 |
| `write_note.py` | 渐进式笔记写入（create→update→append→finalize） |
| `search_vault.py` | Obsidian 全文搜索 + wikilink 反向引用 |
| `init.py` | 交互式初始化向导 |

**SKILL.md**：387 行 → 120 行 + 6 个 reference 文件

---

## 阶段 2：朋友可用版（v1.5）

**目标**：别人能装能用

| 产出 | 说明 |
|------|------|
| 跨平台兼容 | Win/Mac/Linux 默认路径适配 |
| `requirements.txt` | 5 个 pip 依赖声明 |
| README | 安装指南 + FAQ |
| 4 种笔记模板 | obsidian 三段式 / cornell / zettelkasten / plain |
| `cli.py` | 统一 CLI 入口（progress/review/think/search/doctor/read） |
| `feishu_bot.py` | 飞书 Bot 适配器骨架 |

---

## 阶段 3：工程硬化

**目标**：从"自己能跑"到"敢发给朋友"

| 修复 | 说明 |
|------|------|
| Windows 子进程编码 | `PYTHONIOENCODING=utf-8` + `errors='replace'` |
| `cli.py doctor` | 18 项健康检查（依赖/路径/EPUB/模板/脚本） |
| `config.example.yaml` | 配置样例，隔离个人信息 |
| `.gitignore` | state/logs/sessions 不入库 |
| 统一错误格式 | `{"ok":false,"error_code":"...","message":"...","hint":"..."}` |
| 状态历史时间戳 | `2026-05-25T173152.json` 替代日期覆盖 |
| 笔记备份 + 冲突检测 | `.bak` 文件 + mtime 检查防同步覆盖 |

---

## 阶段 4：独立 Agent（v2.0）

**目标**：不依赖 Claude Code，只需要 Python + API Key

| 产出 | 说明 |
|------|------|
| `agent.py` | 多后端 Agent 运行时（DeepSeek/Anthropic/OpenAI） |
| 自动检测后端 | CLI `--provider` > config.yaml > 环境变量 |
| 5 个工具定义 | extract_epub / write_note / read_state / update_state / search_vault |
| 会话管理 | 保存/恢复/用户映射/崩溃恢复 |
| `skill/` 自包含 | 教练提示词不再依赖 `~/.claude/` 外部路径 |
| NDJSON 日志 | 每次 API 调用/工具调用/耗时/错误全记录 |

**主入口切换**：

```
过去: Claude Code + Skill 是主入口
现在: agent.py 是主入口，Claude Code 是调试入口
```

---

## 阶段 5：飞书入口闭环（v2.1）

**目标**：手机飞书 → Agent → Obsidian 笔记

| 产出 | 说明 |
|------|------|
| `process_message()` | agent.py 可编程接口（供飞书/微信/Web 调用） |
| 用户会话映射 | 同一用户跨进程恢复同一会话 |
| `feishu_bot.py listen` | lark-cli 事件监听 + 自动回复 |
| 防御性事件解析 | 兼容扁平和嵌套两种 JSON 结构 |
| DeepSeek thinking 修复 | 默认关闭 thinking，避免 `reasoning_content` 报错 |
| 飞书 Markdown 清洗 | 去除纯文本无意义的 `**` `*` `` ` `` 等标记 |
| 消息去重 | message_id 缓存防重复投递 |
| 命令白名单 | 打招呼秒回/精读走 Agent/未知命令提示 |

---

## 阶段 6：收口与验证（v2.1.3）

| 产出 | 说明 |
|------|------|
| `ARCHITECTURE.md` | v2.0 架构文档（三条链路图） |
| `ISSUES.md` | 问题追踪模板 |
| `RUNNING_NOTES.md` | 7 天使用记录模板 |
| `新手指南-飞书注册与部署.md` | 30 分钟从零部署 |
| Git 初始化 | 9 个 commit，38 个文件，~5000 行 |
| 测试集 | 30 个测试全绿 |
| Doctor | 18 项检查全通过 |

---

## 最终架构 (v2.5)

```
手机飞书 ──→ feishu_bot.py listen --reply
                 │
                 ▼
           agent.process_message()
                 │
         ┌───────┼───────┐
         ▼       ▼       ▼
    DeepSeek  Anthropic  OpenAI
         │
         ├─→ reading_modes.py ──→ 模式判断/切换
         ├─→ learning_contract.py ──→ 学习契约（含模式）
         ├─→ extract_epub.py ──→ EPUB → JSON
         ├─→ write_note.py  ──→ Obsidian 笔记
         ├─→ state.py       ──→ 阅读状态
         ├─→ search_vault.py ──→ 概念卡 + 别名 + 旧笔记
         └─→ note_quality.py ──→ 质量检查（模式感知）

Web 控制台:
  server.py ──→ /setup /modes /concepts /doctor /sessions /notes /compare

终端精读:
  python agent.py

发行形态:
  install.ps1 -Profile trial    # 体验版：IM-first + 4 模式 + 基础概念包
  install.ps1 -Profile personal # 完整版：Obsidian + Wiki + 8 模式 + 全链路
```

## 关键决策记录

| 决策 | 选择 | 原因 |
|------|------|------|
| 主入口 | agent.py（替代 Claude Code） | 独立部署，不需要 Claude Code |
| 多后端 | 抽象 LLMProvider | 用户自由选择模型，自动检测 |
| 默认后端 | DeepSeek | 国内直连，便宜 |
| 默认模型 | deepseek-v4-pro | 默认启用 auto thinking，深任务使用 Pro 推理 |
| 飞书集成 | process_message() 直调 | 保持会话连续性 |
| Skill 存放 | deepread/skill/ 自包含 | 不依赖外部路径 |
| 发行形态 | 单仓库双 profile | 不拆两个 repo，配置文件隔离 |
| 阅读模式 | 契约控制参数 | 模式影响追问方向，不推翻四阶段 |
| 概念卡 | 用户卡 > Trial 包 > 不链接 | 不静默污染用户 Obsidian |
| 日志格式 | NDJSON | 可追加、可 grep、可结构化 |
| 笔记写入 | 渐进式（非一次性） | 每阶段产出即写入 |
| 错误格式 | 统一 JSON | `{"ok":false,"error_code":"...","hint":"..."}` |
| Web 定位 | 运维控制台，非学习入口 | IM 是主入口，Obsidian 是沉淀层 |

## 当前版本

**v2.5** — 阅读模式接入 Agent。76 测试全绿，30 doctor 检查通过。

8 种阅读模式 / 双发行形态 / 飞书 Bot / Web 控制台 / 20 张基础概念卡 / 笔记质量检查器。

下一步：朋友试用验证，记录体验到 RUNNING_NOTES.md。
