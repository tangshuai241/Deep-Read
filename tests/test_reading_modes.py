"""测试 reading_modes.py 模式定义和工具函数。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from reading_modes import (
    suggest_mode, get_mode, list_modes, allowed_modes,
    mode_hint_text, mode_note_sections, mode_quality_checks,
    MODE_QUICK_NAMES,
)


def test_suggest_concept_book():
    key, mode, score = suggest_mode("思考快与慢", "personal")
    assert key == "concept_deep_read"
    assert score > 0


def test_suggest_philosophy_book():
    key, mode, score = suggest_mode("被讨厌的勇气", "trial")
    assert key == "proposition_dialogue"
    assert score > 0


def test_suggest_exam_book():
    key, mode, score = suggest_mode("一级建造师教材", "trial")
    assert key == "exam_mastery"


def test_suggest_history_book():
    key, mode, score = suggest_mode("明朝那些事儿", "trial")
    assert key == "historical_context"
    assert mode["name"] == "历史脉络"
    assert score > 0


def test_trial_modes_include_history_context():
    trial_keys = allowed_modes("trial")
    assert len(trial_keys) == 5
    assert "historical_context" in trial_keys
    assert "standard_lookup" not in trial_keys
    assert "literature_experience" not in trial_keys


def test_personal_all_nine_modes():
    personal_keys = allowed_modes("personal")
    assert len(personal_keys) == 9


def test_get_mode_returns_none_for_unknown():
    assert get_mode("nonexistent") is None


def test_get_mode_returns_dict_for_valid():
    mode = get_mode("exam_mastery")
    assert mode["name"] == "考试掌握"
    assert "自测题" in mode["sections"]


def test_mode_hint_returns_string():
    hint = mode_hint_text("method_conversion")
    assert "行动实验" in hint


def test_mode_note_sections_defaults():
    sections = mode_note_sections("concept_deep_read")
    assert "引用原文" in sections
    assert "我的理解" in sections


def test_mode_quality_checks():
    checks = mode_quality_checks("exam_mastery")
    assert "self_test" in checks


def test_quick_name_mapping():
    assert MODE_QUICK_NAMES["考试"] == "exam_mastery"
    assert MODE_QUICK_NAMES["工具"] == "method_conversion"
    assert MODE_QUICK_NAMES["概念"] == "concept_deep_read"
    assert MODE_QUICK_NAMES["历史"] == "historical_context"


def test_list_modes_returns_json_serializable():
    modes = list_modes("personal")
    assert len(modes) == 9
    json_str = json.dumps(modes, ensure_ascii=False)
    parsed = json.loads(json_str)
    assert len(parsed) == 9
