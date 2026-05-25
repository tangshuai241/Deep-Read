#!/usr/bin/env python3
"""
DeepRead CLI —— 统一命令行入口
用法:
  deepread progress              # 读书进度
  deepread review                # 随机复习一篇旧笔记
  deepread think                 # 生成慢思考问题
  deepread search <关键词>       # 搜索 vault
  deepread read <书> <章>        # 提取章节 + 输出 Claude Code 启动提示
  deepread status                # 阅读状态

可从任何外部入口调用（飞书 Bot / 微信桥接 / shell）。
"""

import argparse
import json
import os
import random
import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent / "scripts"
CONFIG_PATH = Path(__file__).parent / "config.yaml"


def load_config():
    if CONFIG_PATH.exists():
        try:
            import yaml
            with open(CONFIG_PATH, encoding='utf-8') as f:
                return yaml.safe_load(f)
        except ImportError:
            pass
    return {}


def run_script(name, *args):
    """运行 scripts/ 下的脚本并返回 stdout"""
    script = SCRIPTS_DIR / name
    cmd = [sys.executable, str(script)] + list(args)
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(cmd, capture_output=True, text=True,
                            encoding='utf-8', errors='replace', env=env)
    return result.stdout, result.stderr, result.returncode


def cmd_progress():
    config = load_config()
    rn_path = config.get("paths", {}).get("reading_notes",
        str(Path(__file__).parent / "reading-notes.md"))
    if os.path.exists(rn_path):
        with open(rn_path, encoding='utf-8') as f:
            content = f.read()
        # 提取关键行
        for line in content.split('\n'):
            line = line.strip()
            if line.startswith('- 《') or line.startswith('- 「'):
                print(line)
            elif '上次' in line:
                print(line)
    else:
        print("暂无读书进度记录")

    # 补充状态信息
    stdout, _, _ = run_script("state.py", "show")
    print(stdout)


def cmd_review():
    config = load_config()
    notes_dir = config.get("paths", {}).get("notes_dir", "")
    if not notes_dir or not os.path.exists(notes_dir):
        print("笔记目录不存在")
        return

    # 收集所有笔记
    notes = []
    for root, dirs, files in os.walk(notes_dir):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for f in files:
            if f.endswith('.md') and 'LLM-Wiki' not in root:
                notes.append(os.path.join(root, f))

    if not notes:
        print("还没有笔记，先去读一章吧")
        return

    note = random.choice(notes)
    rel = os.path.relpath(note, notes_dir)
    print(f"随机复习: {rel}")
    print()

    with open(note, encoding='utf-8') as f:
        content = f.read()

    # 只显示 frontmatter 后的内容（跳过元数据）
    parts = content.split('---', 2)
    body = parts[2] if len(parts) >= 3 else content
    print(body[:1500])
    print()
    print("---")
    print('试试用大白话重新解释这篇笔记的核心观点。然后输入 "/苏格拉底" 进入深化。')


def cmd_think():
    config = load_config()
    state_path = config.get("paths", {}).get("state_dir",
        str(Path(__file__).parent / "state"))
    current = os.path.join(state_path, "default", "current.json")

    book = "未知"
    chapter = "?"
    summary = ""
    if os.path.exists(current):
        with open(current, encoding='utf-8-sig') as f:
            s = json.load(f)
            c = s.get("current", {})
            book = c.get("book", "未知")
            chapter = c.get("chapter", "?")
            summary = s.get("session_summary", "")

    print(f"基于《{book}》第{chapter}章")
    if summary:
        print(f"最近讨论: {summary}")
    print()
    print("今天只想这一个问题，不用急着回：")
    print()
    print("如果你今天观察到的所有'确定无疑'的判断，其实都是系统1替你选了其中一个解释——")
    print("你现在能想起今天哪个时刻，你可能被系统1替你做主了？")
    print()
    print("（看到任何让你立刻相信、立刻反感、立刻下结论的事，都记一下。）")


def cmd_search(keyword):
    stdout, stderr, rc = run_script("search_vault.py", "--keyword", keyword, "--limit", "10")
    if rc != 0:
        print(stderr, file=sys.stderr)
        return
    print(stdout)


def cmd_doctor():
    """自检：检查依赖、路径、配置、EPUB 连通性"""
    import importlib
    errors = []
    warnings = []
    ok = []

    def check(condition, label, severity="error"):
        if severity == "error":
            (errors if not condition else ok).append(label)
        else:
            (warnings if not condition else ok).append(label)

    # 1. Python 版本
    py_ok = sys.version_info >= (3, 9)
    check(py_ok, f"Python {sys.version.split()[0]} >= 3.9")

    # 2. 依赖包
    for mod, pkg in [("ebooklib", "ebooklib"), ("bs4", "beautifulsoup4"),
                      ("lxml", "lxml"), ("chardet", "chardet"), ("yaml", "pyyaml")]:
        try:
            importlib.import_module(mod)
            check(True, f"包 {pkg} 可用")
        except ImportError:
            check(False, f"缺少包: pip install {pkg}")

    # 3. config.yaml
    config = load_config()
    check(bool(config), "config.yaml 可读取")

    # 4. 路径检查
    for key, label in [("books_dir", "书籍目录"), ("vault_dir", "Obsidian Vault"),
                        ("notes_dir", "笔记目录"), ("state_dir", "状态目录")]:
        p = config.get("paths", {}).get(key, "")
        if p:
            exists = os.path.exists(p)
            if key == "notes_dir":
                # notes_dir 可能还不存在，但父目录应该存在
                parent_ok = os.path.exists(os.path.dirname(p))
                check(parent_ok, f"{label}: {p} (可创建)", "warning" if not exists else "error")
            elif key == "state_dir":
                check(exists, f"{label}: {p}", "warning" if not exists else "error")
            else:
                check(exists, f"{label}: {p}")
        else:
            check(False, f"{label} 未配置")

    # 5. 模板文件
    tmpl_dir = Path(__file__).parent / "templates"
    if tmpl_dir.exists():
        tmpls = list(tmpl_dir.glob("*.md"))
        check(len(tmpls) >= 1, f"模板目录: {len(tmpls)} 个模板 ({', '.join(t.name for t in tmpls)})")
    else:
        check(False, "模板目录不存在")

    # 6. EPUB 连通性
    books_dir = config.get("paths", {}).get("books_dir", "")
    if books_dir and os.path.exists(books_dir):
        epubs = [f for f in os.listdir(books_dir) if f.endswith('.epub')]
        if epubs:
            check(True, f"找到 {len(epubs)} 个 EPUB: {', '.join(epubs[:3])}")
            # 试解析第一个
            stdout, stderr, rc = run_script("extract_epub.py", "--book", epubs[0], "--meta", "--json")
            if rc == 0 and stdout.strip():
                try:
                    json.loads(stdout)
                    check(True, f"EPUB 解析连通: {epubs[0]}")
                except json.JSONDecodeError:
                    check(False, f"EPUB 解析输出异常: {epubs[0]}", "warning")
            else:
                check(False, f"EPUB 解析失败: {epubs[0]} ({stderr.strip()})", "warning")
        else:
            check(False, f"未找到 EPUB 文件在 {books_dir}", "warning")
    else:
        check(False, "书籍目录不存在或未配置", "warning")

    # 7. 脚本自检
    for script in ["extract_epub.py", "state.py", "write_note.py", "search_vault.py"]:
        sp = SCRIPTS_DIR / script
        check(sp.exists(), f"脚本 {script} 存在")

    # 输出报告
    print(f"DeepRead 健康检查 — {len(ok)} 通过, {len(warnings)} 警告, {len(errors)} 错误")
    print()
    if ok:
        for item in ok[:3]:
            print(f"  PASS  {item}")
        if len(ok) > 3:
            print(f"  ... 还有 {len(ok) - 3} 项通过")
        print()
    if warnings:
        for item in warnings:
            print(f"  WARN  {item}")
        print()
    if errors:
        for item in errors:
            print(f"  FAIL  {item}")
    else:
        print("  全部检查通过。可以开始精读了。")


def cmd_read(book, chapter):
    """提取章节并输出 Claude Code 启动提示"""
    stdout, stderr, rc = run_script("extract_epub.py", "--book", book, "--chapter", chapter, "--json")
    if rc != 0:
        print(f"提取失败: {stderr}", file=sys.stderr)
        return

    data = json.loads(stdout)
    ch = data["chapter"]
    print(f"# {data['book']['title']} — {ch['title']}")
    print(f"# 字数: {ch['word_count']} | 小节: {len(data['sections'])}")
    print()

    # 显示第一节的前 300 字
    if data["sections"]:
        first = data["sections"][0]
        preview = first["text"][:300]
        print(f"## {first['title']}")
        print(preview)
        if len(first["text"]) > 300:
            print("...")
        print()

    print("---")
    print("在 Claude Code 中输入以下命令开始精读:")
    print(f"  /deepread 读《{data['book']['title']}》第{ch['index']}章")
    print()
    if ch["word_count"] > 8000:
        print(f"⚠ 本章 {ch['word_count']} 字，建议分次读")


def cmd_status():
    stdout, _, _ = run_script("state.py", "show")
    print(stdout)


def cmd_chat(args):
    """启动独立 Agent 对话"""
    agent_path = Path(__file__).parent / "agent.py"
    if not agent_path.exists():
        print("agent.py 不存在，请确认文件完整")
        return
    cmd = [sys.executable, str(agent_path)]
    if args.resume:
        cmd.extend(["--resume", args.resume])
    if args.model:
        cmd.extend(["--model", args.model])
    if args.provider:
        cmd.extend(["--provider", args.provider])
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    subprocess.run(cmd, env=env)


def main():
    parser = argparse.ArgumentParser(description="DeepRead CLI")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("progress", help="读书进度")
    sub.add_parser("review", help="随机复习一篇笔记")
    sub.add_parser("think", help="生成慢思考问题")
    sub.add_parser("status", help="当前阅读状态")
    sub.add_parser("doctor", help="健康检查：依赖/路径/配置/EPUB连通性")
    p_chat = sub.add_parser("chat", help="启动独立 Agent 对话（需要 DEEPSEEK_API_KEY 或 ANTHROPIC_API_KEY）")
    p_chat.add_argument("--resume", help="恢复会话 ID")
    p_chat.add_argument("--model", default="", help="模型 ID")
    p_chat.add_argument("--provider", default="", help="deepseek / anthropic / openai")

    p_search = sub.add_parser("search", help="搜索 vault")
    p_search.add_argument("keyword", help="搜索关键词")

    p_read = sub.add_parser("read", help="提取章节（为 Claude Code 准备）")
    p_read.add_argument("book", help="书名或 EPUB 文件名")
    p_read.add_argument("chapter", help="章节号")

    args = parser.parse_args()

    if args.command == "progress":
        cmd_progress()
    elif args.command == "review":
        cmd_review()
    elif args.command == "think":
        cmd_think()
    elif args.command == "search":
        cmd_search(args.keyword)
    elif args.command == "read":
        cmd_read(args.book, args.chapter)
    elif args.command == "status":
        cmd_status()
    elif args.command == "doctor":
        cmd_doctor()
    elif args.command == "chat":
        cmd_chat(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
