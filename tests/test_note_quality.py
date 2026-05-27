"""测试 note_quality.py 笔记质量检查器"""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from note_quality import check_note, extract_frontmatter, extract_section


def setup_module():
    os.environ["PYTHONIOENCODING"] = "utf-8"


def _write_temp_note(content):
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8")
    tmp.write(content)
    tmp.close()
    return tmp.name


def test_standard_note_passes():
    content = """---
书名: 《思考快与慢》
章节: 7.字母"B"与数字"13"
tags:
  - 读书笔记
  - 思考
---
## 📖 引用原文
> 系统1会自动补全缺失的信息，构建一个连贯的故事。

> 我们对证据质量的判断，独立于对结论信心的判断。

## 💭 我的理解
- **系统1的补全机制**是WYSIATI的认知底层：它不等待缺失信息，而是用已有信息编造连贯叙事。
    - 这意味着我们经常在"不知道"的情况下产生"确信"的感觉。

## 🔗 让我想到
- **工程现场的第一印象问题**：第一次去工地看到进度至上/现场杂乱，会建立错误基准线。
    - 这跟光环效应中"第一印象影响后续独立判断"是同一机制。

## ❓ 待探索
- 【理解缺口】系统1补全在什么条件下会被系统2拦截？
- 【应用缺口】在施工现场如何训练自己先查看最差区域而非最好区域？
"""
    path = _write_temp_note(content)
    try:
        result = check_note(path, config={})
        assert result["pass"] is True
        assert result["score"] >= 80
        assert len(result["errors"]) == 0
    finally:
        os.unlink(path)


def test_missing_frontmatter_reports_error():
    content = """## 📖 引用原文
> 测试原文

## 💭 我的理解
测试理解

## 🔗 让我想到
测试联想

## ❓ 待探索
- 【理解缺口】测试问题
"""
    path = _write_temp_note(content)
    try:
        result = check_note(path, config={})
        assert result["pass"] is False
        assert any("frontmatter" in e.lower() for e in result["errors"])
    finally:
        os.unlink(path)


def test_missing_section_reports_error():
    content = """---
书名: 《测试》
章节: 1.测试
tags:
  - 读书笔记
---
## 📖 引用原文
> 测试原文

## 🔗 让我想到
测试联想
"""
    path = _write_temp_note(content)
    try:
        result = check_note(path, config={})
        assert not result["pass"]
        assert any("我的理解" in e for e in result["errors"])
    finally:
        os.unlink(path)


def test_uncategorized_explore_items_suggest_categories():
    content = """---
书名: 《测试》
章节: 1.测试
tags:
  - 读书笔记
---
## 📖 引用原文
> 测试原文

## 💭 我的理解
这里是关于测试的理解，内容足够长才能通过实质性检查，所以需要多写一些文字来满足最低字符数要求。

## 🔗 让我想到
这里的联想内容也足够长，包含一些个人化的表达和具体场景描述。

## ❓ 待探索
- 未分类的问题一
- 未分类的问题二
- 【理解缺口】已分类的问题
"""
    path = _write_temp_note(content)
    try:
        result = check_note(path, config={})
        assert any("未分类" in s for s in result["suggestions"])
    finally:
        os.unlink(path)


def test_extend_links_without_description_warns():
    content = """---
书名: 《测试》
章节: 1.测试
tags:
  - 读书笔记
---
## 📖 引用原文
> 测试原文

## 💭 我的理解
这里是对测试的深入理解，包含了足够多的实质内容来通过最小长度检查。

## 🔗 让我想到
测试联想内容，也足够丰富，包含了具体的个人经验和场景描述。

### 相关旧笔记 / 延伸阅读
- [[光环效应]]
- [[系统1]] — 有说明的链接
"""
    path = _write_temp_note(content)
    try:
        result = check_note(path, config={})
        assert any("光环效应" in w and "关系说明" in w for w in result["warnings"])
    finally:
        os.unlink(path)


def test_bare_newline_escapes_reported():
    content = """---
书名: 《测试》
章节: 1.测试
tags:
  - 读书笔记
---
## 📖 引用原文
> 测试原文

## 💭 我的理解
第一段\\n\\n第二段，这里有字面量换行符。

## 🔗 让我想到
测试联想内容足够长，包含了具体的场景描述。

## ❓ 待探索
- 【理解缺口】测试
"""
    path = _write_temp_note(content)
    try:
        result = check_note(path, config={})
        assert any("\\\\n" in e for e in result["errors"])
    finally:
        os.unlink(path)


def test_json_output_contains_required_fields():
    content = """---
书名: 《测试》
章节: 1.测试
tags:
  - 读书笔记
---
## 📖 引用原文
> 测试原文

## 💭 我的理解
这里是对测试的深入理解，需要足够多的文字来通过检查。

## 🔗 让我想到
测试联想内容，包含了个人经验和具体场景的描述。

## ❓ 待探索
- 【理解缺口】测试问题
"""
    path = _write_temp_note(content)
    try:
        result = check_note(path, config={})
        assert "pass" in result
        assert "score" in result
        assert "errors" in result
        assert "warnings" in result
        assert "suggestions" in result
        assert isinstance(result["score"], int)
    finally:
        os.unlink(path)


def test_extract_section_finds_variants():
    body = """## 📖 引用原文
quote content here

## 💭 我的理解
understanding content here

## 🔗 让我想到
connection content here
"""
    assert "quote content" in extract_section(body, ["📖 引用原文", "引用原文"])
    assert "understanding content" in extract_section(body, ["💭 我的理解", "我的理解"])
    assert extract_section(body, ["❓ 待探索"]) == ""


def test_chat_residue_detected():
    content = """---
书名: 《测试》
章节: 1.测试
tags:
  - 读书笔记
---
## 📖 引用原文
> 测试原文

## 💭 我的理解
这里是理解内容，长度足够通过实质性检查。

## 🔗 让我想到
阶段3联想已写入文件，这里是用户的个人经验和场景描述。

## ❓ 待探索
- 【理解缺口】测试问题
"""
    path = _write_temp_note(content)
    try:
        result = check_note(path, config={})
        assert any("阶段3" in w or "聊天残留" in w for w in result["warnings"])
    finally:
        os.unlink(path)


def test_history_mode_requires_timeline_and_judgment():
    content = """---
书名: 《明朝那些事儿》
章节: 第一章
reading_mode: historical_context
tags:
  - 读书笔记
---
## 📖 引用原文
> 这是关于明朝开端的一段历史叙述。

## 💭 我的理解
这一章主要在讲人物选择和时代环境之间的关系，朱元璋并不是凭空出现的英雄，而是在乱世结构中逐渐形成自己的判断和组织方式。

## 🔗 让我想到
这让我想到现实中的组织上升期，个人能力固然重要，但更关键的是能否识别环境里的机会和约束。

## ❓ 待探索
- 【理解缺口】这一时期不同势力的资源差异到底在哪里？
"""
    path = _write_temp_note(content)
    try:
        result = check_note(path, config={})
        assert any("时间线" in w for w in result["warnings"])
        assert any("个人判断" in w or "现实镜鉴" in w for w in result["warnings"])
    finally:
        os.unlink(path)


def test_history_mode_good_note_passes_mode_checks():
    content = """---
书名: 《明朝那些事儿》
章节: 第一章
reading_mode: historical_context
tags:
  - 读书笔记
---
## 📖 引用原文
> 这是关于明朝开端的一段历史叙述。

## 💭 我的理解
- **时间线**：先是元末秩序瓦解，地方力量各自扩张，然后朱元璋在竞争中逐渐完成组织整合。
- **关键转折**：人物选择并不只是性格问题，也受到制度、资源和军事环境的共同推动。

## 🔗 让我想到
- **我的判断**：历史阅读不能只看谁更聪明，还要看环境给了谁更稳定的反馈循环。这个现实镜鉴对理解组织竞争很有帮助。

## ❓ 待探索
- 【理解缺口】元末地方势力为什么没有形成更稳定的联盟？
"""
    path = _write_temp_note(content)
    try:
        result = check_note(path, config={})
        assert not any("历史脉络模式" in w for w in result["warnings"])
    finally:
        os.unlink(path)
