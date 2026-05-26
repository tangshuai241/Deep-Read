#!/usr/bin/env python3
"""
DeepRead 笔记写入器
用法:
  python write_note.py create --book "思考快与慢" --concept "认知放松" --chapter "5.你的直觉有可能只是错觉"
  python write_note.py update --path "..." --section "我的理解" --content "..."
  python write_note.py append --path "..." --section "让我想到" --content "..."
  python write_note.py finalize --path "..." --tags "认知心理学,决策"
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from datetime import date
from errors import error, FILE_NOT_FOUND, SECTION_NOT_FOUND, IO_ERROR


def backup_file(filepath):
    """创建 .bak 备份"""
    bak_path = filepath + ".bak"
    try:
        import shutil
        shutil.copy2(filepath, bak_path)
        return bak_path
    except Exception:
        return None


def safe_write(filepath, content, check_mtime=None):
    """安全写入：先备份，检查冲突。
    如果 check_mtime 提供，写入前检查文件是否被外部修改。
    """
    if os.path.exists(filepath):
        if check_mtime is not None:
            current_mtime = os.path.getmtime(filepath)
            if abs(current_mtime - check_mtime) > 0.5:
                return {"ok": False, "error_code": "CONFLICT",
                        "message": "文件已被外部修改（可能是同步盘），拒绝覆盖",
                        "hint": "重新读取文件后再试，或手动解决冲突"}
        backup_file(filepath)
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return {"ok": True}
    except OSError as e:
        error(IO_ERROR, str(e), hint="检查目录权限和磁盘空间")


def load_config():
    config_path = Path(__file__).parent.parent / "config.yaml"
    if config_path.exists():
        try:
            import yaml
            with open(config_path, encoding='utf-8') as f:
                config = yaml.safe_load(f)
            return config
        except ImportError:
            pass
    return {}


def get_notes_dir(config):
    # 环境变量覆盖（飞书 Bot 测试用）
    env_override = os.environ.get("DEEPREAD_NOTES_DIR", "")
    if env_override:
        return env_override
    return config.get("paths", {}).get("notes_dir",
        os.path.join(os.path.dirname(__file__), "..", "notes"))


def get_vault_dir(config):
    return config.get("paths", {}).get("vault_dir",
        os.path.expanduser("~/Documents/知识库"))


def get_template_name(config):
    return config.get("note", {}).get("template", "obsidian-three-section")


def load_template(config, template_name=None):
    """加载模板内容，支持变量替换"""
    if template_name is None:
        template_name = get_template_name(config)
    template_path = Path(__file__).parent.parent / "templates" / f"{template_name}.md"
    if template_path.exists():
        with open(template_path, encoding='utf-8') as f:
            return f.read()
    return None


def slugify(title):
    """把中文概念名转成安全的文件名"""
    # 保留中文字符、字母、数字、-_
    safe = re.sub(r'[<>:"/\\|?*]', '', title)
    safe = safe.replace('\n', ' ').replace('\r', '')
    return safe.strip()[:80]


def decode_escaped_newlines(text):
    """把 LLM/tool 参数里的字面量 \\n 转成真实换行。"""
    if text is None:
        return ""
    text = str(text)
    return text.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\t", "\t")


def clean_note_text(text):
    """通用正文清洗：修正换行并压缩过度空白。"""
    text = decode_escaped_newlines(text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text.strip()


def normalize_quote_text(text):
    """把引用内容整理成 Obsidian 友好的独立引用块。"""
    text = clean_note_text(text)
    if not text:
        return "(待填入)"
    parts = [p.strip().lstrip("> ").strip() for p in re.split(r"\n\s*\n+", text) if p.strip()]
    if not parts:
        parts = [text]
    return "\n\n".join(f"> {part}" for part in parts)


def normalize_body_text(text, default="(待填入)"):
    """整理普通段落，保留模型生成的标题/列表/链接。"""
    text = clean_note_text(text)
    return text if text else default


def normalize_explore_text(text):
    """把待探索问题拆成多条 bullet。"""
    text = clean_note_text(text)
    if not text:
        return ""

    text = re.sub(r"(?<!^)(?<!\n)(\d+[.、]\s*)", r"\n\1", text)
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    items = []
    for line in lines:
        line = re.sub(r"^[-*+]\s+", "", line).strip()
        if line in ("-", "*", "+"):
            continue
        numbered = re.match(r"^\d+[.、]\s*(.+)$", line)
        if numbered:
            line = numbered.group(1).strip()
        if line:
            items.append(line)

    deduped = []
    for item in items:
        if item not in deduped:
            deduped.append(item)
    return "\n".join(f"- {item}" for item in deduped)


def normalize_note_content(content):
    """最终落盘前的 Markdown 清洗。"""
    content = decode_escaped_newlines(content)
    content = content.replace("\r\n", "\n").replace("\r", "\n")
    content = re.sub(r"\n{4,}", "\n\n\n", content)

    # 避免二级段落里再出现重复二级标题，保护主结构。
    content = content.replace("\n## 联想\n", "\n### 联想\n")

    # 确保主段落之间至少有一个空行。
    content = re.sub(r"(?<!\n)\n(## [^\n]+)", r"\n\n\1", content)
    content = re.sub(r"(---)\n(## )", r"\1\n\n\2", content, count=1)
    return content.strip() + "\n"


def extract_frontmatter(content):
    if content.startswith("---\n"):
        end = content.find("\n---", 4)
        if end >= 0:
            return content[:end + 4].strip(), content[end + 4:].lstrip()
    return "", content


def extract_sections(content):
    sections = {}
    current = None
    buf = []
    for line in content.splitlines():
        is_known_h2 = line.startswith("## ") and any(label in line for label in SECTION_MAP.values())
        if is_known_h2:
            if current is not None:
                sections[current] = "\n".join(buf).strip()
            current = line[3:].strip()
            buf = []
        elif current is not None:
            buf.append(line)
    if current is not None:
        sections[current] = "\n".join(buf).strip()
    return sections


def normalize_understanding_section(text):
    text = normalize_body_text(text)
    if text.startswith("(待填入)"):
        return text
    return text


def normalize_connection_section(text):
    text = normalize_body_text(text, default="")
    if text.startswith("## 联想"):
        text = "### 联想" + text[len("## 联想"):]
    return text


def compile_note_content(content):
    """把已有笔记重新编译成稳定的 Obsidian 三段式。"""
    frontmatter, body = extract_frontmatter(content)
    sections = extract_sections(body)

    quote = sections.get("📖 引用原文", sections.get("引用原文", ""))
    understanding = sections.get("💭 我的理解", sections.get("我的理解", ""))
    connections = sections.get("🔗 让我想到", sections.get("让我想到", ""))
    explore = sections.get("❓ 待探索", sections.get("待探索", ""))

    parts = []
    if frontmatter:
        parts.append(frontmatter)

    parts.append("## 📖 引用原文\n" + normalize_quote_text(quote))
    parts.append("## 💭 我的理解\n" + normalize_understanding_section(understanding))
    parts.append("## 🔗 让我想到\n" + normalize_connection_section(connections))

    explore = normalize_explore_text(explore)
    if explore:
        parts.append("## ❓ 待探索\n" + explore)
    else:
        parts.append("## ❓ 待探索")

    return normalize_note_content("\n\n".join(parts))


def format_frontmatter(meta):
    """生成 YAML frontmatter"""
    lines = ["---"]
    if meta.get("book"):
        lines.append(f'书名: 《{meta["book"]}》')
    if meta.get("author"):
        lines.append(f"作者: {meta['author']}")
    if meta.get("category"):
        cats = meta["category"]
        if isinstance(cats, str):
            cats = [cats]
        lines.append("学科:")
        for c in cats:
            lines.append(f"  - {c}")
    if meta.get("tags"):
        tags = meta["tags"]
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",")]
        lines.append("tags:")
        for t in tags:
            lines.append(f"  - {t}")
    if meta.get("chapter"):
        lines.append(f"章节: {meta['chapter']}")
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def create_note(notes_dir, args, config=None):
    """创建新笔记（阶段1结束后调用）"""
    if config is None:
        config = load_config()
    book_dir = os.path.join(notes_dir, f"《{args.book}》")
    os.makedirs(book_dir, exist_ok=True)

    fname = slugify(args.concept) + ".md"
    filepath = os.path.join(book_dir, fname)

    if os.path.exists(filepath):
        base = slugify(args.concept)
        i = 2
        while os.path.exists(os.path.join(book_dir, f"{base}-{i}.md")):
            i += 1
        fname = f"{base}-{i}.md"
        filepath = os.path.join(book_dir, fname)

    meta = {
        "book": args.book,
        "author": args.author or "",
        "category": args.category or "",
        "tags": args.tags or "读书笔记,思考",
        "chapter": args.chapter or ""
    }

    tmpl = load_template(config)
    quote = normalize_quote_text(args.quote)
    understanding = normalize_body_text(args.understanding)

    if tmpl:
        content = tmpl.replace("{{book}}", meta.get("book", ""))
        content = content.replace("{{author}}", meta.get("author", ""))
        content = content.replace("{{category}}", meta.get("category", ""))
        content = content.replace("{{chapter}}", meta.get("chapter", ""))
        content = content.replace("{{concept}}", args.concept)
        content = content.replace("{{quote}}", quote)
        content = content.replace("{{understanding}}", understanding)
        content = content.replace("{{summary}}", "")
        content = content.replace("{{date}}", str(date.today()))
    else:
        content = format_frontmatter(meta)
        content += "## 📖 引用原文\n"
        if quote:
            content += quote + "\n\n"
        else:
            content += "> (待填入)\n\n"
        content += "## 💭 我的理解\n"
        content += understanding + "\n\n"
        content += "## 🔗 让我想到\n\n"
        content += "## ❓ 待探索\n\n"

    content = normalize_note_content(content)
    result = safe_write(filepath, content)
    if not result["ok"]:
        error(IO_ERROR, result["message"], hint=result.get("hint", ""),
              _no_exit=False)
        sys.exit(1)

    rel_path = os.path.relpath(filepath, os.path.dirname(notes_dir))
    print(json.dumps({"ok": True, "status": "created", "path": filepath, "rel_path": rel_path}, ensure_ascii=False))
    return filepath


SECTION_MAP = {
    "引用原文": "📖 引用原文",
    "我的理解": "💭 我的理解",
    "让我想到": "🔗 让我想到",
    "待探索": "❓ 待探索",
    "quote": "📖 引用原文",
    "understanding": "💭 我的理解",
    "connection": "🔗 让我想到",
    "explore": "❓ 待探索"
}


def find_section_start(lines, section_name):
    """找到指定段落在文件中的行号"""
    target = SECTION_MAP.get(section_name, section_name)
    for i, line in enumerate(lines):
        if line.strip().startswith("## ") and target in line:
            return i
    return -1


def find_next_section(lines, start_idx):
    """找到下一个 ## 段落的行号"""
    for i in range(start_idx + 1, len(lines)):
        if lines[i].startswith("## "):
            return i
    return len(lines)


def update_section(args):
    """覆盖更新指定段落（阶段2结束后调用）"""
    filepath = args.path
    section = args.section

    if not os.path.exists(filepath):
        error(FILE_NOT_FOUND, f"文件不存在: {filepath}",
              hint="检查路径是否正确，或使用 create 创建新笔记")

    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    mtime = os.path.getmtime(filepath)

    sec_idx = find_section_start(lines, section)
    if sec_idx < 0:
        error(SECTION_NOT_FOUND, f"找不到段落: {section}",
              hint=f"可用段落: 引用原文, 我的理解, 让我想到, 待探索")

    next_idx = find_next_section(lines, sec_idx + 1)

    new_content = f"## {SECTION_MAP.get(section, section)}\n"
    if args.content:
        if section in ("引用原文", "quote"):
            new_content += normalize_quote_text(args.content) + "\n"
        else:
            new_content += normalize_body_text(args.content, default="") + "\n"
    if not new_content.endswith("\n\n"):
        new_content += "\n"

    lines[sec_idx:next_idx] = [new_content]
    full_content = normalize_note_content("".join(lines))

    result = safe_write(filepath, full_content, check_mtime=mtime)
    if not result["ok"]:
        print(json.dumps(result, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)

    print(json.dumps({"ok": True, "status": "updated", "path": filepath, "section": section}, ensure_ascii=False))


def append_section(args):
    """追加内容到指定段落（阶段3中每有联想调用）"""
    filepath = args.path
    section = args.section

    if not os.path.exists(filepath):
        error(FILE_NOT_FOUND, f"文件不存在: {filepath}")

    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    mtime = os.path.getmtime(filepath)

    sec_idx = find_section_start(lines, section)
    if sec_idx < 0:
        error(SECTION_NOT_FOUND, f"找不到段落: {section}",
              hint="可用段落: 引用原文, 我的理解, 让我想到, 待探索")

    next_idx = find_next_section(lines, sec_idx + 1)

    insert_pos = next_idx
    content = normalize_body_text(args.content, default="") + "\n"
    if insert_pos > 0 and lines[insert_pos - 1].strip() != "":
        content = "\n" + content

    lines.insert(insert_pos, content)
    full_content = normalize_note_content("".join(lines))

    result = safe_write(filepath, full_content, check_mtime=mtime)
    if not result["ok"]:
        print(json.dumps(result, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)

    print(json.dumps({"ok": True, "status": "appended", "path": filepath, "section": section}, ensure_ascii=False))


def finalize_note(args):
    """补全 frontmatter（阶段4调用）"""
    filepath = args.path

    if not os.path.exists(filepath):
        print(json.dumps({"status": "error", "message": f"文件不存在: {filepath}"}, ensure_ascii=False))
        sys.exit(1)

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # 更新 tags（追加不重复的概念标签）
    if args.tags:
        new_tags = [t.strip() for t in args.tags.split(",") if t.strip()]
        for tag in new_tags:
            if f"  - {tag}" not in content:
                # 在 tags 列表末尾添加
                content = re.sub(
                    r'(tags:\s*\n(?:  - .+\n)*)',
                    rf'\1  - {tag}\n',
                    content
                )

    # 追加待探索
    if args.explore:
        explore = normalize_explore_text(args.explore)
        if "## ❓ 待探索" in content:
            content = content.rstrip() + f"\n{explore}\n"
        else:
            content = content.rstrip() + f"\n\n## ❓ 待探索\n{explore}\n"

    content = normalize_note_content(content)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    print(json.dumps({"status": "finalized", "path": filepath}, ensure_ascii=False))


def compile_note(args):
    """重新编译已有笔记为稳定的 Obsidian 三段式。"""
    filepath = args.path

    if not os.path.exists(filepath):
        print(json.dumps({"status": "error", "message": f"文件不存在: {filepath}"}, ensure_ascii=False))
        sys.exit(1)

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    mtime = os.path.getmtime(filepath)

    compiled = compile_note_content(content)
    result = safe_write(filepath, compiled, check_mtime=mtime)
    if not result["ok"]:
        print(json.dumps(result, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)

    print(json.dumps({"ok": True, "status": "compiled", "path": filepath}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description="DeepRead 笔记写入器")
    sub = parser.add_subparsers(dest="command")

    p_create = sub.add_parser("create", help="创建笔记草稿")
    p_create.add_argument("--book", required=True)
    p_create.add_argument("--concept", required=True)
    p_create.add_argument("--chapter", default="")
    p_create.add_argument("--author", default="")
    p_create.add_argument("--category", default="")
    p_create.add_argument("--tags", default="")
    p_create.add_argument("--quote", default="")
    p_create.add_argument("--understanding", default="")

    p_update = sub.add_parser("update", help="覆盖更新段落")
    p_update.add_argument("--path", required=True)
    p_update.add_argument("--section", required=True)
    p_update.add_argument("--content", required=True)

    p_append = sub.add_parser("append", help="追加到段落")
    p_append.add_argument("--path", required=True)
    p_append.add_argument("--section", required=True)
    p_append.add_argument("--content", required=True)

    p_finalize = sub.add_parser("finalize", help="补全 frontmatter")
    p_finalize.add_argument("--path", required=True)
    p_finalize.add_argument("--tags", default="")
    p_finalize.add_argument("--explore", default="")

    p_compile = sub.add_parser("compile", help="整理已有笔记为 Obsidian 三段式")
    p_compile.add_argument("--path", required=True)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    config = load_config()
    notes_dir = get_notes_dir(config)

    if args.command == "create":
        create_note(notes_dir, args, config)
    elif args.command == "update":
        update_section(args)
    elif args.command == "append":
        append_section(args)
    elif args.command == "finalize":
        finalize_note(args)
    elif args.command == "compile":
        compile_note(args)


if __name__ == "__main__":
    main()
