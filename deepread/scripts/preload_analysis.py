#!/usr/bin/env python3
"""
DeepRead 预读分析 — 对接 4D 拆解管线

在不修改 4D 管线的前提下，读取其产出的 6 份 JSON，
为 DeepRead Agent 生成三层预读上下文：
  L1 紧凑摘要（500 字符，注入 system prompt）
  L2 知识种子（概念/论证，播种 learning_contract）
  L3 完整上下文（按需工具调用）

用法:
  python preload_analysis.py --book "siddhartha" --mode compact  → L1
  python preload_analysis.py --book "siddhartha" --mode seeds    → L2
  python preload_analysis.py --book "siddhartha" --mode full     → L3
  python preload_analysis.py --book "siddhartha" --mode suggest  → 推荐阅读模式
"""

import argparse
import json
import os
import sys
from pathlib import Path

# 4D 拆解输出在书籍所在目录的 analysis/ 子目录
# 默认路径：books/{book}/analysis/
ANALYSIS_SUBDIR = "analysis"

# 可信度阈值：低于此值不自动注入预读
CREDIBILITY_THRESHOLD = 70


def find_analysis_dir(books_dir, book_name):
    """在 books_dir 下模糊匹配书名，返回 analysis/ 目录路径，找不到返回 None。"""
    # 规范化书名（去掉 .epub、空格、特殊字符）
    needle = book_name.replace(".epub", "").replace(".EPUB", "").lower().strip()
    books_path = Path(books_dir)

    if not books_path.exists():
        return None

    # 先精确匹配
    for d in books_path.iterdir():
        if d.is_dir():
            analysis_dir = d / ANALYSIS_SUBDIR
            if analysis_dir.exists():
                if needle in d.name.lower():
                    return analysis_dir

    # 再模糊匹配
    for d in books_path.iterdir():
        if d.is_dir():
            clean = d.name.replace(".epub", "").lower().replace("_", " ").replace("-", " ")
            if needle in clean or clean in needle:
                analysis_dir = d / ANALYSIS_SUBDIR
                if analysis_dir.exists():
                    return analysis_dir

    # 也检查直接放在 books_dir 下的 analysis/ 目录
    direct = books_path / ANALYSIS_SUBDIR
    if direct.exists():
        return direct

    return None


def load_4d_json(analysis_dir):
    """加载 6 份 4D 拆解 JSON。返回 dict，缺少的文件 key 为 None。"""
    files = {
        "preprocess": "preprocess_output.json",
        "skeleton": "agent_a_skeleton.json",
        "thought": "agent_b_thought.json",
        "argument": "agent_c_argument.json",
        "narrative": "agent_d_narrative.json",
        "summary": "summary_verification.json",
    }
    result = {}
    for key, filename in files.items():
        path = analysis_dir / filename
        if path.exists():
            try:
                with open(path, encoding="utf-8") as f:
                    result[key] = json.load(f)
            except (json.JSONDecodeError, IOError):
                result[key] = None
        else:
            result[key] = None
    return result


def _extract_core_conclusion(skeleton):
    """从 agent_a 提取核心结论（一句话）。"""
    if not skeleton:
        return ""
    # 尝试从金字塔结构中取
    pyramid = skeleton.get("金字塔结构") or skeleton.get("金字塔归约", {})
    if isinstance(pyramid, dict):
        core = pyramid.get("全书核心结论", "")
        if isinstance(core, dict):
            # 可能是 {结论, 归约说明} 
            core = core.get("结论") or core.get("总结") or str(core)
        if core:
            return str(core)[:120]
    # 降级：从 MECE 维度中取第一个维度摘要
    mece = skeleton.get("MECE维度分解", {})
    if isinstance(mece, dict):
        for dim_name, dim_data in mece.items():
            if isinstance(dim_data, dict):
                for item in dim_data.get("子项", []):
                    if isinstance(item, dict) and item.get("摘要"):
                        return str(item["摘要"])[:120]
    return ""


def _extract_key_concepts(thought, limit=10):
    """从 agent_b 提取核心概念列表。"""
    concepts = []
    if not thought:
        return concepts
    # 支持多种字段名
    core = thought.get("concept_extraction") or thought.get("core_concepts") or thought.get("concepts") or []
    if isinstance(core, dict):
        # concept_extraction 可能是 dict，值是分类的列表
        core = core.values()
        core = [c for sublist in core for c in (sublist if isinstance(sublist, list) else [sublist])]
    for c in core[:limit]:
        if isinstance(c, dict):
            name = c.get("name") or c.get("concept_id") or c.get("concept", "")
            if name:
                concepts.append({"name": str(name), "category": str(c.get("category", ""))})
    return concepts


def _extract_argument_themes(argument, limit=5):
    """从 agent_c 提取关键论证主题。"""
    themes = []
    if not argument:
        return themes
    chains = argument.get("cross_chapter_argument_chains", [])
    if not chains:
        chains = argument.get("cross_chapter_chains", [])
    if isinstance(chains, dict):
        # 可能是 {chain_id: chain_data} 格式
        chains = list(chains.values())
    if not isinstance(chains, list):
        return themes
    for chain in chains[:limit]:
        if isinstance(chain, dict):
            theme = chain.get("theme") or chain.get("name") or chain.get("title", "")
            if theme:
                themes.append(str(theme)[:80])
    return themes


def _extract_narrative_highlights(narrative):
    """从 agent_d 提取叙事要点。"""
    if not narrative:
        return {}
    fa = narrative.get("framework_analysis", {})
    metaphors = fa.get("core_metaphors", [])
    top_metaphors = []
    for m in metaphors[:3]:
        if isinstance(m, dict):
            top_metaphors.append({"name": m.get("name", ""), "count": m.get("total_occurrences", 0)})

    arc_info = narrative.get("narrative_arc", {})
    return {
        "top_metaphors": top_metaphors,
        "arc_type": str(arc_info.get("type") or arc_info.get("arc_type", ""))[:80],
    }


def _extract_contradictions(summary_verification, limit=4):
    """从 summary_verification 提取矛盾标注。"""
    contradictions = []
    if not summary_verification:
        return contradictions, 0
    credibility = summary_verification.get("6_综合可信度打分", {}).get("总分", 0)
    # 尝试多个嵌套路径
    cross = summary_verification.get("4_交叉验证增强") or summary_verification.get("4_交叉验证_维度间矛盾标注", {})
    items = cross.get("矛盾列表") or cross.get("dimension_contradictions") or cross.get("contradictions", [])

    # 降级：从 5_矛盾标注汇总 提取
    if not items:
        contradiction_summary = summary_verification.get("5_矛盾标注汇总", {})
        if contradiction_summary:
            type_dist = contradiction_summary.get("矛盾类型分布", {})
            for type_name, contr_list in type_dist.items():
                if isinstance(contr_list, list):
                    for c in contr_list:
                        items.append({"type": type_name, "detail": str(c)})
            # 如果有严重性评估，也加进去
            severity = contradiction_summary.get("矛盾严重性评估", {})
            for sev_label, sev_items in severity.items():
                if isinstance(sev_items, list) and sev_items:
                    for c in sev_items:
                        if isinstance(c, str) and "CONTRADICTION" in c:
                            # 提取矛盾ID和描述
                            parts = c.split("(")
                            if len(parts) >= 2:
                                items.append({"type": sev_label.replace("需立即裁决", "严重").replace("建议裁决", "注意").replace("标注即可", "参考"),
                                             "detail": "(" + "(".join(parts[1:])})
    
    for c in items[:limit]:
        if isinstance(c, dict):
            contradictions.append({
                "dimension": str(c.get("type", c.get("dimension", "")))[:60],
                "detail": str(c.get("detail", c.get("description", "")))[:120],
                "suggestion": str(c.get("suggestion", ""))[:80],
            })
    return contradictions, credibility


def generate_compact_summary(data):
    """L1: 生成 ≤500 字符的紧凑摘要，注入 system prompt。"""
    summary = data.get("summary")
    skeleton = data.get("skeleton")
    thought = data.get("thought")
    narrative = data.get("narrative")

    parts = []

    # 书名
    book_title = ""
    if skeleton:
        info = skeleton.get("作品信息", {})
        book_title = info.get("书名", "")
    if not book_title and summary:
        meta = summary.get("meta", {})
        book_title = meta.get("book", "")

    # 核心结论
    conclusion = _extract_core_conclusion(skeleton)
    if conclusion:
        parts.append(f"骨架核心：{conclusion}")

    # 关键数字
    if thought:
        fps = thought.get("first_principles", [])
        concept_ext = thought.get("concept_extraction") or thought.get("core_concepts") or thought.get("concepts") or []
        concept_count = len(concept_ext)
        parts.append(f"{len(fps)}个基础假设，{concept_count}个核心概念")

    # 论证主题
    argument = data.get("argument")
    themes = _extract_argument_themes(argument, 3)
    if themes:
        parts.append(f"论证链：{'、'.join(themes)}")

    # 叙事
    highlights = _extract_narrative_highlights(narrative)
    if highlights.get("top_metaphors"):
        top_m = highlights["top_metaphors"][0]
        parts.append(f"核心隐喻：{top_m['name']}（{top_m['count']}次）")
    if highlights.get("arc_type"):
        parts.append(f"叙事弧线：{highlights['arc_type']}")

    # 可信度 + 矛盾
    contradictions, credibility = _extract_contradictions(summary, 4)
    if credibility > 0:
        parts.append(f"可信度{credibility}/100")
    if contradictions:
        contr_dim = "、".join(c["dimension"][:15] for c in contradictions[:3])
        parts.append(f"{len(contradictions)}个待辨矛盾：{contr_dim}")

    # 模式建议
    mode_hint = suggest_reading_mode(data)
    if mode_hint:
        parts.append(f"建议模式：{mode_hint['primary']}（{mode_hint['reason'][:40]}）")

    compact = "。".join(parts) + "。"
    return compact[:500]


def generate_seeds(data):
    """L2: 生成知识种子清单，播种 learning_contract.knowledge_map。"""
    seeds = {"A_core": [], "B_important": [], "C_evidence": [], "D_application": []}

    # A_core: 第一性原理的前3条
    thought = data.get("thought")
    if thought:
        fps = thought.get("first_principles", [])
        for fp in fps[:3]:
            if isinstance(fp, dict):
                seeds["A_core"].append(fp.get("name", ""))

    # A_core: 核心结论
    skeleton = data.get("skeleton")
    conclusion = _extract_core_conclusion(skeleton)
    if conclusion and conclusion not in seeds["A_core"]:
        seeds["A_core"].append(conclusion[:80])

    # B_important: 核心概念（第4-10）
    concepts = _extract_key_concepts(thought, 10)
    for c in concepts[3:10]:
        seeds["B_important"].append(c["name"])

    # C_evidence: 论证链主题
    argument = data.get("argument")
    themes = _extract_argument_themes(argument, 5)
    for t in themes:
        seeds["C_evidence"].append(t)

    # D_application: 矛盾标注
    summary = data.get("summary")
    if summary:
        contradictions, _ = _extract_contradictions(summary, 4)
        for c in contradictions:
            seeds["D_application"].append(f"辨析：{c['detail'][:60]}")

    return seeds


def generate_full_context(data):
    """L3: 完整上下文，供 Agent 按需加载（工具调用）。"""
    summary = data.get("summary")
    contradictions, credibility = _extract_contradictions(summary, 10)

    return {
        "credibility": credibility,
        "core_conclusion": _extract_core_conclusion(data.get("skeleton")),
        "key_concepts": _extract_key_concepts(data.get("thought"), 25),
        "argument_themes": _extract_argument_themes(data.get("argument"), 10),
        "narrative": _extract_narrative_highlights(data.get("narrative")),
        "contradictions": contradictions,
        "reading_mode_hint": suggest_reading_mode(data),
        "note": "本上下文由 4D 拆解管线生成。矛盾标注仅作参考，不替代个人判断。"
            if credibility >= CREDIBILITY_THRESHOLD
            else "⚠️ 4D拆解可信度低于阈值，以下内容仅供参考，建议持审慎态度。",
    }


def suggest_reading_mode(data):
    """基于 4D 拆解产物推荐 DeepRead 阅读模式。"""
    # 启发式规则：
    # 有密集论证链 → proposition_dialogue
    # 概念密度高（>15个核心概念） → concept_deep_read
    # 有叙事弧线+隐喻 → literature_experience
    # 历史脉络 → historical_context
    # 默认 → concept_deep_read

    argument = data.get("argument")
    thought = data.get("thought")
    narrative = data.get("narrative")
    skeleton = data.get("skeleton")
    preprocess = data.get("preprocess")

    argument_count = len(_extract_argument_themes(argument, 20))
    thought_concepts = _extract_key_concepts(thought, 50)
    concept_count = len(thought_concepts)
    narrative_highlights = _extract_narrative_highlights(narrative)

    # 优先级
    if argument_count >= 3:
        return {"primary": "proposition_dialogue",
                "reason": f"发现{argument_count}条论证链，属于观点密集型著作，命题辨析利于深挖立场和逻辑裂隙",
                "secondary": "concept_deep_read"}
    if concept_count >= 15:
        return {"primary": "concept_deep_read",
                "reason": f"核心概念{concept_count}个，概念密度高，适合概念精读模式逐步拆解",
                "secondary": "proposition_dialogue"}
    if narrative_highlights.get("top_metaphors") and narrative_highlights.get("arc_type"):
        return {"primary": "literature_experience",
                "reason": "叙事结构清晰且有隐喻体系，文学体验模式可深入写作技法分析",
                "secondary": "concept_deep_read"}

    # 尝试从骨架判断
    if skeleton:
        info = skeleton.get("作品信息", {})
        genre = info.get("体裁", "")
        if "历史" in str(genre) or "传记" in str(genre):
            return {"primary": "historical_context", "reason": "历史/传记类作品", "secondary": "concept_deep_read"}

    return {"primary": "concept_deep_read", "reason": "默认概念精读", "secondary": ""}


# ── CLI ──────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="DeepRead 4D 预读分析")
    parser.add_argument("--book", required=True, help="书名（模糊匹配）")
    parser.add_argument("--books-dir", default="", help="书籍目录（默认从 config.yaml 读取）")
    parser.add_argument("--mode", default="compact",
                        choices=["compact", "seeds", "full", "suggest", "all"],
                        help="输出模式")
    parser.add_argument("--json", action="store_true", help="JSON 输出")

    args = parser.parse_args()

    # 解析 books_dir
    books_dir = args.books_dir
    if not books_dir:
        # Try config.yaml relative to script (deepread/scripts/ → ../config.yaml, or repo root)
        script_dir = Path(__file__).resolve().parent
        candidates = [
            script_dir / "config.yaml",
            script_dir.parent.parent / "config.yaml",
            Path.cwd() / "config.yaml",
            Path.home() / ".book-toolchain" / "config.yaml",
        ]
        for c in candidates:
            if c.exists():
                try:
                    import yaml
                    with open(c, encoding="utf-8") as f:
                        conf = yaml.safe_load(f) or {}
                    books_dir = conf.get("paths", {}).get("books_dir", "")
                    if books_dir:
                        break
                except (ImportError, IOError):
                    pass
    if not books_dir:
        books_dir = os.environ.get("BOOK_TOOLCHAIN_BOOKS_DIR", "")
    if not books_dir:
        print(json.dumps({"ok": False, "error": "未设置 books_dir。请在 config.yaml 中配置 paths.books_dir，或设置环境变量 BOOK_TOOLCHAIN_BOOKS_DIR。"}))
        return

    analysis_dir = find_analysis_dir(books_dir, args.book)
    if not analysis_dir:
        result = {"ok": False, "error": f"未找到 '{args.book}' 的 4D 拆解目录。请先运行 4D 拆解管线。"}
        print(json.dumps(result, ensure_ascii=False) if args.json else f"⚠️ {result['error']}")
        return

    data = load_4d_json(analysis_dir)
    if not any(v is not None for v in data.values()):
        result = {"ok": False, "error": f"分析目录存在但无可读的 JSON 文件: {analysis_dir}"}
        print(json.dumps(result, ensure_ascii=False) if args.json else f"⚠️ {result['error']}")
        return

    output = {"ok": True, "book": args.book, "analysis_dir": str(analysis_dir)}

    if args.mode in ("compact", "all"):
        output["compact_summary"] = generate_compact_summary(data)

    if args.mode in ("seeds", "all"):
        output["seeds"] = generate_seeds(data)

    if args.mode in ("full", "all"):
        output["full_context"] = generate_full_context(data)

    if args.mode in ("suggest", "all"):
        output["reading_mode_hint"] = suggest_reading_mode(data)

    if args.json:
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        if "compact_summary" in output:
            print(f"预读摘要: {output['compact_summary']}")
        if "seeds" in output:
            print(f"知识种子: {json.dumps(output['seeds'], ensure_ascii=False, indent=2)}")
        if "reading_mode_hint" in output:
            print(f"推荐模式: {output['reading_mode_hint']['primary']} ({output['reading_mode_hint']['reason']})")


if __name__ == "__main__":
    main()
