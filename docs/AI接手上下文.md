# DeepRead AI 接手上下文

> 更新时间：2026-05-28  
> 当前版本：v2.5.7  
> 用途：给新的 AI / 开发助手快速理解项目现状、边界、服务器部署状态和下一步工作。

---

## 1. 项目一句话

DeepRead 是一个 **IM-first 的 AI 深度阅读教练**。主要使用方式不是网页聊天，而是在飞书 Bot 里通过手机语音/文字对话学习；Agent 负责追问、引导、生成笔记；Obsidian/Markdown 负责沉淀；Web 控制台只负责运维、诊断、用户管理、书籍检查和备份。

---

## 2. 当前稳定能力

### 已可用主链路

```text
飞书手机消息
  -> adapters/feishu_bot.py listen --reply
  -> agent.py
  -> DeepSeek/Anthropic/OpenAI compatible LLM
  -> extract_epub / learning_contract / search_vault / write_note
  -> 飞书回复
  -> 最终 Markdown 笔记附件回传
```

### 已完成的重要版本

| 版本 | 状态 | 核心变化 |
|---|---|---|
| v2.5.3 | 已完成 | EPUB 容错解析增强 |
| v2.5.4 | 已完成 | 飞书最终笔记附件回传、重复消息防护 |
| v2.5.5 | 已完成 | 多用户笔记隔离 |
| v2.5.6 | 已完成 | 修复 EPUB 显式章节编号，前言不再占用第 1 章 |
| v2.5.7 | 已完成 | Web 登录、服务器备份、用户管理、书籍导入检查 |

当前测试：`124 passed`。

---

## 3. 主要入口

### 手机 IM 入口

```bash
python adapters/feishu_bot.py listen --reply
```

服务器上长期运行：

```bash
systemctl status deepread-bot --no-pager
systemctl restart deepread-bot
journalctl -u deepread-bot -n 100 --no-pager
```

### Web 运维入口

本机：

```powershell
.\start.ps1
```

服务器：

```bash
systemctl status deepread-web --no-pager
systemctl restart deepread-web
journalctl -u deepread-web -n 100 --no-pager
```

Web 地址：

```text
http://114.55.244.46:8765
```

Web 公开访问必须设置：

```bash
DEEPREAD_WEB_PASSWORD=强密码
```

### CLI 入口

```bash
python cli.py doctor --deep
python cli.py bot status
python cli.py quality "path/to/note.md"
python cli.py concepts report
python cli.py modes list
python cli.py backup
```

服务器若没有 `python` 命令，使用：

```bash
python3
/www/wwwroot/deepread/.venv/bin/python
```

---

## 4. 服务器状态

服务器路径：

```text
/www/wwwroot/deepread
```

服务器服务：

```text
deepread-bot.service  -> 飞书 Bot 长期监听
deepread-web.service  -> Web 控制台，端口 8765
```

常用命令：

```bash
cd /www/wwwroot/deepread
git pull origin master
source .venv/bin/activate
pip install -r requirements.txt
systemctl restart deepread-bot
systemctl restart deepread-web
```

端口：

```text
8765  -> DeepRead Web
```

如果浏览器打不开 Web，优先检查：

1. 阿里云 ECS 安全组是否放行 TCP `8765`
2. 宝塔防火墙是否放行 TCP `8765`
3. `systemctl status deepread-web --no-pager`

---

## 5. Git 与同步

服务器当前使用 Gitee 拉取。服务器 remote 通常是：

```text
origin https://gitee.com/sakura_241/deep-read.git
```

本机 remote：

```text
gitee  https://gitee.com/sakura_241/deep-read.git
origin git@github.com:tangshuai241/Deep-Read.git
```

服务器拉代码：

```bash
cd /www/wwwroot/deepread
git pull origin master
git log -1 --oneline
```

如果服务器有本地改动导致 pull 失败：

```bash
git stash push -u -m "server-before-pull-$(date +%Y%m%d%H%M%S)"
git pull origin master
```

---

## 6. 数据隔离

飞书多用户用 `open_id` 隔离。

### 会话

```text
state/sessions/*.json
```

会话文件中带：

```json
{
  "user_id": "ou_xxx"
}
```

### 状态与契约

```text
state/<user_id>/current.json
state/<user_id>/learning_contract.json
```

### 笔记

Trial / IM-first 默认隔离：

```text
notes/users/<user_id>/《书名》/*.md
```

Personal 默认不强制加 `users/`，避免污染个人 Obsidian 既有结构。如多人共用 Personal Bot，需设置：

```yaml
note:
  isolate_by_user: true
```

---

## 7. Web 页面

| 页面 | 作用 |
|---|---|
| `/` | 总览仪表盘 |
| `/sessions` | 会话列表 |
| `/notes` | 笔记查看 |
| `/compare` | 两端笔记对比 |
| `/doctor` | 健康检查 |
| `/setup` | 配置状态 |
| `/modes` | 阅读模式 |
| `/concepts` | 概念卡覆盖率 |
| `/users` | 用户管理、导出、重置 |
| `/books` | EPUB 导入检查、目录预览、章节校验 |
| `/backup` | 服务器备份 |
| `/login` | Web 登录 |

Web API：

```text
GET  /api/users
GET  /api/users/{user}
GET  /api/users/{user}/export
POST /api/users/{user}/reset
GET  /api/books
GET  /api/books/inspect?book=...
GET  /api/backup
POST /api/backup
GET  /api/bot/status
POST /api/bot/start
POST /api/bot/stop
POST /api/bot/restart
GET  /api/doctor?deep=1
GET  /api/quality?path=...
```

---

## 8. 阅读模式

阅读模式定义在：

```text
scripts/reading_modes.py
skill/references/reading-modes.md
```

当前 9 种：

| key | 名称 | Trial |
|---|---|---|
| `concept_deep_read` | 概念精读 | yes |
| `proposition_dialogue` | 命题辨析 | yes |
| `method_conversion` | 方法转化 | yes |
| `exam_mastery` | 考试掌握 | yes |
| `historical_context` | 历史脉络 | yes |
| `textbook_derivation` | 教材推导 | no |
| `standard_lookup` | 规范检索 | no |
| `case_review` | 案例复盘 | no |
| `literature_experience` | 文学体验 | no |

《明朝那些事儿》应走：

```text
historical_context
```

---

## 9. EPUB 解析与检查

核心脚本：

```text
scripts/extract_epub.py
```

常用命令：

```bash
python scripts/extract_epub.py --book "明朝那些事儿" --list
python scripts/extract_epub.py --book "明朝那些事儿" --chapter 1 --json
python scripts/extract_epub.py --book "明朝那些事儿" --inspect --json
```

v2.5.6 修复点：

```text
如果 EPUB 目录中已有显式“第一章/第二章”，前言、引子、主目录不再自动编号。
```

v2.5.7 增强点：

```text
--inspect 可输出目录预览、非章节项、空章节、短章节、重复编号、分卷编号重置。
```

注意：《明朝那些事儿》这类全集 EPUB 常见分卷后章节号重新从第一章开始，所以重复章节号不一定是错误，要结合分卷标题看。

---

## 10. 备份

备份脚本：

```text
scripts/backup.py
```

默认备份：

```text
config.yaml
reading-notes.md
state/
notes/
logs/
```

不默认备份 `books/`，因为 EPUB 可能很大。

命令：

```bash
python cli.py backup
python cli.py backup --include-books
python cli.py backup --list
```

Web：

```text
/backup
```

---

## 11. 重要配置

配置文件：

```text
config.yaml
profiles/trial/config.example.yaml
profiles/personal/config.example.yaml
```

关键字段：

```yaml
profile:
  name: trial | personal
  im_first: true | false

paths:
  books_dir: "./books"
  notes_dir: "./notes"
  state_dir: "./state"
  vault_dir: ""

note:
  isolate_by_user: true

llm:
  provider: ""
  model: "deepseek-v4-pro"
  api_key: ""
  base_url: ""
  thinking: "auto"

web:
  password: ""
```

服务器更推荐用环境变量设置密码：

```bash
DEEPREAD_WEB_PASSWORD=...
```

---

## 12. 近期常见问题

### 1. Web `/users` `/books` `/backup` 返回 Not Found

说明服务器没有拉到 v2.5.7 或 Web 服务没重启。

```bash
cd /www/wwwroot/deepread
git pull origin master
systemctl restart deepread-web
```

检查路由：

```bash
/www/wwwroot/deepread/.venv/bin/python - <<'PY'
import server
print([r.path for r in server.app.routes if r.path in ["/users", "/books", "/backup"]])
PY
```

### 2. `ModuleNotFoundError: No module named 'jinja2'`

依赖已补到 `requirements.txt`。服务器执行：

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. 服务器没有 `python`

Ubuntu 默认可能只有 `python3`。

```bash
python3 --version
/www/wwwroot/deepread/.venv/bin/python --version
```

### 4. `git pull gitee master` 失败

服务器 remote 名称通常不是 `gitee`，而是 `origin`。

```bash
git remote -v
git pull origin master
```

### 5. Web 服务 active 但浏览器打不开

检查：

```bash
systemctl status deepread-web --no-pager
ss -lntp | grep 8765
```

然后放行：

```text
阿里云 ECS 安全组 TCP 8765
宝塔防火墙 TCP 8765
```

---

## 13. 当前边界

### DeepRead 强项

- 概念理解
- 追问与辨析
- 个人联想
- 知识迁移
- 生成结构化 Markdown / Obsidian 笔记
- IM 端低摩擦学习
- 多用户朋友试用

### DeepRead 弱项

- 不适合裸奔公网，无密码 Web 很危险
- 考试模式还缺题库、错题、间隔复习
- 语义搜索仍是后续增强，不是完整向量库
- LLM-Wiki 只作为路由/链接裁判，不自动静默改 Wiki
- Web 不是主学习界面，不应改成复杂聊天应用

---

## 14. 下一步建议

优先级建议：

1. **服务器安全与运维**
   - 确认 Web 密码
   - 确认 8765 仅必要范围开放
   - 定期备份
   - Web 日志页面

2. **朋友试用体验**
   - `/books` 支持网页上传 EPUB
   - 新用户首次欢迎流程
   - 用户导出结果可直接飞书发送

3. **历史脉络模式深化**
   - 时间线结构化
   - 人物关系图
   - 关键转折与制度背景模板
   - 《明朝那些事儿》作为样例回归

4. **Obsidian 联动增强**
   - 概念卡 aliases 批量建设
   - 语义搜索
   - Wiki 更新建议，不静默写 Wiki

5. **考试掌握模式**
   - 题库
   - 错题
   - 记忆卡
   - 考点覆盖率

---

## 15. 给接手 AI 的操作原则

- 不要把 Web 改成主学习入口；主学习入口是飞书/IM。
- 不要破坏 Personal 用户的 Obsidian 目录结构。
- 多用户相关改动必须按 `user_id/open_id` 隔离。
- 重置用户数据应归档移动，不直接删除。
- 服务器上的 `git pull` 如果有冲突，先 stash，不要硬 reset。
- EPUB 解析要兼容损坏资源、前言、引子、分卷和章节号重置。
- 新功能至少补最小测试，并跑 `python -m pytest -q`。
