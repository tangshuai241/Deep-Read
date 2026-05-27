#!/usr/bin/env python3
"""
DeepRead 笔记质量检查器

检查 Obsidian 三段式笔记的结构、内容、链接和格式质量。
不自动改写笔记，只生成报告。

用法:
  python note_quality.py --path "...\\眼见即为事实 WYSIATI.md"
  python note_quality.py --path "...\\眼见即为事实 WYSIATI.md" --json
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

# 固定结构检查清单
EXPECTED_SECTIONS = [
    ("📖 引用原文", "引用原文"),
    ("💭 我的理解", "我的理解"),
    ("🔗 让我想到", "让我想到"),
    ("❓ 待探索", "待探索"),
]

EXPLORE_CATEGORIES = ("理解缺口", "应用缺口", "连接缺口")


def load_config():
    config_path = Path(__file__).parent.parent / "config.yaml"
    if config_path.exists():
        try:
            import yaml
            with open(config_path, encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except ImportError:
            pass
    return {}


def extract_frontmatter(content):
    if content.startswith("---\n"):
        end = content.find("\n---", 4)
        if end >= 0:
            return content[:end + 4].strip(), content[end + 4:].lstrip()
    return "", content


def parse_fm_value(fm, key):
    match = re.search(rf"^{re.escape(key)}:\s*(.+)$", fm, re.M)
    return match.group(1).strip().strip('"').strip("'") if match else ""


def extract_section(content, label_variants):
    for label in label_variants:
        pattern = rf"^(?:##|###)\s+{re.escape(label)}\s*\n(.*?)(?=\n(?:##|###)\s+|\Z)"
        match = re.search(pattern, content, re.S | re.M)
        if match:
            return match.group(1).strip()
    return ""


def check_note(note_path, config=None):
    """对单篇笔记执行全部质量检查。返回 (pass, score, errors, warnings, suggestions)。"""
    config = config or load_config()

    if not os.path.exists(note_path):
        return {
            "pass": False, "score": 0,
            "errors": [f"文件不存在: {note_path}"],
            "warnings": [], "suggestions": [],
        }

    errors = []
    warnings = []
    suggestions = []

    with open(note_path, "r", encoding="utf-8") as f:
        content = f.read()

    frontmatter, body = extract_frontmatter(content)
    book = ""
    chapter = ""

    # ── 1. Frontmatter ──
    if not frontmatter:
        errors.append("缺少 frontmatter")
    else:
        book = parse_fm_value(frontmatter, "书名")
        chapter = parse_fm_value(frontmatter, "章节")
        tags_section = "tags:" in frontmatter

        if not book:
            errors.append("frontmatter 缺少 书名")
        if not chapter:
            errors.append("frontmatter 缺少 章节")
        if not tags_section:
            warnings.append("frontmatter 缺少 tags")

    # ── 2. 固定结构 ──
    section_presence = {}
    for heading_variant, key in EXPECTED_SECTIONS:
        found = bool(re.search(rf"^(?:##|###)\s+{re.escape(heading_variant)}", body, re.M))
        section_presence[key] = found
        if not found and key != "待探索":
            errors.append(f"缺少固定段落: {heading_variant}")
        elif not found and key == "待探索":
            warnings.append(f"缺少 {heading_variant} 段落（可选但建议保留）")

    # ── 3. 章节字段检查（不强制替换为小节名）──
    if chapter and "节" in chapter:
        # 章节字段可能含 "第X节"，但主章节名应该是完整的大章名
        # 不报错，只提示
        pass

    # ── 4. 我的理解有实质内容 ──
    understanding = extract_section(body, ["💭 我的理解", "我的理解"])
    if understanding:
        cleaned = re.sub(r"[#\->\|\s\*\[\]\(\)\n]", "", understanding).strip()
        if len(cleaned) < 40:
            warnings.append("💭 我的理解 内容过短（< 40 有效字符）")
    else:
        errors.append("💭 我的理解 无内容")

    # ── 5. 让我想到保留用户个人表达 ──
    connections = extract_section(body, ["🔗 让我想到", "让我想到"])
    if connections:
        # 检查是否全是自动链接（只有 [[...]] 形式，没有实质描述）
        non_link_content = re.sub(r"\[\[.+?\]\]", "", connections)
        non_link_content = re.sub(r"[#\-\|\s\n]", "", non_link_content).strip()
        link_count = len(re.findall(r"\[\[.+?\]\]", connections))
        if link_count > 0 and len(non_link_content) < 30:
            warnings.append("🔗 让我想到 可能只有自动链接，缺少用户个人表达")
        if len(connections.strip()) < 20:
            warnings.append("🔗 让我想到 内容过短")

    # ── 6. 正文概念双链数量 ──
    body_wikilinks = re.findall(r"\[\[(.+?)\]\]", body)
    # 只统计正文部分（排除延伸阅读块）
    extended = extract_section(body, ["相关旧笔记 / 延伸阅读", "延伸阅读"])
    body_only = body.replace(extended, "") if extended else body
    body_wikilinks = re.findall(r"\[\[(.+?)\]\]", body_only)
    if len(body_wikilinks) < 1:
        warnings.append("正文无概念双链，建议 1-5 个")
    elif len(body_wikilinks) > 8:
        warnings.append(f"正文概念双链 {len(body_wikilinks)} 个，偏多（建议 1-5 个）")

    # ── 7. 延伸阅读链接关系说明 ──
    extended_block = extract_section(body, ["相关旧笔记 / 延伸阅读"])
    if extended_block:
        ext_lines = [
            l for l in extended_block.split("\n")
            if l.strip().startswith("-") and "[[" in l
        ]
        for line in ext_lines:
            # 检查 wikilink 之后是否有 — 或 ： 分隔符
            after_link = re.sub(r"^-\s*\[\[.+?\]\]\s*", "", line)
            if not after_link or not re.match(r"^[—：:]", after_link):
                link_match = re.search(r"\[\[(.+?)\]\]", line)
                if link_match:
                    warnings.append(f"延伸阅读链接 [[{link_match.group(1)}]] 缺少关系说明")

    # ── 8. 待探索分类 ──
    explore = extract_section(body, ["❓ 待探索", "待探索"])
    if explore:
        explore_items = [l.strip().lstrip("- ") for l in explore.split("\n") if l.strip().startswith("-")]
        uncategorized = [
            item for item in explore_items
            if not any(f"【{cat}】" in item for cat in EXPLORE_CATEGORIES)
        ]
        if uncategorized:
            suggestions.append(
                f"待探索有 {len(uncategorized)} 项未分类，建议用 "
                f"【理解缺口】/【应用缺口】/【连接缺口】前缀"
            )

    # ── 9. 裸 \\n 和聊天残留 ──
    if "\\n" in content:
        errors.append("存在字面量 \\\\n（应为真实换行）")
    if "\\t" in content:
        errors.append("存在字面量 \\\\t")

    chat_residue_patterns = [
        r"已写入", r"阶段\d", r"费曼输出", r"苏格拉底", r"联想阶段",
        r"笔记草稿已创建", r"\\n\\n已保存", r"现在进入",
    ]
    for pattern in chat_residue_patterns:
        if re.search(pattern, body):
            warnings.append(f"疑似聊天残留: '{pattern}'")
            break  # 只报一次

    # ── 10. 疑似概念未链接 ──
    vault = config.get("paths", {}).get("vault_dir", "")
    if vault:
        concept_dir = os.path.join(vault, "概念（抽象概念）")
        if os.path.exists(concept_dir):
            existing_concepts = set()
            for f in Path(concept_dir).rglob("*.md"):
                existing_concepts.add(os.path.splitext(f.name)[0])

            # 收集别名映射
            try:
                from search_vault import load_concept_index
                concept_index = load_concept_index(config)
            except Exception:
                concept_index = {}

            body_sections = []
            understanding = extract_section(body, ["💭 我的理解", "我的理解"])
            connections = extract_section(body, ["🔗 让我想到", "让我想到"])
            if understanding:
                body_sections.append(understanding)
            if connections:
                body_sections.append(connections)

            body_text = "\n".join(body_sections)
            # 去掉已有的 wikilink 内容
            body_plain = re.sub(r"\[\[.+?\]\]", "", body_text)

            # 检查已知概念是否在正文中以纯文本出现（未链接）
            unlinked = []
            for concept_name in existing_concepts:
                if concept_name in body_plain and f"[[{concept_name}" not in body_text:
                    unlinked.append(concept_name)
            if unlinked:
                suggestions.append(
                    f"疑似概念未链接 ({len(unlinked)} 个): "
                    f"{', '.join(unlinked[:8])}"
                    + (" ..." if len(unlinked) > 8 else "")
                )

    # ── 11. 断开的概念链接 ──
    vault = config.get("paths", {}).get("vault_dir", "")
    if vault:
        all_links = re.findall(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", body)
        for link_target in all_links:
            link_target = link_target.strip()
            if not link_target:
                continue
            # 检查概念卡是否存在
            concept_path = os.path.join(vault, "概念（抽象概念）", f"{link_target}.md")
            if os.path.exists(concept_path):
                continue
            # 检查读书笔记是否存在
            found = False
            for root, dirs, files in os.walk(os.path.join(vault, "读书")):
                if f"{link_target}.md" in files:
                    found = True
                    break
                if any(f"{link_target}.md" in f for f in files):
                    found = True
                    break
            if not found:
                # 检查我的思考
                for root, dirs, files in os.walk(os.path.join(vault, "我的思考")):
                    if f"{link_target}.md" in files:
                        found = True
                        break
            if not found:
                warnings.append(f"概念链接 [[{link_target}]] 在 vault 中未找到对应文件")

    # ── 12. 模式感知质量检查 ──
    reading_mode = ""
    if frontmatter:
        reading_mode = parse_fm_value(frontmatter, "reading_mode")
    if not reading_mode:
        # 尝试从正文推断
        if "考点" in body and "自测" in body:
            reading_mode = "exam_mastery"
        elif "行动清单" in body or "行动实验" in body:
            reading_mode = "method_conversion"
        elif "核心命题" in body and ("我的立场" in body or "反例" in body):
            reading_mode = "proposition_dialogue"

    if reading_mode == "exam_mastery":
        has_self_test = bool(re.search(r"(自测题|自测|待复习|易错)", body))
        if not has_self_test:
            warnings.append("[考试模式] 缺少自测题或待复习内容")
        has_exam_points = bool(re.search(r"(考点|核心理解|易错对比)", body))
        if not has_exam_points:
            suggestions.append("[考试模式] 建议增加考点梳理和核心理解段落")

    elif reading_mode == "method_conversion":
        has_action = bool(re.search(r"(行动清单|行动实验|改造方案|我的场景)", body))
        if not has_action:
            warnings.append("[方法模式] 缺少行动实验或行动清单")
        has_method = bool(re.search(r"(方法提取|SOP|步骤|前提条件)", body))
        if not has_method:
            suggestions.append("[方法模式] 建议增加方法提取和前提条件说明")

    elif reading_mode == "proposition_dialogue":
        has_stance = bool(re.search(r"(我的立场|我的判断|反例|我不同|我同意)", body))
        if not has_stance:
            warnings.append("[命题模式] 缺少个人立场或反例")

    # ── 汇总评分 ──
    score = max(0, 100 - len(errors) * 15 - len(warnings) * 5)
    passed = len(errors) == 0

    return {
        "pass": passed,
        "score": score,
        "errors": errors,
        "warnings": warnings,
        "suggestions": suggestions,
    }


def format_report(result, note_path):
    """人类可读报告"""
    lines = []
    lines.append(f"笔记质量报告: {os.path.basename(note_path)}")
    lines.append(f"状态: {'[PASS] 通过' if result['pass'] else '[FAIL] 未通过'}")
    lines.append(f"得分: {result['score']}/100")
    lines.append("")

    if result["errors"]:
        lines.append(f"错误 ({len(result['errors'])}):")
        for e in result["errors"]:
            lines.append(f"  [ERR] {e}")
        lines.append("")

    if result["warnings"]:
        lines.append(f"警告 ({len(result['warnings'])}):")
        for w in result["warnings"]:
            lines.append(f"[WARN] {w}")
        lines.append("")

    if result["suggestions"]:
        lines.append(f"建议 ({len(result['suggestions'])}):")
        for s in result["suggestions"]:
            lines.append(f"  >> {s}")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="DeepRead 笔记质量检查器")
    parser.add_argument("--path", required=True, help="笔记文件路径")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    result = check_note(args.path)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_report(result, args.path))

    sys.exit(0 if result["pass"] else 1)


if __name__ == "__main__":
    main()
