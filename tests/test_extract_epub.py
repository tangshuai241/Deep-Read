"""测试 extract_epub.py EPUB 基础解析"""
import json
import os
import sys
import zipfile
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from extract_epub import (resolve_book_path, parse_ncx, CHAPTER_PATTERN,
                           chinese_num_to_int,
                           get_book_meta, clean_html, read_epub_tolerant,
                           find_chapter, extract_chapter_text)


def setup_module():
    os.environ["PYTHONIOENCODING"] = "utf-8"


def test_chapter_pattern():
    assert CHAPTER_PATTERN.match("第5章 你的直觉有可能只是错觉")
    assert CHAPTER_PATTERN.match("第38章 思考生活")
    assert CHAPTER_PATTERN.match("第一章 洪武大帝")
    assert CHAPTER_PATTERN.match("第七章 朱棣的选择")
    assert not CHAPTER_PATTERN.match("序言")
    assert not CHAPTER_PATTERN.match("第一部分 系统1")


def test_chinese_num_to_int():
    assert chinese_num_to_int("一") == 1
    assert chinese_num_to_int("十") == 10
    assert chinese_num_to_int("十一") == 11
    assert chinese_num_to_int("二十三") == 23
    assert chinese_num_to_int("一百零二") == 102
    assert chinese_num_to_int("38") == 38


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


def test_resolve_book_path_recursive_and_case_insensitive():
    with tempfile.TemporaryDirectory() as d:
        nested = Path(d) / "books"
        nested.mkdir()
        target = nested / "明朝那些事儿.EPUB"
        target.write_bytes(b"dummy")
        path = resolve_book_path("明朝那些事儿", d)
        assert path == str(target)


def _write_zip_epub(files):
    tmp = tempfile.NamedTemporaryFile(suffix=".epub", delete=False)
    tmp.close()
    with zipfile.ZipFile(tmp.name, "w") as zf:
        for name, content in files.items():
            if isinstance(content, str):
                content = content.encode("utf-8")
            zf.writestr(name, content)
    return tmp.name


def _minimal_container():
    return """<?xml version="1.0"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>"""


def _minimal_opf(extra_manifest="", spine=""):
    return f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>测试书</dc:title>
    <dc:creator>测试作者</dc:creator>
  </metadata>
  <manifest>
    {extra_manifest}
  </manifest>
  <spine>{spine}</spine>
</package>"""


def test_tolerant_reader_parses_ncx_with_chinese_chapter():
    epub_path = _write_zip_epub({
        "META-INF/container.xml": _minimal_container(),
        "OEBPS/content.opf": _minimal_opf(
            '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>'
            '<item id="c1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>'
        ),
        "OEBPS/toc.ncx": """<ncx><navMap>
          <navPoint><navLabel><text>第一章 洪武大帝</text></navLabel><content src="chapter1.xhtml"/></navPoint>
        </navMap></ncx>""",
        "OEBPS/chapter1.xhtml": "<html><body><h1>第一章 洪武大帝</h1><p>这一章讲元末秩序瓦解和朱元璋的选择。</p></body></html>",
    })
    try:
        book = read_epub_tolerant(epub_path)
        ncx = parse_ncx(book)
        assert ncx[0]["chapter_num"] == 1
        result = extract_chapter_text(book, find_chapter(ncx, "一"), ncx)
        assert "朱元璋" in result["sections"][0]["text"]
    finally:
        os.unlink(epub_path)


def test_tolerant_reader_falls_back_to_nav_xhtml():
    epub_path = _write_zip_epub({
        "META-INF/container.xml": _minimal_container(),
        "OEBPS/content.opf": _minimal_opf(
            '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
            '<item id="c1" href="text/ch1.xhtml" media-type="application/xhtml+xml"/>'
        ),
        "OEBPS/nav.xhtml": """<html><body><nav epub:type="toc"><ol>
          <li><a href="text/ch1.xhtml">第一章 开端</a></li>
        </ol></nav></body></html>""",
        "OEBPS/text/ch1.xhtml": "<html><body><h1>第一章 开端</h1><p>正文内容足够长，用来验证 nav.xhtml 目录兜底。</p></body></html>",
    })
    try:
        book = read_epub_tolerant(epub_path)
        ncx = parse_ncx(book)
        assert ncx[0]["title"] == "第一章 开端"
        assert ncx[0]["chapter_num"] == 1
    finally:
        os.unlink(epub_path)


def test_nav_without_chapter_prefix_gets_fallback_numbers():
    epub_path = _write_zip_epub({
        "META-INF/container.xml": _minimal_container(),
        "OEBPS/content.opf": _minimal_opf(
            '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
            '<item id="c1" href="text/ch1.xhtml" media-type="application/xhtml+xml"/>'
        ),
        "OEBPS/nav.xhtml": """<html><body><nav epub:type="toc"><ol>
          <li><a href="text/ch1.xhtml">洪武大帝</a></li>
        </ol></nav></body></html>""",
        "OEBPS/text/ch1.xhtml": "<html><body><h1>洪武大帝</h1><p>正文内容足够长，用来验证没有第几章前缀的目录。</p></body></html>",
    })
    try:
        book = read_epub_tolerant(epub_path)
        ncx = parse_ncx(book)
        assert ncx[0]["title"] == "洪武大帝"
        assert ncx[0]["chapter_num"] == 1
        assert find_chapter(ncx, "1")["title"] == "洪武大帝"
    finally:
        os.unlink(epub_path)


def test_tolerant_reader_falls_back_to_opf_spine():
    epub_path = _write_zip_epub({
        "META-INF/container.xml": _minimal_container(),
        "OEBPS/content.opf": _minimal_opf(
            '<item id="c1" href="ch1.xhtml" media-type="application/xhtml+xml"/>'
            '<item id="c2" href="ch2.xhtml" media-type="application/xhtml+xml"/>',
            '<itemref idref="c1"/><itemref idref="c2"/>'
        ),
        "OEBPS/ch1.xhtml": "<html><body><h1>第一章 起点</h1><p>第一章正文内容足够长，超过最低文本长度要求。</p></body></html>",
        "OEBPS/ch2.xhtml": "<html><body><h1>第二章 转折</h1><p>第二章正文内容足够长，超过最低文本长度要求。</p></body></html>",
    })
    try:
        book = read_epub_tolerant(epub_path)
        ncx = parse_ncx(book)
        assert [e["chapter_num"] for e in ncx if e["is_chapter"]] == [1, 2]
        result = extract_chapter_text(book, find_chapter(ncx, "2"), ncx)
        assert "第二章正文" in result["sections"][0]["text"]
    finally:
        os.unlink(epub_path)
