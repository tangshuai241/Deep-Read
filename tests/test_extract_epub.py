"""测试 extract_epub.py EPUB 基础解析"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from extract_epub import (resolve_book_path, parse_ncx, CHAPTER_PATTERN,
                           get_book_meta, clean_html)


def setup_module():
    os.environ["PYTHONIOENCODING"] = "utf-8"


def test_chapter_pattern():
    assert CHAPTER_PATTERN.match("第5章 你的直觉有可能只是错觉")
    assert CHAPTER_PATTERN.match("第38章 思考生活")
    assert not CHAPTER_PATTERN.match("序言")
    assert not CHAPTER_PATTERN.match("第一部分 系统1")


def test_is_chapter():
    chapters = [e for e in [
        {"title": "第1章 测试", "file": "text.html", "is_chapter": True, "is_part": False},
        {"title": "序言", "file": "text.html", "is_chapter": False, "is_part": False},
        {"title": "第一部分", "file": "text.html", "is_chapter": False, "is_part": True},
    ] if e["is_chapter"]]
    assert len(chapters) == 1
    assert chapters[0]["title"] == "第1章 测试"


def test_clean_html():
    html = "<html><body><h1>标题</h1><p>正文内容</p><script>alert('x')</script></body></html>"
    text = clean_html(html)
    assert "标题" in text
    assert "正文内容" in text
    assert "alert" not in text


def test_real_epub_parse():
    """解析真实 EPUB 文件"""
    epub_path = r"E:\A工作\A、中交二航五公司\燕矶长江大桥\Claude Code 项目\思考快与慢.epub"
    if not os.path.exists(epub_path):
        print("  (EPUB 文件不存在，跳过)")
        return

    from ebooklib import epub
    book = epub.read_epub(epub_path)
    assert book is not None

    ncx = parse_ncx(book)
    assert len(ncx) > 0

    chapters = [e for e in ncx if e.get("is_chapter")]
    assert len(chapters) >= 38

    meta = get_book_meta(book, ncx)
    assert meta["chapters"] >= 38
    assert "卡尼曼" in meta["author"] or "Kahneman" in meta["author"]


def test_resolve_book_path():
    books_dir = r"E:\A工作\A、中交二航五公司\燕矶长江大桥\Claude Code 项目"
    # 模糊匹配
    path = resolve_book_path("思考快与慢", books_dir)
    assert path is not None
    assert path.endswith(".epub")

    # 不存在的文件
    path = resolve_book_path("完全不存在的书.epub", books_dir)
    assert path is None
