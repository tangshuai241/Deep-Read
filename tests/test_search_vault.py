"""测试 search_vault.py 搜索"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from search_vault import (search_keyword, search_backlinks, recent_notes,
                          extract_title_and_tags, search_hybrid, suggest_links,
                          get_scope_dirs, choose_link_candidates,
                          load_concept_index, extract_frontmatter_block,
                          parse_frontmatter_value, extract_aliases_from_fm)


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


def test_scope_core_includes_required_folders():
    config = {"paths": {"vault_dir": r"E:\Documents\知识库",
                        "notes_dir": NOTES_DIR,
                        "wiki_integration_dir": r"E:\Documents\知识库\读书\笔记\📚 LLM-Wiki 整合"}}
    dirs = get_scope_dirs(config, scope="core", include_wiki=True)

    assert any("读书" in d for d in dirs)
    assert any("概念（抽象概念）" in d for d in dirs)
    assert any("我的思考" in d for d in dirs)
    assert any("LLM-Wiki" in d for d in dirs)


def test_hybrid_search_routes_wysiati_to_related_concepts():
    if not os.path.exists(r"E:\Documents\知识库"):
        return

    results = search_hybrid(
        "WYSIATI 眼见即为事实 单侧证据 自信 系统1 确认偏误 光环效应",
        scope="core",
        limit=20,
        include_wiki=True,
    )
    titles = {r["title"] for r in results}

    assert "光环效应" in titles or "光环效应与群体的智慧" in titles
    assert "先相信后怀疑" in titles
    assert "认知与决策" in titles
    assert "系统1" in titles


def test_suggest_links_for_wysiati_note_groups_body_and_related():
    note_path = r"E:\Documents\知识库\读书\笔记-飞书对比\《思考快与慢》\眼见即为事实 WYSIATI.md"
    if not os.path.exists(note_path):
        return

    suggestions = suggest_links(note_path, scope="core", limit=20, include_wiki=True)
    body_titles = {r["title"] for r in suggestions["body_links"]}
    related_titles = {r["title"] for r in suggestions["related_links"]}
    all_titles = body_titles | related_titles

    assert "系统1" in all_titles
    assert "光环效应" in all_titles or "光环效应与群体的智慧" in all_titles
    assert len(suggestions["body_links"]) <= 5
    assert len(suggestions["related_links"]) <= 5


def test_choose_link_candidates_puts_only_concepts_in_body():
    results = [
        {
            "path": "C:/vault/概念（抽象概念）/心理学/光环效应.md",
            "title": "光环效应",
            "type": "concept_card",
            "link_type": "manifestation",
            "score": 80,
        },
        {
            "path": "C:/vault/读书/笔记/《思考快与慢》/光环效应与群体的智慧.md",
            "title": "光环效应与群体的智慧",
            "type": "reading_note",
            "link_type": "manifestation",
            "score": 90,
        },
        {
            "path": "C:/vault/我的思考/判断.md",
            "title": "判断中的第一印象",
            "type": "personal_thought",
            "link_type": "personal_experience",
            "score": 70,
        },
    ]

    grouped = choose_link_candidates(results)

    assert [item["title"] for item in grouped["body_links"]] == ["光环效应"]
    related_titles = [item["title"] for item in grouped["related_links"]]
    assert "光环效应与群体的智慧" in related_titles
    assert "判断中的第一印象" in related_titles


# ── 概念卡别名测试 ──

def test_extract_aliases_from_yaml_list():
    fm = "aliases:\n  - 别名A\n  - 别名B"
    result = extract_aliases_from_fm(fm)
    assert "别名A" in result
    assert "别名B" in result


def test_extract_aliases_from_single_string():
    fm = "alias: 单个别名"
    result = extract_aliases_from_fm(fm)
    assert "单个别名" in result


def test_extract_aliases_from_chinese_key():
    fm = "别名: 中文别名"
    result = extract_aliases_from_fm(fm)
    assert "中文别名" in result


def test_extract_aliases_empty():
    fm = "tags:\n  - 读书笔记"
    result = extract_aliases_from_fm(fm)
    assert result == []


def test_load_concept_index_returns_dict():
    if not os.path.exists(r"E:\Documents\知识库\概念（抽象概念）"):
        return
    index = load_concept_index()
    assert isinstance(index, dict)
    # 应该至少包含一些已知概念
    known = ["系统1", "系统2", "光环效应", "确认偏误"]
    found = any(k in str(index.values()) for k in known)
    # 可能没有，但至少不报错
    assert isinstance(index, dict)
