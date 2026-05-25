# DeepRead 开发日志

> 从个人 Claude Code Skill 到独立多后端 Agent 的完整演进

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

## 最终架构

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
         ├─→ extract_epub.py ──→ EPUB → JSON
         ├─→ write_note.py  ──→ Obsidian 笔记
         ├─→ state.py       ──→ 阅读状态
         └─→ search_vault.py ──→ 旧笔记搜索

终端精读:
  python agent.py

开发者调试:
  Claude Code + /deepread
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
| 日志格式 | NDJSON | 可追加、可 grep、可结构化 |
| 笔记写入 | 渐进式（非一次性） | 每阶段产出即写入 |
| 错误格式 | 统一 JSON | `{"ok":false,"error_code":"...","hint":"..."}` |

## 当前版本

**v2.1.3** — 7 个 commit，30 测试全绿，18 doctor 通过，飞书稳定运行中。

下一步：7 天真实使用期，记录使用体验到 RUNNING_NOTES.md，不加新功能，只修问题。
