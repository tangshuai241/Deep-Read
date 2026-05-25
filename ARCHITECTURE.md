# DeepRead 项目架构与工作流

> **版本**：v2.0 | **日期**：2026-05-25
> **定位**：面向 Obsidian 用户的本地优先 AI 深度阅读教练（独立 Agent 版）
> **原则**：配置化 > 硬编码、模块化 > 单文件、本地优先 > 云依赖、Markdown 优先 > 平台绑定

---

## 一、架构总图

```
                         ┌─────────────────────────────┐
                         │        外部入口层             │
                         │                              │
                         │  ┌──────────┐ ┌───────────┐ │
                         │  │ 飞书 Bot  │ │  微信桥接   │ │
                         │  │process_  │ │  (现有)    │ │
                         │  │message() │ │            │ │
                         │  └─────┬────┘ └─────┬─────┘ │
                         │        │             │       │
                         │  ┌─────┴─────────────┴─────┐ │
                         │  │    CLI (cli.py chat)     │ │
                         │  └──────────┬──────────────┘ │
                         └─────────────┼────────────────┘
                                       │
        ┌──────────────────────────────┼────────────────┐
        │                      主入口层                  │
        │                                               │
        │  ┌─────────────────────────────────────────┐  │
        │  │           agent.py                       │  │
        │  │  • 多后端 (DeepSeek/Anthropic/OpenAI)     │  │
        │  │  • 对话循环 + 工具调度                    │  │
        │  │  • 会话保存/恢复 (按用户映射)              │  │
        │  │  • 日志 + 崩溃恢复                        │  │
        │  └──────────────────┬──────────────────────┘  │
        │                     │                         │
        │  (Claude Code) ──→ 开发者调试入口（保留）      │
        └─────────────────────┼─────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────────┐
        │              AI 对话层（skill/）               │
        │                                               │
        │  ┌─────────────────────────────────────────┐  │
        │  │  SKILL.md (120行)                        │  │
        │  │  references/                             │  │
        │  │    ├─ dialogue-flow.md                    │  │
        │  │    ├─ note-format.md                      │  │
        │  │    ├─ fsm-spec.md                         │  │
        │  │    ├─ epub-parsing.md                     │  │
        │  │    ├─ cognition-profile.md                │  │
        │  │    └─ weread-api.md                       │  │
        │  └─────────────────────────────────────────┘  │
        │                                               │
        │  自包含于 deepread/skill/，不依赖外部路径       │
        └─────────────────────┬─────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────────┐
        │              工具脚本层                        │
        │                                               │
        │  ┌──────────────┐ ┌──────────────┐           │
        │  │extract_epub  │ │  write_note  │           │
        │  │EPUB→JSON     │ │  笔记 CRUD   │           │
        │  └──────────────┘ └──────────────┘           │
        │  ┌──────────────┐ ┌──────────────┐           │
        │  │   state.py   │ │search_vault  │           │
        │  │   状态管理    │ │  Vault搜索   │           │
        │  └──────────────┘ └──────────────┘           │
        │  ┌──────────────┐ ┌──────────────┐           │
        │  │  errors.py   │ │  logger.py   │           │
        │  │  统一错误格式 │ │  NDJSON日志  │           │
        │  └──────────────┘ └──────────────┘           │
        └─────────────────────┬─────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────────┐
        │                 数据层                         │
        │                                               │
        │  ┌────────────────┐ ┌──────────────────────┐ │
        │  │ state/default/ │ │ state/sessions/      │ │
        │  │ current.json   │ │ <sid>.json (对话)     │ │
        │  │ history/       │ │ <sid>.recovery       │ │
        │  └────────────────┘ └──────────────────────┘ │
        │  ┌────────────────┐ ┌──────────────────────┐ │
        │  │ logs/          │ │ config.yaml          │ │
        │  │ <sid>.log      │ │                      │ │
        │  └────────────────┘ └──────────────────────┘ │
        │                                               │
        │  ┌──────────────────────────────────────────┐ │
        │  │     Obsidian Vault (外部，只写不管理)      │ │
        │  │  读书/笔记/《书名》/概念.md                │ │
        │  └──────────────────────────────────────────┘ │
        └───────────────────────────────────────────────┘
```

## 二、三条核心链路

### 链路 1：终端精读（主入口）

```
$ python agent.py
DeepRead > 读《思考快与慢》第7章
  → read_state (获取当前进度)
  → extract_epub (提取第7章)
  → 阶段0: 确认目标
  → 阶段1: 费曼输出
  → write_note create
  ...
  → state/sessions/<sid>.json (会话保存)
  → Obsidian/读书/笔记/《思考快与慢》/xxx.md

$ python agent.py --resume <sid>   # 恢复
$ python agent.py --provider anthropic --model claude-sonnet-4-6
```

### 链路 2：飞书 Bot（手机入口）

```
手机飞书消息 "继续读第7章"
  → adapters/feishu_bot.py
  → find_session_for_user(user_id) → 恢复会话
  → agent.process_message(text)
  → 返回回复
  → lark-cli im send (发送回飞书)

$ python feishu_bot.py --once "继续读" --user tangshuai  # 单次测试
```

### 链路 3：Claude Code（开发者调试）

```
Claude Code 中输入 /deepread
  → skill/SKILL.md 触发
  → 手动调脚本或让 Claude Code 调
  → 用于：开发、调试、改提示词、试新功能
```

## 三、核心组件

| 组件 | 文件 | 行数 | 职责 |
|------|------|:--:|------|
| **Agent** | `agent.py` | 600 | 多后端 LLM 对话循环、工具调度、会话管理、日志 |
| **CLI** | `cli.py` | 300 | 统一入口：chat/progress/review/think/search/doctor |
| **EPUB** | `scripts/extract_epub.py` | 329 | EPUB→结构化 JSON，38 章识别，小节拆分 |
| **笔记** | `scripts/write_note.py` | 340 | 渐进式写入：create→update→append→finalize，4 模板 |
| **状态** | `scripts/state.py` | 220 | 5 阶段 FSM，时间戳归档，多用户预留 |
| **搜索** | `scripts/search_vault.py` | 207 | Obsidian 全文搜索，反向链接，最近笔记 |
| **错误** | `scripts/errors.py` | 30 | 统一 `{"ok":false, "error_code":"...", "message":"...", "hint":"..."}` |
| **日志** | `scripts/logger.py` | 50 | NDJSON 结构化日志（API 调用/工具调用/耗时/错误） |
| **飞书** | `adapters/feishu_bot.py` | 90 | 消息→用户会话映射→agent.process_message() |
| **教练** | `skill/SKILL.md` | 120 | 四阶段阅读教练系统提示词 |
| **配置** | `config.yaml` | — | 路径/LLM/模板/集成/认知画像 |
| **会话** | `state/sessions/` | — | 对话历史 JSON + 恢复文件 |
| **日志** | `logs/` | — | NDJSON 运行日志 |

## 四、数据流：完整精读

```
用户输入 "读《思考快与慢》第7章"
  │
  ▼
agent.process_message()
  │
  ▼
LLMProvider.chat(system_prompt=SKILL.md, messages=[...], tools=[5个])
  │
  ├─→ tool_call: read_state        → state.py show → state/default/current.json
  ├─→ tool_call: extract_epub      → extract_epub.py --book ... --chapter 7 --json
  ├─→ tool_call: write_note create → write_note.py create → Obsidian/《思考快与慢》/xxx.md
  ├─→ tool_call: write_note update → write_note.py update
  ├─→ tool_call: search_vault      → search_vault.py --keyword ...
  ├─→ tool_call: update_state      → state.py set
  └─→ 纯文本回复 → 显示给用户
  │
  ▼
save_session() → state/sessions/<sid>.json
log_*()        → logs/<sid>.log
```

## 五、后端支持

| 后端 | 默认模型 | 类型 | API Key 环境变量 |
|------|---------|:--:|------|
| DeepSeek | deepseek-chat | openai 兼容 | `DEEPSEEK_API_KEY` |
| Anthropic | claude-sonnet-4-6 | 原生 | `ANTHROPIC_API_KEY` |
| OpenAI | gpt-4o | 原生 | `OPENAI_API_KEY` |

自动检测优先级：CLI `--provider` > `config.yaml llm.provider` > 环境变量。

## 六、当前成熟度

| 维度 | 状态 | 判断 |
|------|:--:|------|
| 个人自用 | ✅ | agent.py 可独立完成四阶段精读 |
| 本地可移植 | ✅ | init.py + config.yaml + skill/ 自包含 |
| 可分享给技术用户 | ✅ | pip install + API Key 即可，有 doctor 自检 |
| 飞书入口 | 🔌 | process_message() 接口就绪，单次调用可用，事件流待实现 |
| 错误恢复 | ✅ | 日志、重试、崩溃恢复文件、备份 |
| 测试 | ⬜ | 最小测试集待建 |
| Git | ⬜ | 仓库待初始化 |

## 七、后续计划

```
P0 — 端到端验收：agent.py 独立完成一章完整精读
P1 — 飞书事件流：lark-cli event consume → handle_message → 自动回复
P2 — 最小测试集：tests/test_state.py, test_write_note.py, ...
P3 — Git 初始化 + 回滚能力
P4 — 多书源：paste 文本 > Web > PDF > 微信读书
P5 — 阅读统计 / 概念地图 / 模板增强
```

## 八、关键决策记录

| 决策 | 选择 | 原因 |
|------|------|------|
| 主入口 | agent.py（替代 Claude Code） | 独立部署，不需要 Claude Code |
| 多后端 | 抽象 LLMProvider | 用户自由选择模型，自动检测 |
| 飞书集成 | process_message() 直调 | 保持会话连续性，不丢上下文 |
| Skill 存放 | deepread/skill/（自包含） | 不依赖 ~/.claude/ 外部路径 |
| 日志格式 | NDJSON（一行一记录） | 可追加、可 grep、可结构化解析 |
| 会话格式 | JSON（完整 messages 数组） | 可恢复、可审计、可跨进程 |
| 笔记写入 | 渐进式（非一次性） | 每阶段产出即写入，断电不丢 |
| 错误格式 | 统一 JSON | `{"ok":false, "error_code":"...", "hint":"..."}` |

## 九、文件清单

```
deepread/                               ← 独立包 (2000+ 行 Python + 模板 + 文档)
├── ARCHITECTURE.md                     ← 本文档
├── README.md                           ← 用户安装指南
├── requirements.txt                    ← 7 个依赖
├── .gitignore
├── config.yaml / config.example.yaml
├── init.py                             ← 初始化向导
├── agent.py                            ← ★ 主入口
├── cli.py                              ← CLI 命令
├── skill/                              ← 教练提示词（自包含）
│   ├── SKILL.md
│   └── references/ (6 文件)
├── scripts/
│   ├── extract_epub.py
│   ├── write_note.py
│   ├── state.py
│   ├── search_vault.py
│   ├── errors.py
│   └── logger.py
├── adapters/
│   └── feishu_bot.py
├── templates/ (4 种)
├── state/
│   ├── default/ (阅读状态)
│   └── sessions/ (对话会话)
└── logs/ (运行日志)
```
