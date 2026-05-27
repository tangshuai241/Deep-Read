# DeepRead — AI 深度阅读教练

基于费曼学习法、苏格拉底提问和类比联想的阅读教练。帮助真正理解，而非替用户理解。

**v2.5.4** — IM-first · 9 种阅读模式 · EPUB 容错解析 · 飞书最终笔记附件回传

## 旧用户升级

从 v2.3 升级无需重新初始化。系统会自动将旧配置识别为 personal 完整版。如需显式声明：

```yaml
# 在 config.yaml 中添加
profile:
  name: personal
```

然后运行 `python cli.py doctor` 确认健康状态。

## 最快启动 (Windows)

```powershell
# 1. 安装 Python 3.9+ → https://www.python.org/downloads/
# 2. 打开 PowerShell 进入项目目录
.\install.ps1

# 3. 编辑 config.yaml 填写 Obsidian 路径和 API Key
# 4. 启动
.\start.ps1            # Web 控制台 → http://127.0.0.1:8765
.\start-bot.ps1        # 飞书 Bot（可选）
```

**排障**：`python cli.py doctor` → `python cli.py doctor --deep`

详细步骤见 [快速启动（新手版）](docs/快速启动-新手版.md)。

---

## 快速开始（终端/手动）

### 前提

- Python 3.9+
- 一个 LLM API Key（任选）：
  - [DeepSeek](https://platform.deepseek.com) — 推荐，国内直连，便宜
  - [Anthropic](https://console.anthropic.com) — 对话更细腻
  - [OpenAI](https://platform.openai.com)
- [Obsidian](https://obsidian.md/)（可选）
- EPUB 书籍

### 安装

```bash
cd deepread
pip install -r requirements.txt
python init.py
```

设置 API Key：

```bash
# DeepSeek
set DEEPSEEK_API_KEY=sk-...

# Anthropic
set ANTHROPIC_API_KEY=sk-ant-...

# OpenAI
set OPENAI_API_KEY=sk-...
```

### 使用

```bash
# 主入口：启动精读对话
python agent.py

# 或通过 CLI
python cli.py chat

# 指定后端/模型
python agent.py --provider anthropic --model claude-sonnet-4-6

# 恢复上次对话
python agent.py --resume 20260525T173000
```

## 对话命令

在 agent 对话中：

| 命令 | 作用 |
|------|------|
| `读《书名》第N章` | 开始精读 |
| `进入下一阶段` / `继续` | 推进阶段 |
| `跳过` | 跳过当前阶段 |
| `/exit` | 保存会话并退出 |
| `/state` | 查看当前阅读状态 |
| `/session` | 会话信息 |

## 轻量命令（不需要 LLM）

```bash
python cli.py progress                # 读书进度
python cli.py review                  # 随机复习一篇旧笔记
python cli.py think                   # 每天一个慢思考问题
python cli.py search 关键词           # 搜索笔记
python cli.py doctor                  # 健康检查（28项）
python cli.py doctor --deep           # 深度检查（LLM/飞书连通性）
python cli.py quality "path/note.md"  # 笔记质量检查
python cli.py concepts scan           # 概念卡盘点
python cli.py bot status              # 飞书 Bot 状态
python cli.py bot start --reply       # 启动飞书 Bot
python cli.py bot stop                # 停止飞书 Bot
```

飞书 Bot 默认会在最终笔记完成后，把生成的 `.md` 文件作为附件发回当前聊天。服务器部署时如需关闭：

```bash
export DEEPREAD_FEISHU_SEND_NOTE_FILE=0
```

## 四阶段精读流程

1. **费曼输出** — 用大白话复述核心观点
2. **苏格拉底式深化** — 触及理解边界
3. **强制联想** — 连接已有知识网络
4. **收尾** — 生成 Obsidian 笔记

笔记自动保存到 Obsidian vault。

## Claude Code 模式（开发者/调试用）

```bash
# 在 Claude Code 中输入
/deepread 读《思考快与慢》第5章
```

## 目录结构

```
deepread/
├── agent.py                  # 独立 Agent 运行时（主入口）
├── cli.py                    # CLI 命令入口
├── init.py                   # 初始化向导
├── config.yaml               # 配置文件
├── config.example.yaml       # 配置样例
├── requirements.txt          # Python 依赖
├── skill/                    # 教练提示词（自包含）
│   ├── SKILL.md
│   └── references/
├── scripts/
│   ├── extract_epub.py       # EPUB 解析
│   ├── state.py              # 状态管理
│   ├── write_note.py         # 笔记写入
│   ├── search_vault.py       # Vault 搜索
│   └── errors.py             # 统一错误格式
├── adapters/
│   └── feishu_bot.py         # 飞书 Bot 适配器
├── templates/                # 笔记模板
├── state/                    # 状态和会话
│   ├── default/
│   └── sessions/
└── logs/                     # 运行日志
```

## 配置

编辑 `config.yaml`：

- `llm.provider` — deepseek / anthropic / openai（留空自动检测）
- `llm.model` — 模型 ID（默认 `deepseek-v4-pro`）
- `llm.thinking` — DeepSeek thinking 开关：`auto` / `disabled` / `enabled`
- `note.template` — obsidian-three-section / cornell / zettelkasten / plain
- `cognition.enabled` — 是否启用认知画像
- `integrations.weread.enabled` — 是否启用微信读书

## 常见问题

**Q: EPUB 解析失败？**
A: 检查 EPUB 是否有 DRM。加密的 EPUB 无法解析。

**Q: 找不到书籍？**
A: 确认 EPUB 在 `paths.books_dir` 目录下。

**Q: 笔记在哪？**
A: `paths.notes_dir` 指定的 Obsidian vault 路径。

**Q: 支持其他模型吗？**
A: 所有 OpenAI 兼容 API 都支持。在 config.yaml 设置 `llm.provider: openai` 并配置对应的 base_url 和 api_key。

**Q: DeepSeek Thinking 怎么用？**
A: 推荐 `llm.thinking: auto`。DeepRead 会在精读、批判、联想、总结回答等深任务启用 Thinking，寒暄、进度、搜索等轻量消息关闭。手机端可用 `/深思 总结我的回答` 强制开启本轮 Thinking，用 `/普通 你好` 强制关闭本轮 Thinking。DeepRead 会保存并回传 `reasoning_content`，但不会展示它。

**Q: agent.py 和 Claude Code 什么关系？**
A: agent.py 是独立运行时，不依赖 Claude Code。Claude Code 保留作为开发者调试入口。
