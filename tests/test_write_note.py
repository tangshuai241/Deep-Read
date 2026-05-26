"""测试 write_note.py 笔记 create/update/append/finalize"""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from write_note import (create_note, update_section, append_section,
                         finalize_note, compile_note, slugify, SECTION_MAP,
                         normalize_explore_text)


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

        assert "- 问题一？" in content
        assert "- 问题二？" in content
        assert "- 问题三？" in content
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
        assert "- 问题一？" in content
        assert "- 问题二？" in content


def test_normalize_explore_text_dedupes_items():
    result = normalize_explore_text("1. 问题一？2. 问题二？\n- 问题一？")

    assert result == "- 问题一？\n- 问题二？"


def test_normalize_explore_text_drops_empty_bullet():
    result = normalize_explore_text("- 1. 问题一？2. 问题二？")

    assert result == "- 问题一？\n- 问题二？"


def test_section_mapping():
    assert SECTION_MAP["我的理解"] == "💭 我的理解"
    assert SECTION_MAP["让我想到"] == "🔗 让我想到"
    assert SECTION_MAP["引用原文"] == "📖 引用原文"
    assert SECTION_MAP["待探索"] == "❓ 待探索"
