#!/usr/bin/env python3
"""
DeepRead 章节学习契约

契约负责记录一节/一章的知识地图、阶段通过条件和用户理解证据。
它不直接写 Obsidian 笔记，也不更新 LLM-Wiki，只给 Agent/Claude Code
提供共同的学习路线。
"""

import argparse
import json
import os
from datetime import datetime
from pathlib import Path


POINT_GROUPS = ("A_core", "B_important", "C_evidence", "D_application")
VALID_STATUSES = {"pending", "covered", "unclear", "passed"}
REQUIRED_STAGE_EVENTS = {
    "boundary_or_counterexample": "至少完成 1 个边界/反例追问",
    "application_probe": "至少完成 1 个现实应用追问",
    "old_note_connection": "至少产生 1 条旧知识关联",
    "personal_association": "至少产生 1 条用户个人真实场景联想",
}


def load_config():
    config_path = Path(__file__).parent.parent / "config.yaml"
    if config_path.exists():
        try:
            import yaml
            with open(config_path, encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except ImportError:
            return {}
    return {}


def get_state_root():
    config = load_config()
    configured = config.get("paths", {}).get("state_dir", "")
    if configured:
        return Path(configured)
    return Path(__file__).parent.parent / "state"


def get_user_dir(user="default"):
    return get_state_root() / user


def get_contract_path(user="default"):
    return get_user_dir(user) / "learning_contract.json"


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def normalize_points(raw):
    if not raw:
        return []
    if isinstance(raw, list):
        items = raw
    else:
        text = str(raw).strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
            items = parsed if isinstance(parsed, list) else [parsed]
        except json.JSONDecodeError:
            items = [part.strip() for part in text.replace("，", ",").split(",")]

    result = []
    seen = set()
    for item in items:
        if isinstance(item, dict):
            title = str(item.get("title") or item.get("name") or "").strip()
            desc = str(item.get("description") or item.get("desc") or "").strip()
        else:
            title = str(item).strip()
            desc = ""
        if not title or title in seen:
            continue
        seen.add(title)
        result.append({
            "title": title,
            "description": desc,
            "status": "pending",
            "evidence": [],
            "updated_at": None,
        })
    return result


def default_contract(book="", chapter="", section="", goal="理解",
                     profile="personal", book_type="", reading_mode="concept_deep_read",
                     mode_reason=""):
    return {
        "version": "1.1",
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "profile": profile,
        "scope": {
            "book": book or "",
            "chapter": chapter or "",
            "section": section or "",
            "goal": goal or "理解",
            "book_type": book_type or "",
            "reading_mode": reading_mode or "concept_deep_read",
            "mode_reason": mode_reason or "",
        },
        "knowledge_map": {
            "A_core": [],
            "B_important": [],
            "C_evidence": [],
            "D_application": [],
        },
        "stage_events": {
            "boundary_or_counterexample": [],
            "application_probe": [],
            "old_note_connection": [],
            "personal_association": [],
        },
        "note_deposits": {
            "understanding": [],
            "associations": [],
            "explore": [],
        },
        "notes": [],
    }


def load_contract(user="default"):
    path = get_contract_path(user)
    if not path.exists():
        return default_contract()
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def save_contract(contract, user="default"):
    contract["updated_at"] = now_iso()
    path = get_contract_path(user)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(contract, f, ensure_ascii=False, indent=2)
    return path


def init_contract(args):
    contract = default_contract(
        args.book, args.chapter, args.section, args.goal,
        profile=getattr(args, "profile", "personal"),
        book_type=getattr(args, "book_type", ""),
        reading_mode=getattr(args, "reading_mode", "concept_deep_read"),
        mode_reason=getattr(args, "mode_reason", ""),
    )
    for group in POINT_GROUPS:
        contract["knowledge_map"][group] = normalize_points(getattr(args, group))
    path = save_contract(contract, args.user)
    return {"ok": True, "path": str(path), "contract": contract}


def find_point(contract, title):
    for group in POINT_GROUPS:
        for point in contract.get("knowledge_map", {}).get(group, []):
            if point.get("title") == title:
                return group, point
    return None, None


def add_point(contract, group, title):
    if group not in POINT_GROUPS:
        group = "B_important"
    group_points = contract.setdefault("knowledge_map", {}).setdefault(group, [])
    for point in group_points:
        if point.get("title") == title:
            return point
    point = {
        "title": title,
        "description": "",
        "status": "pending",
        "evidence": [],
        "updated_at": None,
    }
    group_points.append(point)
    return point


def append_unique(items, value):
    if value and value not in items:
        items.append(value)


def update_contract(args):
    contract = load_contract(args.user)
    changed = False

    if args.point:
        group, point = find_point(contract, args.point)
        if point is None:
            point = add_point(contract, args.group, args.point)
            group = args.group
        status = args.status or "covered"
        if status not in VALID_STATUSES:
            return {"ok": False, "error": f"无效 status: {status}"}
        point["status"] = status
        point["updated_at"] = now_iso()
        if args.evidence:
            append_unique(point.setdefault("evidence", []), args.evidence)
        changed = True

    if args.event:
        if args.event not in REQUIRED_STAGE_EVENTS:
            return {"ok": False, "error": f"无效 event: {args.event}"}
        append_unique(contract.setdefault("stage_events", {}).setdefault(args.event, []),
                      args.evidence or args.point or args.event)
        changed = True

    if args.deposit:
        deposits = contract.setdefault("note_deposits", {})
        append_unique(deposits.setdefault(args.deposit, []),
                      args.evidence or args.point or args.deposit)
        changed = True

    if args.note:
        append_unique(contract.setdefault("notes", []), args.note)
        changed = True

    if changed:
        path = save_contract(contract, args.user)
        return {"ok": True, "path": str(path), "contract": contract}
    return {"ok": False, "error": "没有可更新内容"}


def count_status(points, statuses):
    return sum(1 for point in points if point.get("status") in statuses)


def check_feynman(contract):
    a_points = contract.get("knowledge_map", {}).get("A_core", [])
    total = len(a_points)
    passed = count_status(a_points, {"covered", "passed"})
    ratio = 1.0 if total == 0 else passed / total
    missing = [p.get("title") for p in a_points if p.get("status") not in {"covered", "passed"}]
    ok = ratio >= 0.8 and all(p.get("evidence") for p in a_points if p.get("status") in {"covered", "passed"})
    return ok, {
        "a_core_total": total,
        "a_core_covered": passed,
        "coverage_ratio": round(ratio, 2),
        "missing": missing,
        "requirements": ["A 类核心点至少覆盖 80%", "已覆盖 A 点必须有用户自己的解释证据"],
    }


def check_socratic(contract):
    km = contract.get("knowledge_map", {})
    ab_points = km.get("A_core", []) + km.get("B_important", [])
    deepened = count_status(ab_points, {"passed"})
    events = contract.get("stage_events", {})
    has_boundary = bool(events.get("boundary_or_counterexample"))
    has_application = bool(events.get("application_probe"))
    ok = deepened >= 2 and has_boundary and has_application
    return ok, {
        "deepened_points": deepened,
        "has_boundary_or_counterexample": has_boundary,
        "has_application_probe": has_application,
        "requirements": ["至少深挖 2 个 A/B 点", REQUIRED_STAGE_EVENTS["boundary_or_counterexample"], REQUIRED_STAGE_EVENTS["application_probe"]],
    }


def check_associate(contract):
    events = contract.get("stage_events", {})
    deposits = contract.get("note_deposits", {})
    has_old = bool(events.get("old_note_connection"))
    has_personal = bool(events.get("personal_association"))
    deposited = bool(deposits.get("associations"))
    ok = has_old and has_personal and deposited
    return ok, {
        "has_old_note_connection": has_old,
        "has_personal_association": has_personal,
        "association_deposited": deposited,
        "requirements": [REQUIRED_STAGE_EVENTS["old_note_connection"], REQUIRED_STAGE_EVENTS["personal_association"], "联想必须写入让我想到"],
    }


def check_wrapup(contract):
    f_ok, f_detail = check_feynman(contract)
    s_ok, s_detail = check_socratic(contract)
    a_ok, a_detail = check_associate(contract)
    return f_ok and s_ok and a_ok, {
        "feynman": f_detail,
        "socratic": s_detail,
        "associate": a_detail,
    }


def check_contract(args):
    contract = load_contract(args.user)
    stage = args.stage or contract.get("current_stage") or "wrapup"
    if stage == "feynman":
        ok, detail = check_feynman(contract)
    elif stage == "socratic":
        ok, detail = check_socratic(contract)
    elif stage == "associate":
        ok, detail = check_associate(contract)
    elif stage == "wrapup":
        ok, detail = check_wrapup(contract)
    else:
        return {"ok": False, "stage": stage, "error": f"不支持的阶段: {stage}"}
    return {"ok": ok, "stage": stage, "detail": detail}


def report_contract(args):
    contract = load_contract(args.user)
    km = contract.get("knowledge_map", {})
    learned = []
    unclear = []
    pending = []
    for group in POINT_GROUPS:
        for point in km.get(group, []):
            item = {
                "group": group,
                "title": point.get("title", ""),
                "status": point.get("status", "pending"),
                "evidence": point.get("evidence", []),
            }
            if item["status"] == "passed":
                learned.append(item)
            elif item["status"] == "unclear":
                unclear.append(item)
            elif item["status"] == "pending":
                pending.append(item)
            else:
                learned.append(item)
    a_missing = [
        p.get("title", "")
        for p in km.get("A_core", [])
        if p.get("status") not in {"covered", "passed"}
    ]
    return {
        "ok": True,
        "scope": contract.get("scope", {}),
        "learned": learned,
        "unclear": unclear,
        "pending": pending,
        "missing_a_core": a_missing,
        "stage_events": contract.get("stage_events", {}),
        "note_deposits": contract.get("note_deposits", {}),
        "suggested_explore": [f"继续澄清：{title}" for title in a_missing],
    }


def print_result(result, as_json=False):
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    if not result.get("ok"):
        print(f"失败: {result.get('error', '未知错误')}")
        return
    if "contract" in result:
        c = result["contract"]
        scope = c.get("scope", {})
        print(f"学习契约: 《{scope.get('book', '')}》 {scope.get('chapter', '')} {scope.get('section', '')}".strip())
        for group in POINT_GROUPS:
            print(f"{group}: {len(c.get('knowledge_map', {}).get(group, []))} 项")
    elif "detail" in result:
        print(f"阶段检查 {result.get('stage')}: {'通过' if result.get('ok') else '未通过'}")
        print(json.dumps(result.get("detail", {}), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))


def build_parser():
    parser = argparse.ArgumentParser(description="DeepRead 章节学习契约")
    parser.add_argument("--user", default="default", help="用户 ID")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    sub = parser.add_subparsers(dest="command")

    p_init = sub.add_parser("init", help="初始化学习契约")
    p_init.add_argument("--book", default="")
    p_init.add_argument("--chapter", default="")
    p_init.add_argument("--section", default="")
    p_init.add_argument("--goal", default="理解")
    p_init.add_argument("--profile", default="personal", choices=("trial", "personal"))
    p_init.add_argument("--book-type", default="", help="书籍类型，如 方法工具型/概念思想型")
    p_init.add_argument("--reading-mode", default="concept_deep_read", help="阅读模式键名")
    p_init.add_argument("--mode-reason", default="", help="模式选择依据")
    for group in POINT_GROUPS:
        p_init.add_argument(f"--{group}", default="", help="逗号分隔或 JSON 数组")

    p_show = sub.add_parser("show", help="显示当前学习契约")

    p_update = sub.add_parser("update", help="更新知识点、阶段事件或笔记沉淀")
    p_update.add_argument("--point", default="", help="知识点标题")
    p_update.add_argument("--group", default="B_important", choices=POINT_GROUPS)
    p_update.add_argument("--status", default="", choices=sorted(VALID_STATUSES))
    p_update.add_argument("--evidence", default="", help="用户理解证据/事件说明")
    p_update.add_argument("--event", default="", choices=tuple(REQUIRED_STAGE_EVENTS.keys()))
    p_update.add_argument("--deposit", default="", choices=("understanding", "associations", "explore"))
    p_update.add_argument("--note", default="", help="相关笔记路径")

    p_check = sub.add_parser("check", help="检查阶段是否达到通过条件")
    p_check.add_argument("--stage", required=True, choices=("feynman", "socratic", "associate", "wrapup"))

    p_report = sub.add_parser("report", help="生成学习覆盖报告")
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "init":
        result = init_contract(args)
    elif args.command == "show":
        result = {"ok": True, "contract": load_contract(args.user)}
    elif args.command == "update":
        result = update_contract(args)
    elif args.command == "check":
        result = check_contract(args)
    elif args.command == "report":
        result = report_contract(args)
    else:
        parser.print_help()
        return
    print_result(result, args.json)


if __name__ == "__main__":
    main()
