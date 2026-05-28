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
import zipfile
import posixpath
import urllib.parse
import xml.etree.ElementTree as ET
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
    needle = book_arg.replace('.epub', '').replace('.EPUB', '').lower()
    for root, dirs, files in os.walk(books_dir):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for f in files:
            if f.lower().endswith('.epub') and needle in f.lower():
                return os.path.join(root, f)
    return None


def clean_html(html_content):
    soup = BeautifulSoup(html_content, 'lxml')
    for tag in soup(['script', 'style']):
        tag.decompose()
    text = soup.get_text()
    text = re.sub(r'\n\s*\n', '\n\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    return text.strip()


def _decode_bytes(data):
    for encoding in ("utf-8", "utf-8-sig", "gb18030", "big5"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="ignore")


class ZipEpubItem:
    def __init__(self, name, content):
        self._name = name
        self._content = content

    def get_name(self):
        return self._name

    def get_content(self):
        return self._content


class ZipEpubBook:
    """EPUB 容错读取器：只读取目录和文本资源，跳过损坏的图片/字体等资源。"""

    def __init__(self, path):
        self.path = path
        self.items = []
        self.metadata = {"title": [], "creator": []}
        self.spine = []
        self.manifest = {}

    def get_items(self):
        return self.items

    def get_metadata(self, namespace, key):
        if namespace != "DC":
            return []
        return [(v, {}) for v in self.metadata.get(key, [])]


def _container_opf_path(zf):
    try:
        raw = zf.read("META-INF/container.xml")
    except Exception:
        return None
    root = ET.fromstring(raw)
    for elem in root.iter():
        if elem.tag.endswith("rootfile"):
            return elem.attrib.get("full-path")
    return None


def _xml_texts(root, local_name):
    values = []
    for elem in root.iter():
        if elem.tag.split("}")[-1] == local_name and elem.text:
            values.append(elem.text.strip())
    return [v for v in values if v]


def _local_name(tag):
    return tag.split("}")[-1]


def _join_epub_path(base_dir, href):
    href = urllib.parse.unquote((href or "").split("#")[0])
    if not href:
        return ""
    return posixpath.normpath(posixpath.join(base_dir, href))


def _parse_opf_into_book(book, opf_raw, opf_dir):
    root = ET.fromstring(opf_raw)
    book.metadata["title"] = _xml_texts(root, "title")
    book.metadata["creator"] = _xml_texts(root, "creator")

    manifest = {}
    spine_ids = []
    for elem in root.iter():
        local = _local_name(elem.tag)
        if local == "item":
            item_id = elem.attrib.get("id")
            href = elem.attrib.get("href", "")
            if item_id and href:
                manifest[item_id] = {
                    "href": _join_epub_path(opf_dir, href),
                    "media_type": elem.attrib.get("media-type", ""),
                    "properties": elem.attrib.get("properties", ""),
                }
        elif local == "itemref":
            idref = elem.attrib.get("idref")
            if idref:
                spine_ids.append(idref)

    book.manifest = manifest
    book.spine = [
        manifest[item_id]["href"]
        for item_id in spine_ids
        if item_id in manifest and manifest[item_id]["href"]
    ]


def read_epub_tolerant(book_path):
    """读取损坏 EPUB 的文本资源。ebooklib 失败时使用。"""
    book = ZipEpubBook(book_path)
    with zipfile.ZipFile(book_path) as zf:
        names = set(zf.namelist())
        opf_path = _container_opf_path(zf)
        opf_dir = posixpath.dirname(opf_path) if opf_path else ""

        if opf_path and opf_path in names:
            opf_raw = zf.read(opf_path)
            try:
                _parse_opf_into_book(book, opf_raw, opf_dir)
            except Exception:
                pass
            book.items.append(ZipEpubItem(opf_path, opf_raw))

        text_exts = (".ncx", ".xhtml", ".html", ".htm", ".xml")
        for name in zf.namelist():
            lower = name.lower()
            if not lower.endswith(text_exts):
                continue
            try:
                content = zf.read(name)
            except Exception as exc:
                print(f"[WARN] 跳过损坏资源: {name} ({exc})", file=sys.stderr)
                continue
            book.items.append(ZipEpubItem(name, content))

        # 有些 OPF manifest 的 href 是相对路径，而 NCX 里的 content src 也是相对 OPF 目录。
        # 这里把文本资源再补一个去掉 OPF 目录的别名，兼容旧的 item.get_name() 精确匹配逻辑。
        if opf_dir:
            aliases = []
            existing = {item.get_name() for item in book.items}
            for item in list(book.items):
                name = item.get_name()
                if name.startswith(opf_dir + "/"):
                    alias = name[len(opf_dir) + 1:]
                    if alias and alias not in existing:
                        aliases.append(ZipEpubItem(alias, item.get_content()))
                        existing.add(alias)
            book.items.extend(aliases)

    return book


def load_epub(book_path):
    try:
        return epub.read_epub(book_path), "ebooklib"
    except Exception as exc:
        print(f"[WARN] ebooklib 读取失败，尝试容错文本模式: {exc}", file=sys.stderr)
        try:
            return read_epub_tolerant(book_path), "zip-tolerant"
        except Exception as fallback_exc:
            error(EPUB_PARSE_FAILED, f"EPUB 解析失败: {fallback_exc}",
                  hint=f"原始错误: {exc}")


CHINESE_DIGITS = {
    "零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
}


def chinese_num_to_int(text):
    """把常见中文数字转成整数，支持 一/十一/二十三/一百零二。"""
    text = text.strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)

    total = 0
    section = 0
    number = 0
    units = {"十": 10, "百": 100, "千": 1000}

    for ch in text:
        if ch in CHINESE_DIGITS:
            number = CHINESE_DIGITS[ch]
        elif ch in units:
            unit = units[ch]
            if number == 0:
                number = 1
            section += number * unit
            number = 0
        else:
            return None

    total += section + number
    return total if total > 0 else 0


CHAPTER_PATTERN = re.compile(r'第([0-9零〇一二两三四五六七八九十百千]+)章')
PART_PATTERN = re.compile(r'第[一二三四五六七八九十百]+部分')
NCX_ENTRY_PATTERN = re.compile(
    r'<navPoint[^>]*>.*?<navLabel>\s*<text>(.*?)</text>\s*</navLabel>.*?<content\s+src="([^"]*)"',
    re.DOTALL
)


def _entry_from_title_file(title, fname, fallback_num=None):
    title = re.sub(r"\s+", " ", BeautifulSoup(title, "lxml").get_text()).strip()
    cm = CHAPTER_PATTERN.match(title)
    pm = PART_PATTERN.match(title)
    chapter_num = chinese_num_to_int(cm.group(1)) if cm else fallback_num
    is_chapter = bool(cm) or fallback_num is not None
    return {
        "title": title,
        "file": fname,
        "is_chapter": is_chapter,
        "is_part": bool(pm),
        "chapter_num": chapter_num,
    }


def _number_entries_when_needed(entries):
    """仅在目录完全没有明确“第X章”时，才给普通内容页自动编号。

    许多 EPUB 的目录前面有“主目录/前言/分卷页/引子”，后面才是“第一章”。
    如果一边有明确章节号，一边又给前言自动编号，就会导致 --chapter 1
    命中“主目录/前言”，而不是真正的“第一章”。
    """
    if any(entry.get("is_chapter") and entry.get("chapter_num") is not None for entry in entries):
        return entries

    numbered = []
    chapter_idx = 0
    for entry in entries:
        if not entry.get("is_part") and _looks_like_content_file(entry.get("file", "")):
            chapter_idx += 1
            entry = dict(entry)
            entry["is_chapter"] = True
            entry["chapter_num"] = chapter_idx
        numbered.append(entry)
    return numbered


def _normalize_epub_ref(ref):
    return urllib.parse.unquote((ref or "").split("#")[0])


def parse_ncx(book):
    """用正则从 NCX 提取所有导航点（扁平列表）。
    返回: [{"title": ..., "file": ..., "is_chapter": bool, "is_part": bool, "chapter_num": int|None}, ...]
    """
    for item in book.get_items():
        if 'ncx' in item.get_name().lower():
            raw = _decode_bytes(item.get_content())
            entries = []
            for m in NCX_ENTRY_PATTERN.finditer(raw):
                title = m.group(1).strip()
                fname = _normalize_epub_ref(m.group(2))
                entries.append(_entry_from_title_file(title, fname))
            if entries:
                return _number_entries_when_needed(entries)
    return parse_nav_or_spine(book)


def parse_nav_or_spine(book):
    nav_entries = parse_nav_xhtml(book)
    if nav_entries:
        return nav_entries
    spine_entries = parse_spine(book)
    if spine_entries:
        return spine_entries
    return synthesize_chapters_from_items(book)


def parse_nav_xhtml(book):
    """解析 EPUB3 nav.xhtml 目录。"""
    for item in book.get_items():
        name = item.get_name().lower()
        if not name.endswith((".xhtml", ".html", ".htm")):
            continue
        soup = BeautifulSoup(item.get_content(), "lxml")
        nav = soup.find("nav", attrs={"epub:type": re.compile(r"\btoc\b")}) or soup.find("nav")
        if not nav:
            continue
        entries = []
        for a in nav.find_all("a"):
            title = a.get_text(" ", strip=True)
            href = _normalize_epub_ref(a.get("href", ""))
            if not title or not href:
                continue
            entries.append(_entry_from_title_file(title, href))
        if entries:
            return _number_entries_when_needed(entries)
    return []


def parse_spine(book):
    """从 OPF spine 合成章节。ZipEpubBook 可用；ebooklib 对象无该字段时自动跳过。"""
    spine = getattr(book, "spine", []) or []
    if not spine:
        return []
    entries = []
    for file_name in spine:
        text = get_content_for_file(book, file_name)
        if not text or len(text.strip()) < 20:
            continue
        title = infer_title_from_file(book, file_name) or Path(file_name).stem
        if PART_PATTERN.match(title):
            entries.append(_entry_from_title_file(title, file_name))
            continue
        entries.append(_entry_from_title_file(title, file_name))
    return _number_entries_when_needed(entries)


def synthesize_chapters_from_items(book):
    """最后兜底：从所有文本文件中合成章节列表。"""
    entries = []
    for item in book.get_items():
        name = item.get_name()
        lower = name.lower()
        if not lower.endswith((".xhtml", ".html", ".htm")):
            continue
        if "nav" in lower or "toc" in lower or "cover" in lower:
            continue
        text = get_content_for_file(book, name)
        if not text or len(text.strip()) < 100:
            continue
        title = infer_title_from_file(book, name) or Path(name).stem
        if PART_PATTERN.match(title):
            entries.append(_entry_from_title_file(title, name))
            continue
        entries.append(_entry_from_title_file(title, name))
    return _number_entries_when_needed(entries)


def infer_title_from_file(book, file_name):
    soup = get_content_soup(book, file_name)
    if not soup:
        return ""
    for selector in ("h1", "h2", "h3", "title"):
        tag = soup.find(selector)
        if tag:
            title = tag.get_text(" ", strip=True)
            if title:
                return title
    return ""


def _looks_like_content_file(file_name):
    lower = (file_name or "").lower()
    if not lower.endswith((".xhtml", ".html", ".htm")):
        return False
    return not any(skip in lower for skip in ("cover", "nav", "toc", "copyright", "titlepage"))


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


def _candidate_file_names(file_name):
    raw = _normalize_epub_ref(file_name)
    if not raw:
        return []
    basename = posixpath.basename(raw)
    candidates = [raw]
    if basename and basename != raw:
        candidates.append(basename)
    return candidates


def get_content_for_file(book, file_name):
    candidates = _candidate_file_names(file_name)
    for item in book.get_items():
        item_name = _normalize_epub_ref(item.get_name())
        item_base = posixpath.basename(item_name)
        if item_name in candidates or item_base in candidates:
            return clean_html(item.get_content())
    return None


def get_content_soup(book, file_name):
    candidates = _candidate_file_names(file_name)
    for item in book.get_items():
        item_name = _normalize_epub_ref(item.get_name())
        item_base = posixpath.basename(item_name)
        if item_name in candidates or item_base in candidates:
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
    target = chinese_num_to_int(str(chapter_ref))
    if target is not None:
        for entry in ncx:
            if entry["is_chapter"] and entry["chapter_num"] == target:
                return entry
    for entry in ncx:
        if str(chapter_ref) in entry["title"] and entry["is_chapter"]:
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

    book, read_mode = load_epub(book_path)
    ncx = parse_ncx(book)
    if not ncx:
        error(EPUB_PARSE_FAILED, "无法从 EPUB 中识别目录或正文章节",
              hint="可尝试换一个 EPUB 版本，或将章节原文粘贴给 Bot")

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
