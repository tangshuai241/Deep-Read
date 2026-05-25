"""测试 search_vault.py 搜索"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from search_vault import search_keyword, search_backlinks, recent_notes, extract_title_and_tags


def setup_module():
    os.environ["PYTHONIOENCODING"] = "utf-8"


NOTES_DIR = r"E:\Documents\知识库\读书\笔记"


def test_search_keyword_finds_results():
    if not os.path.exists(NOTES_DIR):
        print("  (笔记目录不存在，跳过)")
        return

    results = search_keyword(NOTES_DIR, "系统1", max_results=10)
    assert len(results) > 0

    for r in results:
        assert "path" in r
        assert "title" in r
        assert os.path.exists(r["path"])


def test_search_returns_empty_for_nonsense():
    if not os.path.exists(NOTES_DIR):
        return
    results = search_keyword(NOTES_DIR, "xyz完全不存在的关键词12345", max_results=5)
    assert len(results) == 0


def test_extract_title_and_tags():
    """测试 frontmatter 解析"""
    # 使用真实笔记
    notes = Path(NOTES_DIR) if os.path.exists(NOTES_DIR) else None
    if not notes:
        return

    md_files = list(notes.rglob("*.md"))
    if not md_files:
        return

    title, tags, book = extract_title_and_tags(str(md_files[0]))
    assert title  # 至少有个文件名作为标题
    assert isinstance(tags, list)


def test_search_backlinks():
    if not os.path.exists(NOTES_DIR):
        return
    results = search_backlinks(NOTES_DIR, "系统1")
    # 可能有也可能没有反向链接，但不应报错
    assert isinstance(results, list)


def test_recent_notes():
    if not os.path.exists(NOTES_DIR):
        return
    results = recent_notes(NOTES_DIR, limit=5)
    assert len(results) <= 5
    if results:
        assert "mtime" in results[0]
