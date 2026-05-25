#!/usr/bin/env python3
"""
DeepRead EPUB 提取器
用法:
  python extract_epub.py --book "思考快与慢.epub" --list
  python extract_epub.py --book "思考快与慢.epub" --chapter 5
  python extract_epub.py --book "思考快与慢.epub" --chapter 5 --json
  python extract_epub.py --book "思考快与慢.epub" --meta
"""

import argparse
import json
import re
import sys
import os
import warnings
from pathlib import Path
from errors import error, BOOK_NOT_FOUND, CHAPTER_NOT_FOUND, EPUB_PARSE_FAILED

try:
    from ebooklib import epub
    from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
    warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
except ImportError as e:
    from errors import error, DEPENDENCY_MISSING
    error(DEPENDENCY_MISSING, str(e), hint="pip install ebooklib beautifulsoup4 lxml")


def load_config():
    config_path = Path(__file__).parent.parent / "config.yaml"
    if config_path.exists():
        try:
            import yaml
            with open(config_path, encoding='utf-8') as f:
                config = yaml.safe_load(f)
            return config.get("paths", {}).get("books_dir", os.getcwd())
        except ImportError:
            pass
    return os.getcwd()


def resolve_book_path(book_arg, books_dir):
    if os.path.isabs(book_arg) and os.path.exists(book_arg):
        return book_arg
    candidate = os.path.join(books_dir, book_arg)
    if os.path.exists(candidate):
        return candidate
    if not os.path.isdir(books_dir):
        return None
    for f in os.listdir(books_dir):
        if f.endswith('.epub') and book_arg.replace('.epub', '') in f:
            return os.path.join(books_dir, f)
    return None


def clean_html(html_content):
    soup = BeautifulSoup(html_content, 'lxml')
    for tag in soup(['script', 'style']):
        tag.decompose()
    text = soup.get_text()
    text = re.sub(r'\n\s*\n', '\n\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    return text.strip()


CHAPTER_PATTERN = re.compile(r'第(\d+)章')
PART_PATTERN = re.compile(r'第[一二三四五六七八九十百]+部分')
NCX_ENTRY_PATTERN = re.compile(
    r'<navPoint[^>]*>.*?<navLabel>\s*<text>(.*?)</text>\s*</navLabel>.*?<content\s+src="([^"]*)"',
    re.DOTALL
)


def parse_ncx(book):
    """用正则从 NCX 提取所有导航点（扁平列表）。
    返回: [{"title": ..., "file": ..., "is_chapter": bool, "is_part": bool, "chapter_num": int|None}, ...]
    """
    for item in book.get_items():
        if 'ncx' in item.get_name().lower():
            raw = item.get_content().decode('utf-8')
            entries = []
            for m in NCX_ENTRY_PATTERN.finditer(raw):
                title = m.group(1).strip()
                fname = m.group(2).split('#')[0]
                cm = CHAPTER_PATTERN.match(title)
                pm = PART_PATTERN.match(title)
                entries.append({
                    "title": title,
                    "file": fname,
                    "is_chapter": bool(cm),
                    "is_part": bool(pm),
                    "chapter_num": int(cm.group(1)) if cm else None
                })
            return entries
    return []


def get_chapter_sections(ncx, chapter_num):
    """获取某章的所有小节标题。
    返回: [{"title": ..., "file": ...}, ...]
    """
    sections = []
    in_chapter = False
    for entry in ncx:
        if entry["is_chapter"]:
            if entry["chapter_num"] == chapter_num:
                in_chapter = True
                continue
            elif in_chapter:
                break  # 进入下一章，停止
        if in_chapter and not entry["is_part"]:
            sections.append({"title": entry["title"], "file": entry["file"]})
    return sections


def get_content_for_file(book, file_name):
    for item in book.get_items():
        if item.get_name() == file_name:
            return clean_html(item.get_content())
    return None


def get_content_soup(book, file_name):
    for item in book.get_items():
        if item.get_name() == file_name:
            return BeautifulSoup(item.get_content(), 'lxml')


def list_chapters(book, ncx):
    chapters = []
    for entry in ncx:
        if entry["is_chapter"]:
            text = get_content_for_file(book, entry["file"])
            wc = len(text) if text else 0
            chapters.append((entry, wc))

    print(f"{'#':>3}  {'章节':<42} {'字数':>6}")
    print("-" * 54)
    for entry, wc in chapters:
        print(f"{entry['chapter_num']:>3}  {entry['title']:<42} {wc:>6}")
    print(f"\n共 {len(chapters)} 章")
    return len(chapters)


def find_chapter(ncx, chapter_ref):
    try:
        target = int(chapter_ref)
        for entry in ncx:
            if entry["is_chapter"] and entry["chapter_num"] == target:
                return entry
        return None
    except ValueError:
        for entry in ncx:
            if chapter_ref in entry["title"] and entry["is_chapter"]:
                return entry
        return None


def extract_chapter_text(book, entry, ncx):
    """提取章节全文，按小节拆分"""
    full_text = get_content_for_file(book, entry["file"])
    if not full_text:
        return None

    sections = []
    section_titles = get_chapter_sections(ncx, entry["chapter_num"])

    if section_titles:
        remaining = full_text
        for sec in section_titles:
            st = sec["title"]
            idx = remaining.find(st)
            if idx >= 0:
                if idx > 50 and not sections:
                    intro_text = remaining[:idx].strip()
                    if len(intro_text) > 20:
                        sections.append({"title": "_intro", "text": intro_text, "word_count": len(intro_text)})
                # 找下一个小节边界
                next_idx = len(remaining)
                for other_sec in section_titles:
                    if other_sec["title"] != st:
                        pos = remaining.find(other_sec["title"], idx + len(st))
                        if 0 < pos < next_idx:
                            next_idx = pos
                section_text = remaining[idx:next_idx].strip()
                if section_text.startswith(st):
                    section_text = section_text[len(st):].strip()
                if section_text:
                    sections.append({"title": st, "text": section_text, "word_count": len(section_text)})
                remaining = remaining[next_idx:]

    # 如果 NCX 小节切分不够，尝试按 HTML 标题标签切分
    if not sections or len(sections) <= 1:
        sections = _split_by_html_headings(book, entry, full_text)

    if not sections:
        sections = [{"title": entry["title"], "text": full_text, "word_count": len(full_text)}]

    return {
        "title": entry["title"],
        "word_count": len(full_text),
        "file": entry["file"],
        "sections": sections
    }


def _split_by_html_headings(book, entry, full_text):
    """按 HTML 中的 h3/h4 标题切分"""
    soup = get_content_soup(book, entry["file"])
    if not soup:
        return []
    body = soup.find('body')
    if not body:
        return []
    for tag in body(['script', 'style']):
        tag.decompose()
    headings = body.find_all(['h3', 'h4'])
    if not headings:
        return []

    sections = []
    remaining = full_text
    heading_data = [(h.get_text().strip(), h.name) for h in headings]

    for i, (ht, _tag) in enumerate(heading_data):
        idx = remaining.find(ht)
        if idx < 0:
            continue
        if idx > 50 and not sections:
            intro = remaining[:idx].strip()
            if len(intro) > 20:
                sections.append({"title": "_intro", "text": intro, "word_count": len(intro)})
        next_idx = len(remaining)
        if i + 1 < len(heading_data):
            pos = remaining.find(heading_data[i + 1][0], idx + len(ht))
            if pos > 0:
                next_idx = pos
        section_text = remaining[idx:next_idx].strip()
        if section_text.startswith(ht):
            section_text = section_text[len(ht):].strip()
        if section_text:
            sections.append({"title": ht, "text": section_text, "word_count": len(section_text)})
        remaining = remaining[next_idx:]

    return sections


def get_book_meta(book, ncx):
    title = book.get_metadata('DC', 'title')
    creator = book.get_metadata('DC', 'creator')
    chapter_count = sum(1 for e in ncx if e["is_chapter"])
    return {
        "title": title[0][0] if title else "未知",
        "author": creator[0][0] if creator else "未知",
        "chapters": chapter_count
    }


def main():
    parser = argparse.ArgumentParser(description="DeepRead EPUB 提取器")
    parser.add_argument("--book", required=True, help="EPUB 文件名或路径")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--meta", action="store_true")
    parser.add_argument("--chapter")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    books_dir = load_config()
    book_path = resolve_book_path(args.book, books_dir)
    if not book_path:
        error(BOOK_NOT_FOUND, f"找不到书籍: {args.book}",
              hint=f"搜索目录: {books_dir}，请确认文件名正确且文件存在")

    book = epub.read_epub(book_path)
    ncx = parse_ncx(book)

    if args.meta:
        meta = get_book_meta(book, ncx)
        if args.json:
            print(json.dumps(meta, ensure_ascii=False, indent=2))
        else:
            print(f"书名: {meta['title']}")
            print(f"作者: {meta['author']}")
            print(f"章节数: {meta['chapters']}")
        return

    if args.list:
        list_chapters(book, ncx)
        return

    if args.chapter:
        entry = find_chapter(ncx, args.chapter)
        if not entry:
            error(CHAPTER_NOT_FOUND, f"找不到章节: {args.chapter}",
                  hint="使用 --list 查看可用章节列表")

        result = extract_chapter_text(book, entry, ncx)
        if not result:
            print("无法提取章节内容", file=sys.stderr)
            sys.exit(1)

        meta = get_book_meta(book, ncx)
        output = {
            "book": meta,
            "chapter": {
                "index": entry["chapter_num"],
                "title": result["title"],
                "word_count": result["word_count"]
            },
            "sections": result["sections"]
        }

        if args.json:
            print(json.dumps(output, ensure_ascii=False, indent=2))
        else:
            print(f"# {meta['title']} — {result['title']}")
            print(f"# 字数: {result['word_count']} | 小节数: {len(result['sections'])}")
            print()
            for sec in result["sections"]:
                print(f"## {sec['title']} ({sec['word_count']}字)")
                print(sec['text'])
                print()
        return

    parser.print_help()


if __name__ == "__main__":
    main()
