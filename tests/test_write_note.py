"""测试 write_note.py 笔记 create/update/append/finalize"""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from write_note import (create_note, update_section, append_section,
                         finalize_note, compile_note, slugify, SECTION_MAP,
                         normalize_explore_text, compile_note_content)


def setup_module():
    os.environ["PYTHONIOENCODING"] = "utf-8"


WRITE_DEFAULTS = {
    "author": "", "category": "", "tags": "", "quote": "",
    "understanding": "", "content": "", "explore": "", "path": "",
    "section": "", "chapter": "", "concept": "", "book": ""
}


class Args:
    pass


def make_args(**kwargs):
    args = Args()
    for k, v in WRITE_DEFAULTS.items():
        setattr(args, k, v)
    for k, v in kwargs.items():
        setattr(args, k, v)
    return args


def test_slugify():
    assert slugify("认知放松与真相错觉") == "认知放松与真相错觉"
    assert slugify("test:file?name") == "testfilename"
    assert "\\" not in slugify("a\\b/c")


def test_create_note():
    with tempfile.TemporaryDirectory() as tmp:
        notes_dir = os.path.join(tmp, "笔记")
        os.makedirs(os.path.join(notes_dir, "《测试书》"), exist_ok=True)

        args = make_args(
            book="测试书", concept="测试概念",
            chapter="1.测试章", author="测试作者",
            quote="测试引用文本", understanding="- 测试理解"
        )
        create_note(notes_dir, args)

        book_dir = os.path.join(notes_dir, "《测试书》")
        note_path = os.path.join(book_dir, "测试概念.md")
        assert os.path.exists(note_path)

        with open(note_path, encoding='utf-8') as f:
            content = f.read()

        assert "《测试书》" in content
        assert "测试引用文本" in content
        assert "测试理解" in content
        assert "📖 引用原文" in content
        assert "💭 我的理解" in content


def test_update_note():
    with tempfile.TemporaryDirectory() as tmp:
        notes_dir = os.path.join(tmp, "笔记")
        os.makedirs(os.path.join(notes_dir, "《测试书》"), exist_ok=True)

        # 先创建
        create_note(notes_dir, make_args(book="测试书", concept="更新测试", chapter="1"))
        note_path = os.path.join(notes_dir, "《测试书》", "更新测试.md")

        # 更新
        args = make_args(path=note_path, section="我的理解",
                          content="- 更新后的理解\n- 第二点")
        update_section(args)

        with open(note_path, encoding='utf-8') as f:
            content = f.read()
        assert "更新后的理解" in content
        assert "第二点" in content


def test_append_note():
    with tempfile.TemporaryDirectory() as tmp:
        notes_dir = os.path.join(tmp, "笔记")
        os.makedirs(os.path.join(notes_dir, "《测试书》"), exist_ok=True)

        create_note(notes_dir, make_args(book="测试书", concept="追加测试", chapter="1"))
        note_path = os.path.join(notes_dir, "《测试书》", "追加测试.md")

        append_section(make_args(path=note_path, section="让我想到",
                                  content="- 联想1: 这是测试联想"))

        with open(note_path, encoding='utf-8') as f:
            content = f.read()
        assert "联想1" in content


def test_finalize_note():
    with tempfile.TemporaryDirectory() as tmp:
        notes_dir = os.path.join(tmp, "笔记")
        os.makedirs(os.path.join(notes_dir, "《测试书》"), exist_ok=True)

        create_note(notes_dir, make_args(book="测试书", concept="收尾测试", chapter="1"))
        note_path = os.path.join(notes_dir, "《测试书》", "收尾测试.md")

        finalize_note(make_args(path=note_path, tags="测试标签", explore="待探索问题"))

        with open(note_path, encoding='utf-8') as f:
            content = f.read()
        assert "测试标签" in content
        assert "待探索问题" in content


def test_create_note_decodes_escaped_newlines():
    with tempfile.TemporaryDirectory() as tmp:
        notes_dir = os.path.join(tmp, "笔记")
        os.makedirs(os.path.join(notes_dir, "《测试书》"), exist_ok=True)

        args = make_args(
            book="测试书",
            concept="换行测试",
            chapter='7.字母"B"与数字"13"',
            quote="引用一\\n\\n引用二",
            understanding="第一段\\n\\n第二段"
        )
        create_note(notes_dir, args)

        note_path = os.path.join(notes_dir, "《测试书》", "换行测试.md")
        with open(note_path, encoding='utf-8') as f:
            content = f.read()

        assert "\\n" not in content
        assert "> 引用一\n\n> 引用二" in content
        assert "第一段\n\n第二段" in content
        assert '章节: 7.字母"B"与数字"13"' in content


def test_finalize_splits_explore_items():
    with tempfile.TemporaryDirectory() as tmp:
        notes_dir = os.path.join(tmp, "笔记")
        os.makedirs(os.path.join(notes_dir, "《测试书》"), exist_ok=True)

        create_note(notes_dir, make_args(book="测试书", concept="探索测试", chapter='7.字母"B"与数字"13"'))
        note_path = os.path.join(notes_dir, "《测试书》", "探索测试.md")

        finalize_note(make_args(path=note_path, explore="1. 问题一？2. 问题二？3. 问题三？"))

        with open(note_path, encoding='utf-8') as f:
            content = f.read()

        assert "- 【理解缺口】问题一？" in content
        assert "- 【理解缺口】问题二？" in content
        assert "- 【理解缺口】问题三？" in content
        assert "- 1. 问题一？2." not in content


def test_compile_preserves_chapter_and_normalizes_sections():
    with tempfile.TemporaryDirectory() as tmp:
        note_path = os.path.join(tmp, "note.md")
        with open(note_path, "w", encoding="utf-8") as f:
            f.write(
                "---\n"
                "书名: 《思考快与慢》\n"
                "章节: 7.字母\"B\"与数字\"13\"\n"
                "---\n"
                "## 📖 引用原文\n"
                "> 引用一\\n\\n引用二\n"
                "## 💭 我的理解\n"
                "第一段\\n\\n第二段\n"
                "## 🔗 让我想到\n"
                "## 联想\n"
                "内容\n"
                "## ❓ 待探索\n"
                "- 1. 问题一？2. 问题二？\n"
            )

        compile_note(make_args(path=note_path))

        with open(note_path, encoding="utf-8") as f:
            content = f.read()

        assert '章节: 7.字母"B"与数字"13"' in content
        assert "\\n" not in content
        assert "> 引用一\n\n> 引用二" in content
        assert "### 联想" in content
        assert "\n## 联想\n" not in content
        assert "- 【理解缺口】问题一？" in content
        assert "- 【理解缺口】问题二？" in content


def test_compile_content_adds_precise_links_without_touching_chapter():
    content = (
        "---\n"
        "书名: 《思考快与慢》\n"
        "章节: 7.字母\"B\"与数字\"13\"\n"
        "---\n"
        "## 📖 引用原文\n"
        "> 引用\n\n"
        "## 💭 我的理解\n"
        "WYSIATI 的底层是系统1根据片面信息构建故事，并形成确认偏误。\n\n"
        "## 🔗 让我想到\n"
        "它也能解释光环效应，以及投资中看到利好就加仓。\n\n"
        "## ❓ 待探索\n"
    )
    suggestions = {
        "body_links": [
            {"title": "系统1", "reason": "核心机制", "type": "concept_card"},
            {"title": "确认偏误", "reason": "核心机制", "type": "concept_card"},
            {"title": "光环效应", "reason": "具体表现", "type": "concept_card"},
        ],
        "related_links": [
            {"title": "对基金加仓行为自我分析", "reason": "个人经验：投资场景中的单侧信息判断", "type": "personal_thought"},
        ],
    }

    compiled = compile_note_content(content, suggestions=suggestions)

    assert '章节: 7.字母"B"与数字"13"' in compiled
    assert "[[系统1]]" in compiled
    assert "[[确认偏误]]" in compiled
    assert "[[光环效应]]" in compiled
    assert "### 相关旧笔记 / 延伸阅读" in compiled
    assert "[[对基金加仓行为自我分析]]" in compiled


def test_compile_filters_virtual_link_suggestions(monkeypatch):
    import write_note

    def fake_suggest_links(*args, **kwargs):
        return {
            "body_links": [
                {"title": "系统1", "virtual": True, "type": "concept_card"},
                {"title": "系统1定义", "path": "x", "type": "concept_card"},
                {"title": "同书旧笔记", "path": "n", "type": "reading_note"},
            ],
            "related_links": [
                {"title": "WYSIATI", "virtual": True},
                {"title": "光环效应与群体的智慧", "path": "y", "type": "reading_note"},
            ],
        }

    monkeypatch.setitem(sys.modules, "search_vault", type("M", (), {"suggest_links": fake_suggest_links}))
    suggestions = write_note.load_link_suggestions("C:/tmp/测试笔记.md")

    assert [item["title"] for item in suggestions["body_links"]] == ["系统1定义"]
    assert [item["title"] for item in suggestions["related_links"]] == ["同书旧笔记", "光环效应与群体的智慧"]


def test_compile_links_only_concept_cards_in_body_and_bolds_key_bullets():
    content = (
        "---\n"
        "书名: 《思考快与慢》\n"
        "章节: 8.我们究竟是如何作出判断的？\n"
        "---\n"
        "## 📖 引用原文\n"
        "> 引用\n\n"
        "## 💭 我的理解\n"
        "- 情感启发式与光环效应的统一：底层都是替代机制。\n"
        "\t- 旧读书笔记不要进正文。\n\n"
        "## 🔗 让我想到\n"
        "- 工程现场第一印象会影响后续判断。\n\n"
        "## ❓ 待探索\n"
    )
    suggestions = {
        "body_links": [
            {"title": "光环效应", "reason": "概念卡", "type": "concept_card"},
            {"title": "光环效应与群体的智慧", "reason": "读书笔记", "type": "reading_note"},
        ],
        "related_links": [
            {"title": "对基金加仓行为自我分析", "reason": "个人经验", "type": "personal_thought"},
        ],
    }

    compiled = compile_note_content(content, suggestions=suggestions)

    assert "**情感启发式与[[光环效应]]的统一：**底层都是替代机制。" in compiled
    assert "**工程现场第一印象会影响后续判断。**" in compiled
    assert "[[光环效应与群体的智慧]]" in compiled
    assert "[[对基金加仓行为自我分析]]" in compiled
    assert "旧读书笔记不要进正文" in compiled


def test_normalize_explore_text_dedupes_items():
    result = normalize_explore_text("1. 问题一？2. 问题二？\n- 问题一？")

    assert result == "- 【理解缺口】问题一？\n- 【理解缺口】问题二？"


def test_normalize_explore_text_drops_empty_bullet():
    result = normalize_explore_text("- 1. 问题一？2. 问题二？")

    assert result == "- 【理解缺口】问题一？\n- 【理解缺口】问题二？"


def test_normalize_explore_text_classifies_cognitive_gaps():
    result = normalize_explore_text(
        "情感启发式和光环效应的边界在哪里？\n"
        "- 当我在工作中快速下判断时，怎么识别自己替代了问题？\n"
        "- 后续读到损失厌恶时，回头看它是否也是替代机制？\n"
        "- 【应用缺口】已经分类的问题不要重复套标签"
    )

    assert "- 【理解缺口】情感启发式和光环效应的边界在哪里？" in result
    assert "- 【应用缺口】当我在工作中快速下判断时，怎么识别自己替代了问题？" in result
    assert "- 【连接缺口】后续读到损失厌恶时，回头看它是否也是替代机制？" in result
    assert "- 【应用缺口】已经分类的问题不要重复套标签" in result
    assert "【应用缺口】【应用缺口】" not in result


def test_section_mapping():
    assert SECTION_MAP["我的理解"] == "💭 我的理解"
    assert SECTION_MAP["让我想到"] == "🔗 让我想到"
    assert SECTION_MAP["引用原文"] == "📖 引用原文"
    assert SECTION_MAP["待探索"] == "❓ 待探索"
