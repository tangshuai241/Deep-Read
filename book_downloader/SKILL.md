---
name: book-downloader
description: >-
  Search and download ebooks from Gutenberg (60,000+ public domain) and LibGen (millions, incl. Chinese contemporary).
  Supports EPUB quality verification and email delivery with correct MIME types.
  Use when user asks to find/download/search books, ebooks, novels, or send books via email.
triggers:
  - search: 找书/搜书/下载书/电子书/epub/book/书籍/小说/名著/下本书/发邮箱
compatibility:
  standalone: true          # book_downloader.py 可脱离 Hermes 独立运行
  hermes: true              # Hermes 用户可直接加载本 skill
---

# Book Downloader v2 — 双源搜书 + 邮件交付

> **前置检查**：搜索不需要配置。下载时才需要 `config.yaml → paths.books_dir`。
> 如果 `config.yaml` 不存在，引导用户运行 `python install.py`。

> **兼容性**：本工具提供两条使用路径——
> - **独立 CLI**：`python book_downloader/book_downloader.py search "xxx"`（任何 Python 环境）
> - **Hermes Skill**：Hermes 用户加载本 skill 后，说"下载《XXX》"自动调用

## 首次使用

```bash
# 1. 创建配置文件
cp config.example.yaml config.yaml

# 2. 编辑 config.yaml，至少填写：
#    - paths.books_dir（EPUB 存放目录，如 ~/TaskOS/books）
#    - email.smtp_*（如需邮件发送功能）
```

配置文件会被自动搜索（优先级：脚本上级目录 → 当前目录 → `~/.book-toolchain/`）。

## 快速开始

```bash
# Gutenberg 搜索（公版英文/中文古籍）
python book_downloader/book_downloader.py search "tan jing" -n 5

# LibGen 搜索（当代中文书）
python book_downloader/book_downloader.py search "坛经 中华书局" -s libgen -n 10

# Gutenberg 下载
python book_downloader/book_downloader.py download 23844 -s gutenberg

# LibGen 下载（用 MD5）
python book_downloader/book_downloader.py download <32位MD5> -s libgen

# 验证 EPUB
python book_downloader/book_downloader.py verify "path/to/book.epub"

# 发邮件（需先配置 config.yaml → email 段）
python book_downloader/book_downloader.py email "path/to/book.epub" "recipient@example.com"
```

输出目录默认从 `config.yaml → paths.books_dir` 读取，可用 `-o` 指定。

---

## 搜索策略（按书籍类型）

### 类型 A：公版英文经典 / 中文古籍
→ **Gutenberg** 主力
- 中文搜拼音：三国演义→"three kingdoms"，论语→"analects"，坛经→"tan jing"
- 直接 `search` → `download`

### 类型 B：中文当代出版物（如中华书局版）
→ **LibGen** 主力。Gutenberg 只有古文原文，没有现代点校本。

5 步 fallback 链（按顺序试）：
1. **libgen.li CLI** — `book_downloader.py search "书名 出版社" -s libgen` ✅ 首选
2. **libgen.li 浏览器** — 打开 `https://libgen.li`，搜索后手动点下载（CLI 失败时）
3. **Anna's Archive 浏览器** — `https://annas-archive.org`（国内常被墙）
4. **libgen.is 浏览器** — `https://libgen.is`（国内常不可达）
5. 如实告知用户：已穷尽可用源，建议尝试 Z-Library 个人账号或其他渠道

### 类型 C：连 LibGen 都没有的小众书
→ 如实告知，不做假。

---

## 源一：Project Gutenberg（公版）

**特点**：60,000+ 公版书，curl 直接下载，稳定快速。

**下载 URL**：`https://www.gutenberg.org/ebooks/{id}.epub.noimages`

**中文古籍速查表**：

| 书名 | Gutenberg 搜索词 | ID |
|------|-----------------|-----|
| 三国演义 | three kingdoms | 23950 |
| 西游记 | journey to the west | 23962 |
| 红楼梦 | dream of the red chamber | 9603 |
| 孙子兵法 | art of war | 132 |
| 论语 | analects | 3330 |
| 六祖坛经 | tan jing | 23844 |
| 道德经 | tao te ching | 49965 |

**限制**：只有公版书（版权过期），无当代出版物。古籍是原文无标点版，非现代点校本。

---

## 源二：LibGen（百万级，含中文当代书）

### 搜索
```bash
python book_downloader/book_downloader.py search "坛经 中华书局" -s libgen -n 10
```
输出：MD5、书名、出版社、年份、格式、大小。

### 下载（关键：必须用 requests session）
LibGen 下载需要 cookie/session 交换。**curl / wget 会失败**（返回 HTML 而非文件）。
脚本已内置 requests session 流程：

```
ads.php?md5=XXX  →  提取 key  →  get.php?md5=XXX&key=YYY  →  文件
```

```bash
python book_downloader/book_downloader.py download <32位MD5> -s libgen
```

**依赖**：`requests` 库（`pip install requests` 如未安装）

### 已知陷阱
- **不能用 curl**：libgen.li 需要 cookie 会话，curl 被拦截返回 HTML
- **key 会过期**：从 ads.php 获取的 download key 有效期很短（~30秒），拿到立刻用
- **mirror 不稳定**：libgen.is 国内常不可达；Anna's Archive 国内被墙
- **library.lol**：404 率极高，不推荐

---

## EPUB 质量核验

```bash
python book_downloader/book_downloader.py verify "path/to/book.epub"
```

报告字段：
- `valid`：是否为合法 EPUB（mimetype + container.xml + .opf）
- `size_kb`：文件大小
- `chapters`：HTML/XHTML 章节数
- `images`：图片数
- `title`, `author`, `publisher`：元数据
- `samples`：前 3 大章节的内容抽样（验证确实是目标书籍）

核验必须做：确认是用户要的版本（Gutenberg 古文 vs 中华书局点校本 vs 其他出版社）。

---

## 邮件发送

需先在 `config.yaml` 中配置 `email` 段（smtp_host / smtp_port / smtp_sender / smtp_password），或设置环境变量 `SMTP_PASSWORD`。

```bash
python book_downloader/book_downloader.py email "path/to/book.epub" "recipient@example.com"
```

### MIME 类型修复（重要）
- ✅ `Content-Type: application/epub+zip` + RFC 2231 文件名编码
- ❌ 不能用 `application/octet-stream` → 主流邮箱会改名 `.bin`
- 文件名用 `("utf-8", "", "书名.epub")` 格式防止乱码

### 自定义邮件
```bash
python book_downloader/book_downloader.py email "book.epub" "user@example.com" \
  -s "定制主题" -b "定制正文"
```

---

## 依赖

- Python 3.12+（标准库：json, zipfile, urllib, pathlib, smtplib, email, re）
- `requests`（仅 LibGen 需要；`pip install requests`）
- `pyyaml`（读取 config.yaml；`pip install pyyaml`）
- SMTP 配置（仅邮件功能需要；不启用则跳过）

---

## 工作流（Hermes 端到端）

用户说"下载《XXX》"时：

1. **判断版本需求**：公有领域（Gutenberg）还是当代出版物（LibGen）
2. **搜索**：选择正确源搜索
3. **下载**：CLI 直接下载
4. **核验**：`verify` 命令确认是用户要的版本
5. **邮件**：如用户要求发邮箱，用 `email` 子命令

如果 LibGen CLI 失败：
→ 浏览器打开 libgen.li 手动搜索 → 用户确认后点下载
→ 始终告知用户当前在哪一步
