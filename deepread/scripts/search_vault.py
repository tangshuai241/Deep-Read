#!/usr/bin/env python3
"""
DeepRead Vault 搜索器

支持旧的关键词/反链/最近笔记命令，也支持面向 DeepRead 阶段3和
compile 的 Wiki-aware 候选链接搜索。

用法:
  python search_vault.py --keyword "认知放松"
  python search_vault.py --query "WYSIATI 单侧证据 自信" --mode hybrid --scope core --include-wiki --json
  python search_vault.py --suggest-links --note-path "...\\眼见即为事实 WYSIATI.md" --json
  python search_vault.py --backlinks "认知放松与真相错觉"
  python search_vault.py --recent 10 --scope core
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path


if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

WIKI_DIR_NAME = "📚 LLM-Wiki 整合"

FOLDER_TYPES = {
    "读书": "reading_note",
    "概念（抽象概念）": "concept_card",
    "我的思考": "personal_thought",
}

LINK_TYPE_LABELS = {
    "core_mechanism": "核心机制",
    "manifestation": "具体表现",
    "countermeasure": "应对方法",
    "personal_experience": "个人经验",
    "wiki_hub": "Wiki枢纽",
    "extension": "延伸阅读",
}

# 轻量语义增强：不引入向量库，先覆盖 DeepRead 当前高频概念。
SEMANTIC_TERMS = {
    "wysiati": [
        "WYSIATI", "眼见即为事实", "所见即全部", "只看到一部分", "单侧证据",
        "片面证据", "信息缺失", "自信", "连贯故事", "系统1", "确认偏误",
        "光环效应", "先相信后怀疑", "框架效应", "证据质量", "证据数量",
        "困难问题替代", "自动补全", "反方", "最坏情况",
    ],
    "光环效应": ["光环效应", "第一印象", "特质", "独立判断", "错误关联", "群体智慧"],
    "确认偏误": ["确认偏误", "寻找支持", "已有信念", "先相信后怀疑", "证据"],
    "系统1": ["系统1", "自动", "直觉", "快速", "连贯", "补全", "无法关闭"],
    "系统2": ["系统2", "慢思考", "努力", "质疑", "核查", "反方自问", "独立判断"],
    "认知与决策": ["认知与决策", "判断", "决策", "认知偏差", "系统1", "系统2"],
    "投资": ["投资", "基金", "加仓", "利好", "高位", "跟随", "朋友操作"],
    "加仓": ["加仓", "基金", "投资", "利好", "高位", "跟随", "朋友操作"],
}

RELATION_HINTS = [
    ("core_mechanism", ("系统1", "确认偏误", "先相信后怀疑", "信念偏见", "最省力法则")),
    ("manifestation", ("光环效应", "框架效应", "曝光效应", "熟悉感", "WYSIATI")),
    ("countermeasure", ("系统2", "避免错觉", "独立判断", "反方", "清单", "核查", "慢思考")),
    ("personal_experience", ("加仓", "投资", "工作", "会议", "项目", "PPT", "AI")),
    ("wiki_hub", ("认知与决策", "情绪与自我调节", "改变与行动", "自我与关系", "幸福与意义")),
]

LINKABLE_CONCEPTS = {
    "WYSIATI", "系统1", "系统2", "确认偏误", "光环效应", "先相信后怀疑",
    "框架效应", "信念偏见效应", "最省力法则", "避免错觉最好的方式",
    "认知与决策", "情绪与自我调节", "改变与行动", "自我与关系", "幸福与意义",
}


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


def get_vault_dir(config):
    return config.get("paths", {}).get(
        "vault_dir", os.path.expanduser("~/Documents/知识库")
    )


def get_notes_dir(config):
    return config.get("paths", {}).get(
        "notes_dir", os.path.join(get_vault_dir(config), "读书", "笔记")
    )


def get_wiki_dir(config):
    return config.get("paths", {}).get(
        "wiki_integration_dir", os.path.join(get_notes_dir(config), WIKI_DIR_NAME)
    )


def norm_path(path):
    return str(Path(path))


def iter_markdown_files(base_dirs):
    seen = set()
    for base in base_dirs:
        if not base or not os.path.exists(base):
            continue
        for root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for fname in files:
                if not fname.endswith(".md"):
                    continue
                path = os.path.abspath(os.path.join(root, fname))
                if path in seen:
                    continue
                seen.add(path)
                yield path


def get_scope_dirs(config, scope="notes", include_wiki=False):
    vault_dir = get_vault_dir(config)
    notes_dir = get_notes_dir(config)
    wiki_dir = get_wiki_dir(config)

    if scope == "notes":
        dirs = [notes_dir]
    elif scope == "wiki":
        dirs = [wiki_dir]
    elif scope == "core":
        dirs = [
            os.path.join(vault_dir, "读书"),
            os.path.join(vault_dir, "概念（抽象概念）"),
            os.path.join(vault_dir, "我的思考"),
        ]
    elif scope == "all":
        dirs = [vault_dir]
    else:
        dirs = [notes_dir]

    if include_wiki and wiki_dir not in dirs:
        dirs.append(wiki_dir)
    return dirs


def extract_frontmatter_block(content):
    if content.startswith("---"):
        end = content.find("---", 3)
        if end > 0:
            return content[3:end]
    return ""


def parse_frontmatter_value(fm, key):
    match = re.search(rf"^{re.escape(key)}:\s*(.+)$", fm, re.M)
    return match.group(1).strip().strip('"').strip("'") if match else ""


def parse_tags(fm):
    tags = []
    inline = re.search(r"^tags:\s*\[(.*?)\]\s*$", fm, re.M)
    if inline:
        return [t.strip().strip('"').strip("'") for t in inline.group(1).split(",") if t.strip()]

    lines = fm.splitlines()
    for i, line in enumerate(lines):
        if line.strip() == "tags:":
            for next_line in lines[i + 1:]:
                if next_line.startswith("  - "):
                    tags.append(next_line[4:].strip())
                elif next_line.strip() == "":
                    continue
                else:
                    break
    return tags


def extract_wikilinks(content):
    links = []
    for target in re.findall(r"\[\[([^\]]+)\]\]", content):
        target = target.split("|", 1)[0].strip()
        if target:
            links.append(target)
    return links


def folder_type(filepath, config=None):
    path = norm_path(filepath)
    config = config or load_config()
    wiki_dir = norm_path(get_wiki_dir(config))
    if path.startswith(wiki_dir):
        name = os.path.basename(path)
        if name in {"SCHEMA.md", "index.md", "log.md", "LLM Wiki 使用指南.md", "linking-rules.md"}:
            return "wiki_meta"
        if f"{os.sep}concepts{os.sep}" in path:
            return "wiki_hub"
        if f"{os.sep}books{os.sep}" in path:
            return "wiki_book"
        if f"{os.sep}comparisons{os.sep}" in path:
            return "wiki_comparison"
        return "wiki"

    vault_dir = norm_path(get_vault_dir(config))
    rel = os.path.relpath(path, vault_dir) if path.startswith(vault_dir) else path
    first = rel.split(os.sep, 1)[0]
    return FOLDER_TYPES.get(first, "note")


def extract_title_and_tags(filepath):
    """从 markdown 文件提取 frontmatter 和标题。保持旧测试兼容。"""
    title = os.path.splitext(os.path.basename(filepath))[0]
    tags = []
    book = ""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read(4000)
        fm = extract_frontmatter_block(content)
        tags = parse_tags(fm)
        fm_title = parse_frontmatter_value(fm, "title")
        if fm_title:
            title = fm_title
        book_match = re.search(r"书名:\s*《(.+?)》", content)
        if book_match:
            book = book_match.group(1)
        else:
            book = parse_frontmatter_value(fm, "book")
    except Exception:
        pass
    return title, tags, book


# ── 概念卡别名索引 ──

def load_concept_index(config=None):
    """扫描 vault_dir/概念（抽象概念）下的所有概念卡，建立别名→主标题索引。
    返回 dict: {alias_lower: canonical_title}

    优先级：用户 Obsidian 概念卡 > trial 基础包概念卡
    """
    config = config or load_config()
    vault = get_vault_dir(config)
    index = {}

    # 先加载 trial 基础包（低优先级）
    trial_concepts = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                   "profiles", "trial", "concepts")
    if os.path.exists(trial_concepts):
        _index_concept_dir(trial_concepts, index)

    # 再加载用户 vault 概念卡（高优先级，覆盖 trial 同名卡）
    concept_dir = os.path.join(vault, "概念（抽象概念）")
    if os.path.exists(concept_dir):
        _index_concept_dir(concept_dir, index)

    return index


def _index_concept_dir(directory, index):
    """扫描一个概念卡目录，将主标题和别名添加到索引中。"""
    for filepath in iter_markdown_files([directory]):
        canonical = os.path.splitext(os.path.basename(filepath))[0]
        if not canonical:
            continue

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                fm = extract_frontmatter_block(f.read(3000))
        except Exception:
            fm = ""

        aliases = extract_aliases_from_fm(fm)

        index[canonical.lower()] = canonical
        for alias in aliases:
            key = alias.lower()
            if key not in index:
                index[key] = canonical


def extract_aliases_from_fm(fm):
    """从 frontmatter 提取所有别名。支持多行 YAML 列表和单行形式。"""
    result = []
    for key in ("aliases", "alias", "别名"):
        # 尝试多行 YAML 列表: key:\n  - item1\n  - item2
        multiline = re.search(
            rf"^{re.escape(key)}:\s*\n((?:\s+-\s+.+\n?)+)", fm, re.M
        )
        if multiline:
            for line in multiline.group(1).strip().split("\n"):
                item = re.sub(r"^\s*-\s+", "", line.strip()).strip('"').strip("'")
                if item and not item.startswith("-"):
                    result.append(item)
            continue
        # 尝试单行: key: value 或 key: [a, b, c]
        val = parse_frontmatter_value(fm, key)
        if not val:
            continue
        if val.startswith("[") and val.endswith("]"):
            for item in val[1:-1].split(","):
                item = item.strip().strip('"').strip("'")
                if item:
                    result.append(item)
        else:
            result.append(val)
    return result


def read_doc(filepath, config=None):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    fm = extract_frontmatter_block(content)
    title, tags, book = extract_title_and_tags(filepath)
    result = {
        "path": filepath,
        "title": title,
        "book": book,
        "tags": tags,
        "type": folder_type(filepath, config),
        "wikilinks": extract_wikilinks(content),
        "content": content,
    }
    if result["type"] == "concept_card":
        result["aliases"] = extract_aliases_from_fm(fm)
    return result


def snippet_for(content, keyword, window=50):
    haystack = content.lower()
    needle = keyword.lower()
    idx = haystack.find(needle)
    if idx < 0:
        idx = 0
    start = max(0, idx - window)
    end = min(len(content), idx + len(keyword) + window)
    return "..." + content[start:end].replace("\n", " ").strip() + "..."


def search_keyword(notes_dir, keyword, max_results=20):
    """旧接口：在指定目录内容搜索。"""
    results = []
    kw_lower = keyword.lower()

    for filepath in iter_markdown_files([notes_dir]):
        try:
            doc = read_doc(filepath)
        except Exception:
            continue

        content = doc["content"]
        title_hit = kw_lower in doc["title"].lower()
        content_hit = kw_lower in content.lower()
        if title_hit or content_hit:
            results.append({
                "path": filepath,
                "title": doc["title"],
                "book": doc["book"],
                "tags": doc["tags"],
                "snippet": snippet_for(content, keyword),
                "type": doc["type"],
            })

    return results[:max_results]


def search_backlinks(notes_dir, target_name):
    """搜索所有引用目标笔记的 wikilink。"""
    results = []
    target = target_name.replace(".md", "")

    for filepath in iter_markdown_files([notes_dir]):
        try:
            doc = read_doc(filepath)
        except Exception:
            continue

        matches = [
            link for link in doc["wikilinks"]
            if link == target or link.endswith("/" + target)
        ]
        if matches:
            results.append({
                "path": filepath,
                "title": doc["title"],
                "book": doc["book"],
                "references": len(matches),
                "type": doc["type"],
            })

    return results


def recent_notes(notes_dir, limit=10):
    """最近修改的笔记。"""
    results = []
    for filepath in iter_markdown_files([notes_dir]):
        try:
            title, tags, book = extract_title_and_tags(filepath)
            results.append({
                "path": filepath,
                "title": title,
                "book": book,
                "tags": tags,
                "type": folder_type(filepath),
                "mtime": os.path.getmtime(filepath),
            })
        except OSError:
            continue

    results.sort(key=lambda x: x["mtime"], reverse=True)
    return results[:limit]


def tokenize(text):
    text = str(text or "")
    terms = []
    for token in re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]{2,}", text):
        if len(token.strip()) >= 2:
            terms.append(token.strip())
    return terms


def expand_query_terms(query):
    terms = tokenize(query)
    lowered = query.lower()
    expanded = list(terms)
    for key, values in SEMANTIC_TERMS.items():
        if key.lower() in lowered or any(v.lower() in lowered for v in values):
            expanded.extend(values)
    deduped = []
    seen = set()
    for term in expanded:
        key = term.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(term)
    return deduped


def infer_link_type(doc, query=""):
    text = f"{doc.get('title', '')} {' '.join(doc.get('tags', []))} {doc.get('book', '')}"
    if doc.get("type") in ("wiki_hub", "wiki_book", "wiki_comparison", "wiki"):
        return "wiki_hub" if doc.get("type") == "wiki_hub" else "extension"
    if doc.get("type") == "concept_card":
        if any(term in text for term in ("系统1", "系统2", "确认偏误", "先相信后怀疑", "信念偏见", "最省力法则")):
            return "core_mechanism"
        if any(term in text for term in ("光环效应", "框架效应", "曝光效应", "熟悉感", "WYSIATI")):
            return "manifestation"
        if any(term in text for term in ("避免错觉", "独立判断", "反方", "清单", "核查", "慢思考")):
            return "countermeasure"
        return "core_mechanism"
    if doc.get("type") == "personal_thought":
        return "personal_experience"
    for link_type, terms in RELATION_HINTS:
        if any(term in text for term in terms):
            return link_type
    return "extension"


def relation_reason(doc, link_type):
    label = LINK_TYPE_LABELS.get(link_type, "相关")
    if doc.get("type") == "wiki_hub":
        return f"{label}：用于定位当前笔记所在的知识枢纽"
    if doc.get("type") == "personal_thought":
        return f"{label}：可把阅读概念接到你的真实经验"
    if link_type == "core_mechanism":
        return f"{label}：解释当前概念背后的底层认知机制"
    if link_type == "manifestation":
        return f"{label}：展示同一机制在具体场景中的表现"
    if link_type == "countermeasure":
        return f"{label}：提供对抗偏差或启用慢思考的方法"
    return f"{label}：与当前笔记存在语义或图谱关联"


def score_doc(doc, query_terms, query="", include_content=True):
    title = doc.get("title", "")
    tags = " ".join(doc.get("tags", []))
    links = " ".join(doc.get("wikilinks", []))
    content = doc.get("content", "") if include_content else ""

    title_l = title.lower()
    meta_l = f"{tags} {links} {doc.get('book', '')}".lower()
    content_l = content.lower()

    score = 0
    hits = []
    for term in query_terms:
        t = term.lower()
        if not t:
            continue
        if t in title_l:
            score += 8
            hits.append(term)
        if t in meta_l:
            score += 5
            hits.append(term)
        if t in content_l:
            occurrences = min(content_l.count(t), 4)
            score += occurrences
            hits.append(term)

    doc_type = doc.get("type")
    if doc_type == "wiki_hub":
        score += 7
    elif doc_type == "concept_card":
        score += 16
    elif doc_type == "reading_note":
        score += 3
    elif doc_type == "personal_thought":
        score += 8

    if doc_type == "personal_thought":
        personal_terms = ("投资", "加仓", "工作", "会议", "项目", "生活", "拖延", "AI")
        doc_text = f"{title} {tags} {content[:3000]}"
        if any(term in query for term in personal_terms) and any(term in doc_text for term in personal_terms):
            score += 18
        for term in ("加仓", "基金", "投资", "朋友操作", "跟随"):
            if term in query and term in doc_text:
                score += 20
            if term in query and term in title:
                score += 35

    # WYSIATI 这类英文缩写常常通过中文概念显性连到旧笔记。
    if "wysiati" in query.lower():
        wysiati_related = ("系统1", "确认偏误", "光环效应", "先相信后怀疑", "信念偏见")
        if any(term in f"{title} {tags} {links} {content[:2000]}" for term in wysiati_related):
            score += 8

    return score, sorted(set(hits), key=lambda x: x.lower())


def search_hybrid(query, scope="core", limit=20, include_wiki=True, config=None):
    """轻量混合搜索：关键词 + 标题/标签/wikilink + Wiki 路由 + 语义词扩展。"""
    config = config or load_config()
    dirs = get_scope_dirs(config, scope, include_wiki=include_wiki)
    query_terms = expand_query_terms(query)
    results = []

    for filepath in iter_markdown_files(dirs):
        try:
            doc = read_doc(filepath, config)
        except Exception:
            continue
        if doc.get("type") == "wiki_meta":
            continue
        score, hits = score_doc(doc, query_terms, query=query)
        if score <= 0:
            continue
        link_type = infer_link_type(doc, query=query)
        item = {
            "path": filepath,
            "title": doc["title"],
            "book": doc["book"],
            "tags": doc["tags"],
            "type": doc["type"],
            "link_type": link_type,
            "link_type_label": LINK_TYPE_LABELS.get(link_type, "相关"),
            "score": score,
            "matched_terms": hits[:8],
            "reason": relation_reason(doc, link_type),
            "snippet": snippet_for(doc["content"], hits[0] if hits else query_terms[0] if query_terms else query),
        }
        if doc.get("aliases"):
            item["aliases"] = doc["aliases"]
        results.append(item)

    results.extend(virtual_link_candidates(query, query_terms, results))
    results.sort(key=lambda r: (r["score"], r["type"] == "wiki_hub"), reverse=True)
    return dedupe_results(results)[:limit]


def dedupe_results(results):
    seen_paths = set()
    seen_titles = set()
    deduped = []
    for item in results:
        title = item["title"]
        path = f"virtual:{title}" if item.get("virtual") else os.path.abspath(item["path"])
        title = item["title"]
        if path in seen_paths:
            continue
        # 虚拟概念链接来自 Wiki 枢纽，若已有真实同名页面则取真实页面。
        title_key = title if item.get("virtual") else (title, item.get("type"))
        if title_key in seen_titles:
            continue
        seen_paths.add(path)
        seen_titles.add(title_key)
        deduped.append(item)
    return deduped


def virtual_link_candidates(query, query_terms, actual_results):
    """从 Wiki 枢纽和轻量语义词中提取可链接但未必已有文件的概念名。"""
    actual_titles = {item.get("title", "") for item in actual_results}
    query_text = query.lower()
    candidate_titles = []

    for key, values in SEMANTIC_TERMS.items():
        if key.lower() in query_text or any(v.lower() in query_text for v in values):
            candidate_titles.extend(values)

    for item in actual_results:
        if item.get("type") not in ("wiki_hub", "wiki_book", "wiki_comparison"):
            continue
        try:
            with open(item["path"], "r", encoding="utf-8") as f:
                candidate_titles.extend(extract_wikilinks(f.read()))
        except Exception:
            continue

    wanted = {term.lower() for term in query_terms}
    virtual = []
    seen = set()
    for raw_title in candidate_titles:
        title = raw_title.split("/", 1)[-1].strip()
        title = title.replace(".md", "")
        if not title or title in actual_titles or title in seen:
            continue
        if title not in LINKABLE_CONCEPTS:
            continue
        if len(title) > 30:
            continue
        # 只保留与当前查询或语义扩展明确相关的虚拟概念，避免把整张 Wiki 表都灌进来。
        exact_query_hit = title.lower() in wanted or title in query
        if not exact_query_hit:
            continue
        seen.add(title)
        doc = {"title": title, "tags": [], "book": "", "type": "virtual_concept"}
        link_type = infer_link_type(doc, query=query)
        virtual.append({
            "path": f"virtual://{title}",
            "title": title,
            "book": "",
            "tags": [],
            "type": "virtual_concept",
            "virtual": True,
            "link_type": link_type,
            "link_type_label": LINK_TYPE_LABELS.get(link_type, "相关"),
            "score": 80 if exact_query_hit else 35,
            "matched_terms": [title],
            "reason": relation_reason(doc, link_type),
            "snippet": f"来自 LLM-Wiki 概念路由的候选链接：[[{title}]]",
        })
    return virtual


def read_note_query(note_path):
    with open(note_path, "r", encoding="utf-8") as f:
        content = f.read()
    title = os.path.splitext(os.path.basename(note_path))[0]
    # 用正文核心段落作为查询，避免引用原文噪音过重。
    sections = []
    for heading in ("💭 我的理解", "🔗 让我想到", "❓ 待探索"):
        match = re.search(rf"##\s+{re.escape(heading)}\s*\n(.*?)(?=\n##\s+|\Z)", content, re.S)
        if match:
            sections.append(match.group(1))
    return title + "\n" + "\n".join(sections), content


def choose_link_candidates(results, current_path="", max_body=5, max_related=5):
    current_abs = os.path.abspath(current_path) if current_path else ""
    current_title = os.path.splitext(os.path.basename(current_path))[0] if current_path else ""
    body = []
    related = []
    used_titles = set()

    preferred_order = {
        "core_mechanism": 0,
        "manifestation": 1,
        "countermeasure": 2,
        "wiki_hub": 3,
        "personal_experience": 4,
        "extension": 5,
    }
    results = sorted(results, key=lambda r: (preferred_order.get(r.get("link_type"), 9), -r.get("score", 0)))

    for item in results:
        if current_abs and os.path.abspath(item["path"]) == current_abs:
            continue
        title = item["title"]
        if current_title and (title == current_title or (item.get("virtual") and title in current_title)):
            continue
        if title in used_titles:
            continue
        used_titles.add(title)
        link_type = item.get("link_type", "extension")
        if item.get("type") == "concept_card" and link_type in ("core_mechanism", "manifestation", "countermeasure") and len(body) < max_body:
            body.append(item)
        elif len(related) < max_related:
            related.append(item)
        if len(body) >= max_body and len(related) >= max_related:
            break

    if not any(item.get("link_type") == "personal_experience" for item in related):
        for item in results:
            title = item["title"]
            if item.get("link_type") != "personal_experience":
                continue
            if current_abs and os.path.abspath(item["path"]) == current_abs:
                continue
            if title in used_titles:
                continue
            if len(related) >= max_related:
                related[-1] = item
            else:
                related.append(item)
            break

    return {"body_links": body, "related_links": related}


def suggest_links(note_path, scope="core", limit=20, include_wiki=True, config=None):
    config = config or load_config()
    query, _ = read_note_query(note_path)
    results = search_hybrid(query, scope=scope, limit=max(limit, 40), include_wiki=include_wiki, config=config)
    grouped = choose_link_candidates(results, current_path=note_path)
    grouped["query"] = query[:1000]
    return grouped


def print_json(results):
    output = []
    for r in results:
        item = dict(r)
        if "mtime" in item:
            from datetime import datetime
            item["mtime"] = datetime.fromtimestamp(item["mtime"]).isoformat()
        output.append(item)
    print(json.dumps(output, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description="DeepRead Vault 搜索器")
    parser.add_argument("--keyword", help="旧版关键词搜索，等同 query 的 keyword 模式")
    parser.add_argument("--query", help="新版查询文本，支持 hybrid")
    parser.add_argument("--mode", choices=["keyword", "hybrid"], default="keyword")
    parser.add_argument("--scope", choices=["notes", "core", "wiki", "all"], default="notes")
    parser.add_argument("--include-wiki", action="store_true", help="在 core/notes 搜索时纳入 LLM-Wiki")
    parser.add_argument("--suggest-links", action="store_true", help="基于整篇笔记生成正文链接和延伸链接候选")
    parser.add_argument("--note-path", help="--suggest-links 使用的笔记路径")
    parser.add_argument("--backlinks")
    parser.add_argument("--recent", type=int)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    config = load_config()
    notes_dir = get_notes_dir(config)

    if args.suggest_links:
        if not args.note_path or not os.path.exists(args.note_path):
            print("必须提供存在的 --note-path", file=sys.stderr)
            sys.exit(1)
        output = suggest_links(
            args.note_path,
            scope=args.scope if args.scope != "notes" else "core",
            limit=args.limit,
            include_wiki=True,
            config=config,
        )
        if args.json:
            print(json.dumps(output, ensure_ascii=False, indent=2))
        else:
            print("正文建议链接:")
            for item in output["body_links"]:
                print(f"- [[{item['title']}]] — {item['reason']}")
            print("\n相关旧笔记 / 延伸阅读:")
            for item in output["related_links"]:
                print(f"- [[{item['title']}]] — {item['reason']}")
        return

    if args.query:
        if args.mode == "hybrid":
            results = search_hybrid(
                args.query, scope=args.scope, limit=args.limit,
                include_wiki=args.include_wiki, config=config
            )
        else:
            dirs = get_scope_dirs(config, args.scope, include_wiki=args.include_wiki)
            results = []
            for base in dirs:
                results.extend(search_keyword(base, args.query, args.limit))
            results = dedupe_results(results)[:args.limit]
    elif args.keyword:
        # 旧参数保持 notes 默认行为；显式 scope/core 时走多目录。
        if args.scope == "notes" and not args.include_wiki:
            results = search_keyword(notes_dir, args.keyword, args.limit)
        else:
            dirs = get_scope_dirs(config, args.scope, include_wiki=args.include_wiki)
            results = []
            for base in dirs:
                results.extend(search_keyword(base, args.keyword, args.limit))
            results = dedupe_results(results)[:args.limit]
    elif args.backlinks:
        dirs = get_scope_dirs(config, args.scope, include_wiki=args.include_wiki)
        results = []
        for base in dirs:
            results.extend(search_backlinks(base, args.backlinks))
        results = dedupe_results(results)
    elif args.recent:
        dirs = get_scope_dirs(config, args.scope, include_wiki=args.include_wiki)
        results = []
        for base in dirs:
            results.extend(recent_notes(base, args.recent))
        results.sort(key=lambda x: x["mtime"], reverse=True)
        results = dedupe_results(results)[:args.recent]
    else:
        parser.print_help()
        return

    if args.json:
        print_json(results)
    else:
        for i, r in enumerate(results):
            book_info = f" [{r.get('book', '')}]" if r.get("book") else ""
            type_info = f" ({r.get('link_type_label') or r.get('type', '')})"
            print(f"{i+1}. [[{r['title']}]]{book_info}{type_info}")
            if "reason" in r:
                print(f"   {r['reason']}")
            if "snippet" in r:
                print(f"   {r['snippet'][:140]}")
            if "references" in r:
                print(f"   引用数: {r['references']}")


if __name__ == "__main__":
    main()
