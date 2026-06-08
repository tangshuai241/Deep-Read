# Book Toolchain — 多维书籍拆解 + 深度阅读教练

三件套：**下载 → 拆解 → 教练**

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://python.org)
[![DeepSeek](https://img.shields.io/badge/LLM-DeepSeek%20V4%20Pro-orange)](https://platform.deepseek.com)

---

## 快速开始

### 一键安装

```bash
git clone https://github.com/your-username/book-toolchain.git
cd book-toolchain
python install.py
```

`install.py` 会自动：
1. 检测你用的 AI Agent（Hermes / Claude Code / 其他）
2. 按环境安装对应配置
3. 引导填写 `config.yaml`

### 配置

安装后编辑 `config.yaml`，必填：

```yaml
llm:
  provider: "deepseek"
  api_key: "***"                        # https://platform.deepseek.com 注册获取
  model: "deepseek-v4-pro"              # 或 deepseek-v4-flash
  base_url: "https://api.deepseek.com"

paths:
  books_dir: "~/TaskOS/books"           # EPUB + 4D 拆解 JSON 统一存储
  notes_dir: "~/Documents/reading-notes" # 阅读笔记输出
```

验证：`python doctor.py`

---

## 三件套

```
book_downloader/     ← EPUB 下载（Gutenberg + LibGen）+ 邮件发送
4d_pipeline/         ← 四维并行 Agent 拆解（骨架/思想/论证/叙事）
deepread/            ← 费曼教练 + Obsidian 笔记 + 4D 预读对接
```

### 1. 下载一本书

```bash
python book_downloader/book_downloader.py search "Thinking, Fast and Slow"
python book_downloader/book_downloader.py download <id>
```

或在你的 AI Agent 中说 "下载《思考快与慢》"。

### 2. 运行 4D 拆解

**Hermes：** 说 "拆解《思考快与慢》"（自动调用 delegate_task 并行拆解）

**Claude Code：** 说 "按 4d_pipeline/CLAUDE.md 拆解《思考快与慢》"（用 Task 工具并行）

**CLI：** `python book_downloader/book_downloader.py get "Thinking, Fast and Slow"`（仅下载）

输出：`{BOOKS_DIR}/{book}/analysis/` 下 6 份 JSON + 全文。

### 3. 开始深度阅读

```bash
cd deepread
python agent.py --book "thinking_fast_slow"
```

或在 AI Agent 中说 "读《思考快与慢》第5章"。

---

## 各平台兼容性

| 模块 | Hermes | Claude Code | 其他 Agent | CLI |
|------|--------|-------------|-----------|-----|
| book-downloader | ✅ 自动 | ✅ CLI | ✅ CLI | ✅ CLI |
| 4D 拆解 | ✅ Skill | ✅ Task 并行 | ❌ 缺子 Agent | ❌ |
| DeepRead 教练 | ✅ Skill | ✅ CLAUDE.md | ✅ prompt 模板 | ✅ CLI |

> 4D 拆解需要并行隔离子 Agent 能力。目前仅 Hermes (`delegate_task`) 和 Claude Code (`Task`) 支持。

---

## 可选功能

### 邮件发送 EPUB

```yaml
# config.yaml
email:
  enabled: true
  smtp_host: "smtp.qq.com"
  smtp_port: 465
  smtp_ssl: true
  smtp_sender: "your-email@qq.com"
  smtp_password: ""    # 推荐用环境变量 SMTP_PASSWORD
```

### Obsidian 集成

```yaml
obsidian:
  enabled: true
  vault_dir: "~/Documents/ObsidianVault"
```

---

## 项目结构

```
book-toolchain/
├── install.py                     ← 一键安装引导
├── doctor.py                      ← 健康检查
├── config.example.yaml            ← 配置模板
├── README.md
├── LICENSE
├── .gitignore
├── book_downloader/
│   ├── book_downloader.py         ← 双源下载器 + 邮件
│   └── SKILL.md                   ← Hermes skill
├── 4d_pipeline/
│   ├── SKILL.md                   ← Hermes skill
│   └── CLAUDE.md                  ← Claude Code 指令
├── deepread/
│   ├── agent.py                   ← 独立 Agent 运行时
│   ├── config.yaml                ← DeepRead 本地配置（提交到 git）
│   ├── SKILL.md                   ← Hermes skill
│   ├── CLAUDE.md                  ← Claude Code 指令
│   ├── reading-notes.example.md   ← 阅读进度模板
│   ├── state/                     ← 会话状态（gitignore）
│   ├── logs/                      ← 运行日志（gitignore）
│   └── scripts/
│       ├── extract_epub.py        ← EPUB 章节提取
│       ├── preload_analysis.py    ← 4D→DeepRead 桥接
│       ├── errors.py              ← 错误定义
│       ├── state.py               ← 会话状态读写
│       ├── learning_contract.py   ← 学习契约
│       ├── write_note.py          ← 笔记写入
│       ├── search_vault.py        ← 知识库搜索
│       ├── logger.py              ← 日志
│       └── reading_modes.py       ← 阅读模式定义
```

---

## 依赖

- Python 3.12+
- `pip install requests pyyaml`
- DeepSeek API Key（或任何 OpenAI 兼容接口）
- Hermes Agent 或 Claude Code（4D 拆解 + DeepRead 需要）

---

## License

MIT
