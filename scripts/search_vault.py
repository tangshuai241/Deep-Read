#!/usr/bin/env python3
"""
DeepRead Vault 搜索器
在 Obsidian vault 中搜索相关笔记，支持关键词和 wikilink 反向引用。
用法:
  python search_vault.py --keyword "认知放松"               # 搜索内容
  python search_vault.py --keyword "认知放松" --json         # JSON 输出
  python search_vault.py --recent 10                        # 最近修改的笔记
  python search_vault.py --backlinks "认知放松与真相错觉"     # 找反向链接
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path


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


def get_vault_dir(config):
    return config.get("paths", {}).get("vault_dir",
        os.path.expanduser("~/Documents/知识库"))


def get_notes_dir(config):
    return config.get("paths", {}).get("notes_dir",
        os.path.join(get_vault_dir(config), "读书", "笔记"))


def extract_title_and_tags(filepath):
    """从 markdown 文件提取 frontmatter 和标题"""
    title = os.path.splitext(os.path.basename(filepath))[0]
    tags = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read(2000)
            # 提取 frontmatter
            if content.startswith('---'):
                end = content.find('---', 3)
                if end > 0:
                    fm = content[3:end]
                    for line in fm.split('\n'):
                        line = line.strip()
                        if line.startswith('tags:'):
                            pass  # handled below
                        elif line.startswith('  - '):
                            tags.append(line[4:])
            # 提取书名上下文
            book_match = re.search(r'书名:\s*《(.+?)》', content)
            book = book_match.group(1) if book_match else ""
    except Exception:
        book = ""
    return title, tags, book


def search_keyword(notes_dir, keyword, max_results=20):
    """内容搜索"""
    results = []
    kw_lower = keyword.lower()

    for root, dirs, files in os.walk(notes_dir):
        # 跳过非笔记目录
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for fname in files:
            if not fname.endswith('.md'):
                continue
            filepath = os.path.join(root, fname)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
            except Exception:
                continue

            if kw_lower in content.lower():
                title, tags, book = extract_title_and_tags(filepath)
                # 提取关键词前后的上下文
                idx = content.lower().find(kw_lower)
                start = max(0, idx - 40)
                end = min(len(content), idx + len(keyword) + 40)
                snippet = content[start:end].replace('\n', ' ').strip()
                results.append({
                    "path": filepath,
                    "title": title,
                    "book": book,
                    "tags": tags,
                    "snippet": f"...{snippet}..."
                })

    return results[:max_results]


def search_backlinks(notes_dir, target_name):
    """搜索所有引用目标笔记的 wikilink"""
    results = []
    # 去掉 .md 后缀
    target = target_name.replace('.md', '')

    for root, dirs, files in os.walk(notes_dir):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for fname in files:
            if not fname.endswith('.md'):
                continue
            filepath = os.path.join(root, fname)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
            except Exception:
                continue

            # 找 [[target]] 或 [[target|alias]]
            pattern = re.compile(r'\[\[' + re.escape(target) + r'(?:\|[^\]]+)?\]\]')
            matches = pattern.findall(content)
            if matches:
                title, tags, book = extract_title_and_tags(filepath)
                results.append({
                    "path": filepath,
                    "title": title,
                    "book": book,
                    "references": len(matches)
                })

    return results


def recent_notes(notes_dir, limit=10):
    """最近修改的笔记"""
    results = []
    for root, dirs, files in os.walk(notes_dir):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for fname in files:
            if not fname.endswith('.md'):
                continue
            filepath = os.path.join(root, fname)
            mtime = os.path.getmtime(filepath)
            title, tags, book = extract_title_and_tags(filepath)
            results.append({
                "path": filepath,
                "title": title,
                "book": book,
                "mtime": mtime
            })

    results.sort(key=lambda x: x["mtime"], reverse=True)
    return results[:limit]


def main():
    parser = argparse.ArgumentParser(description="DeepRead Vault 搜索器")
    parser.add_argument("--keyword")
    parser.add_argument("--backlinks")
    parser.add_argument("--recent", type=int)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    config = load_config()
    notes_dir = get_notes_dir(config)

    if not os.path.exists(notes_dir):
        print(f"笔记目录不存在: {notes_dir}", file=sys.stderr)
        sys.exit(1)

    if args.keyword:
        results = search_keyword(notes_dir, args.keyword, args.limit)
    elif args.backlinks:
        results = search_backlinks(notes_dir, args.backlinks)
    elif args.recent:
        results = recent_notes(notes_dir, args.recent)
    else:
        parser.print_help()
        return

    if args.json:
        # 转换路径为相对路径（更可读）
        output = []
        for r in results:
            item = dict(r)
            if "mtime" in item:
                from datetime import datetime
                item["mtime"] = datetime.fromtimestamp(item["mtime"]).isoformat()
            output.append(item)
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        for i, r in enumerate(results):
            book_info = f" [{r.get('book', '')}]" if r.get('book') else ""
            print(f"{i+1}. [[{r['title']}]]{book_info}")
            if "snippet" in r:
                print(f"   {r['snippet'][:120]}")
            if "references" in r:
                print(f"   引用数: {r['references']}")


if __name__ == "__main__":
    main()
