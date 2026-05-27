# DeepRead 架构与工作流

> **版本**：v2.5  
> **日期**：2026-05-27  
> **定位**：本地优先、IM-first 的 AI 深度阅读教练。手机 IM 负责学习对话，Obsidian/Markdown 负责沉淀，Web 负责运维控制。  
> **核心原则**：单仓库双发行形态、本地优先、配置隔离、IM 主入口、Obsidian 兼容、Wiki/概念卡增强、Web 不替代学习对话。

---

## 1. 当前产品形态

DeepRead 不是单纯的网页阅读器，也不是只给 Claude Code 使用的 skill。当前主形态是：

```text
手机飞书 / 未来其他 IM
  -> DeepRead Agent 对话引导
  -> 阅读模式判断
  -> 学习契约控制路线
  -> Obsidian / Markdown 笔记沉淀
  -> Web 控制台做状态、配置、质量检查
```

### 两种发行形态

项目保持一个代码库，不拆成两个 repo，通过 profile 区分使用形态。

| Profile | 面向对象 | 默认能力 | 边界 |
|---|---|---|---|
| `trial` | 朋友、同学、新手试用 | IM-first、4 种常用阅读模式、Trial 基础概念卡包、本地 Markdown 输出 | 不强制 Obsidian、LLM-Wiki、个人知识库 |
| `personal` | 个人完整版 | 飞书 Bot、Obsidian、LLM-Wiki、用户概念卡、认知画像、8 种阅读模式 | 保留完整增强链路 |

旧配置没有 `profile.name` 时，系统默认按 `personal` 处理，并由 `doctor` 给出迁移提示。

---

## 2. 总体架构

```text
┌─────────────────────────────────────────────────────────────┐
│                         入口层                              │
│                                                             │
│  手机飞书 Bot          CLI / PowerShell        Claude Code   │
│  adapters/feishu_bot   cli.py / agent.py       skill 调试入口 │
│                                                             │
└───────────────┬─────────────────────┬───────────────────────┘
                │                     │
                ▼                     ▼
┌─────────────────────────────────────────────────────────────┐
│                      Agent 运行时                            │
│                                                             │
│  agent.py                                                    │
│  - 多后端 LLM: DeepSeek / Anthropic / OpenAI compatible      │
│  - 会话保存与恢复                                             │
│  - 工具调用调度                                               │
│  - Thinking auto 路由                                         │
│  - 阅读模式判断与切换                                         │
└───────────────┬─────────────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────────────┐
│                        控制层                               │
│                                                             │
│  reading_modes.py       learning_contract.py                 │
│  阅读模式定义/建议       学习契约/知识地图/阶段检查             │
│                                                             │
│  state.py               note_quality.py                      │
│  阅读状态                笔记质量检查                         │
└───────────────┬─────────────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────────────┐
│                        工具层                               │
│                                                             │
│  extract_epub.py       write_note.py       search_vault.py   │
│  EPUB 解析            笔记写入/编译       Vault/Wiki/概念搜索 │
└───────────────┬─────────────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────────────┐
│                        数据层                               │
│                                                             │
│  config.yaml             state/                logs/         │
│  profile 配置            会话/契约/进度        运行日志       │
│                                                             │
│  profiles/trial/         Obsidian Vault 外部目录              │
│  体验版配置与基础概念卡    读书笔记/概念卡/我的思考/Wiki        │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                     Web 控制台层                             │
│                                                             │
│  server.py                                                  │
│  /setup /modes /concepts /doctor /sessions /notes /compare  │
│  只负责状态、运维、质量检查，不作为主学习界面                  │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. 核心链路

### 3.1 手机 IM 主链路

```text
用户手机发消息
  -> adapters/feishu_bot.py listen --reply
  -> 去重、轻量命令判断、用户会话映射
  -> agent.process_message(user_text)
  -> Agent 判断阅读模式 / 读取学习契约 / 调工具
  -> 返回适合手机阅读的短回复
  -> lark-cli im send 发送回飞书
```

Bot 进程由 CLI 管理：

```powershell
python cli.py bot status
python cli.py bot start --reply
python cli.py bot stop
python cli.py bot restart --reply
```

### 3.2 阅读模式链路

```text
用户说“我想读《被讨厌的勇气》”
  -> reading_mode suggest
  -> scripts/reading_modes.py
  -> 返回 proposition_dialogue
  -> learning_contract init 写入 reading_mode/book_type/mode_reason
  -> Agent 按命题辨析方式追问
```

当前 8 种模式：

| 模式 | key | Trial | 用途 |
|---|---|:--:|---|
| 概念精读 | `concept_deep_read` | yes | 心理学、认知科学、思想概念密集书 |
| 命题辨析 | `proposition_dialogue` | yes | 《被讨厌的勇气》、哲学、观点型书 |
| 方法转化 | `method_conversion` | yes | 工具书、方法论、行动指南 |
| 考试掌握 | `exam_mastery` | yes | 一级建造师、职业资格、应试教材 |
| 教材推导 | `textbook_derivation` | no | 学术教材、公式推导、理论课程 |
| 规范检索 | `standard_lookup` | no | 法规、标准、合同、工程规范 |
| 案例复盘 | `case_review` | no | 商业案例、工程案例、事故复盘 |
| 文学体验 | `literature_experience` | no | 小说、散文、传记、纪实文学 |

CLI 入口：

```powershell
python cli.py modes list
python cli.py modes suggest "被讨厌的勇气"
python cli.py modes show exam_mastery
```

### 3.3 学习契约链路

学习契约是 Agent 的学习路线控制层，记录当前章节的范围、知识地图、阶段事件、笔记沉淀与阅读模式。

```text
阶段 0
  -> learning_contract init
  -> 写入 book/chapter/section/goal/profile/book_type/reading_mode

用户回答后
  -> learning_contract update
  -> 更新 A/B/C/D 知识点状态和证据

阶段切换前
  -> learning_contract check
  -> 未达标则继续追问

收尾时
  -> learning_contract report
  -> 提供已掌握、未覆盖、待探索、个人联想
```

契约文件位置：

```text
state/<user>/learning_contract.json
```

核心字段：

```json
{
  "profile": "personal",
  "scope": {
    "book": "思考快与慢",
    "chapter": "第7章",
    "section": "光环效应与群体的智慧",
    "goal": "理解"
  },
  "book_type": "概念思想型",
  "reading_mode": "concept_deep_read",
  "mode_reason": "概念密集，适合概念精读",
  "knowledge_map": {
    "A_core": [],
    "B_important": [],
    "C_evidence": [],
    "D_application": []
  }
}
```

### 3.4 笔记生成链路

```text
extract_epub.py
  -> 提取章节/小节

write_note.py create/update/append/finalize
  -> 分阶段写入草稿

search_vault.py --suggest-links
  -> 候选正文概念链接 + 延伸链接

write_note.py compile
  -> 生成稳定 Obsidian 三段式成品

note_quality.py
  -> 检查格式、链接、待探索、模式特定缺口
```

当前笔记规则：

- 正文 `我的理解` / `让我想到` 只给概念卡打双链。
- 读书笔记、我的思考、LLM-Wiki 枢纽进入“相关旧笔记 / 延伸阅读”。
- `待探索` 按价值分为理解缺口、应用缺口、连接缺口。
- `note_quality.py` 会根据 `reading_mode` 给出模式感知提示：
  - 考试模式缺自测题 -> WARN
  - 方法模式缺行动清单 -> WARN
  - 命题模式缺个人立场/反例 -> WARN

---

## 4. 组件职责

| 组件 | 文件/目录 | 职责 |
|---|---|---|
| Agent 运行时 | `agent.py` | LLM 对话循环、工具调用、会话保存、Thinking 路由、阅读模式工具 |
| 飞书入口 | `adapters/feishu_bot.py` | 事件监听、消息去重、会话映射、自动回复 |
| CLI | `cli.py` | doctor、bot、quality、concepts、profile、modes、contract 等统一入口 |
| Web 控制台 | `server.py` + `templates/` | 状态查看、Bot 管理、doctor、quality、概念卡报告、模式说明 |
| 阅读模式 | `scripts/reading_modes.py` | 8 种模式定义、Trial/Personal 过滤、模式建议 |
| 学习契约 | `scripts/learning_contract.py` | A/B/C/D 知识地图、阶段检查、模式字段、覆盖报告 |
| EPUB 解析 | `scripts/extract_epub.py` | EPUB 章节和小节提取 |
| 笔记写入 | `scripts/write_note.py` | create/update/append/finalize/compile |
| Vault 搜索 | `scripts/search_vault.py` | 读书笔记、概念卡、我的思考、LLM-Wiki 混合搜索 |
| 笔记质检 | `scripts/note_quality.py` | Obsidian 笔记质量、链接、模式特定检查 |
| Skill | `skill/` | Claude Code 调试入口和 Agent 系统提示参考 |
| Profile | `profiles/` | trial/personal 两套配置与 Trial 概念卡基础包 |

---

## 5. 数据与目录

```text
deepread/
├── agent.py
├── cli.py
├── init.py
├── server.py
├── install.ps1
├── start.ps1
├── start-bot.ps1
├── config.yaml
├── profiles/
│   ├── trial/
│   │   ├── config.example.yaml
│   │   ├── README.md
│   │   └── concepts/              # 20 张基础概念卡
│   └── personal/
│       ├── config.example.yaml
│       └── README.md
├── adapters/
│   └── feishu_bot.py
├── scripts/
│   ├── extract_epub.py
│   ├── write_note.py
│   ├── search_vault.py
│   ├── state.py
│   ├── learning_contract.py
│   ├── reading_modes.py
│   ├── note_quality.py
│   └── logger.py
├── skill/
│   ├── SKILL.md
│   └── references/
│       ├── dialogue-flow.md
│       ├── note-format.md
│       ├── learning-contract.md
│       └── reading-modes.md
├── templates/
├── static/
├── state/
│   ├── default/
│   ├── sessions/
│   └── feishu_bot.listen.lock
└── logs/
```

外部 Obsidian vault 建议结构：

```text
知识库/
├── 读书/
│   └── 笔记/
├── 概念（抽象概念）/
├── 我的思考/
└── 读书/笔记/📚 LLM-Wiki 整合/
```

---

## 6. 概念卡与链接架构

DeepRead 使用两级概念卡索引：

```text
用户 Obsidian 概念卡
  优先级高
  路径: vault_dir/概念（抽象概念）/**/*.md

Trial 基础概念卡
  fallback
  路径: profiles/trial/concepts/*.md
```

链接规则：

- 主名出现：`光环效应` -> `[[光环效应]]`
- 别名出现：`晕轮效应` -> `[[光环效应|晕轮效应]]`
- 每个概念每篇笔记正文最多链接一次。
- 不链接读书笔记、我的思考、Wiki 枢纽到正文。
- 找不到概念卡时不自动创建，只由质量检查或 concepts 命令提示。

概念卡 CLI：

```powershell
python cli.py concepts scan
python cli.py concepts aliases
python cli.py concepts missing
python cli.py concepts report
```

---

## 7. Web 控制台

Web 控制台定位为运维面板，不是学习主界面。

```text
http://127.0.0.1:8765/
```

主要页面：

| 页面 | 作用 |
|---|---|
| `/` | 当前阅读、系统状态、最近活动 |
| `/setup` | profile、LLM、Obsidian、Wiki、增强模块状态 |
| `/modes` | 阅读模式列表与说明 |
| `/concepts` | 概念卡数量、别名、覆盖率 |
| `/doctor` | 普通/深度健康检查 |
| `/sessions` | Agent 和 Claude Code 会话 |
| `/notes` | 笔记浏览与质量检查 |
| `/compare` | Claude Code 与飞书 Agent 笔记对比 |

主要 API：

```text
GET  /api/profile
GET  /api/modes
GET  /api/concepts/report
GET  /api/doctor?deep=1
GET  /api/bot/status
POST /api/bot/start
POST /api/bot/stop
POST /api/bot/restart
GET  /api/quality?path=<note_path>
```

---

## 8. 配置与安装

### Profile 初始化

```powershell
python init.py --profile trial
python init.py --profile personal

.\install.ps1 -Profile trial
.\install.ps1 -Profile personal
```

### 推荐启动

```powershell
.\start.ps1
.\start-bot.ps1
```

### 健康检查

```powershell
python cli.py doctor
python cli.py doctor --deep
```

`doctor` 检查依赖、路径、LLM、飞书 CLI、Bot 锁文件、Obsidian 目录、概念卡、profile、脚本完整性。`--deep` 额外检查 LLM 连通性、飞书 CLI 基础能力和笔记质量抽样。

---

## 9. 后端模型与 Thinking

支持后端：

| Provider | 默认模型 | API Key |
|---|---|---|
| DeepSeek | `deepseek-v4-pro` | `DEEPSEEK_API_KEY` |
| Anthropic | `claude-sonnet-4-6` | `ANTHROPIC_API_KEY` |
| OpenAI compatible | `gpt-4o` 或配置值 | `OPENAI_API_KEY` |

配置优先级：

```text
CLI 参数 > config.yaml llm.provider/model > provider 默认值
```

DeepSeek Thinking：

- `llm.thinking: auto` 推荐。
- 寒暄、进度、搜索等轻量消息关闭。
- 精读、批判、联想、总结等深任务开启。
- `reasoning_content` 仅用于 API 连续性，不展示给用户。

---

## 10. 成熟度与边界

### 已稳定

- 飞书 IM 对话闭环。
- Agent 独立运行，不依赖 Claude Code。
- 单仓库双 profile。
- Bot start/stop/status。
- Web 控制台运维入口。
- 笔记质量检查。
- 概念卡正文双链与 Trial 基础包 fallback。
- 阅读模式识别和契约写入。
- 76 项测试通过。

### 当前边界

- Web 不承担主学习界面。
- Trial 不强制 LLM-Wiki。
- 概念卡是增强资产，不要求所有书都概念化。
- 微信桥接未实现，只保留 IM 抽象与未来方向。
- Personal 额外 4 种模式已可识别和写入契约，深度阶段标准后续继续细化。

---

## 11. 关键决策记录

| 决策 | 当前选择 | 原因 |
|---|---|---|
| 项目形态 | 单仓库双 profile | 避免维护两套代码，同时隔离个人版和体验版 |
| 主学习入口 | 手机 IM | 语音输入方便，学习对话天然适合移动端 |
| Web 定位 | 运维控制台 | 避免把学习体验做重，保持状态可见和问题可查 |
| 笔记沉淀 | Obsidian/Markdown | 本地优先、可同步、双链生态成熟 |
| 知识增强 | 概念卡 + LLM-Wiki | 概念卡做正文强链接，Wiki 做路由和索引增强 |
| 阅读路线 | learning_contract | 让两端围绕同一知识地图和阶段标准推进 |
| 书籍适配 | reading_modes | 不同书籍不能硬套同一套概念精读流程 |
| Claude Code | 调试入口 | 保留 skill，但主运行时是 agent.py |

---

## 12. 后续方向

优先级建议：

1. 用真实书籍验证 4 个 Trial 模式：概念精读、命题辨析、方法转化、考试掌握。
2. 细化 Personal 额外模式：教材推导、规范检索、案例复盘、文学体验。
3. 增强语义搜索，提升旧笔记和“我的思考”的召回质量。
4. 做朋友试用包：样例书、样例 vault、最短 IM 使用脚本。
5. 持续扩充概念卡基础包，但保持少而准。
