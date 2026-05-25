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
    quote = args.quote or ""
    understanding = args.understanding or "(待填入)"

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
            for q in quote.split("\\n"):
                q = q.strip()
                if q:
                    content += f"> {q}\n\n"
        else:
            content += "> (待填入)\n\n"
        content += "## 💭 我的理解\n"
        content += understanding + "\n\n"
        content += "## 🔗 让我想到\n\n"
        content += "## ❓ 待探索\n\n"

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
        new_content += args.content.rstrip() + "\n"
    if not new_content.endswith("\n\n"):
        new_content += "\n"

    lines[sec_idx:next_idx] = [new_content]
    full_content = "".join(lines)

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
    content = args.content.rstrip() + "\n"
    if insert_pos > 0 and lines[insert_pos - 1].strip() != "":
        content = "\n" + content

    lines.insert(insert_pos, content)
    full_content = "".join(lines)

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
        if "## ❓ 待探索" in content:
            content = content.rstrip() + f"\n- {args.explore}\n"
        else:
            content = content.rstrip() + f"\n\n## ❓ 待探索\n- {args.explore}\n"

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    print(json.dumps({"status": "finalized", "path": filepath}, ensure_ascii=False))


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


if __name__ == "__main__":
    main()
