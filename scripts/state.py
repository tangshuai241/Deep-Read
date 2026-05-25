#!/usr/bin/env python3
"""
DeepRead 状态管理
用法:
  python state.py show [--user default]       # 显示当前阅读状态
  python state.py set --stage feynman --book "思考快与慢" --chapter 5  # 更新状态
  python state.py set --field blindspots --add "新盲点"  # 追加到列表字段
  python state.py reset [--user default]       # 重置为空闲
  python state.py history [--user default]     # 查看历史
"""

import argparse
import json
import os
import sys
from pathlib import Path
from datetime import datetime, date


def load_config():
    config_path = Path(__file__).parent.parent / "config.yaml"
    if config_path.exists():
        try:
            import yaml
            with open(config_path, encoding='utf-8') as f:
                config = yaml.safe_load(f)
            return config.get("paths", {}).get("state_dir", os.path.join(os.path.dirname(__file__), "..", "state"))
        except ImportError:
            pass
    return os.path.join(os.path.dirname(__file__), "..", "state")


def get_state_dir(config_state_dir, user="default"):
    return os.path.join(config_state_dir, user)


def get_current_path(state_dir):
    return os.path.join(state_dir, "current.json")


def get_history_dir(state_dir):
    return os.path.join(state_dir, "history")


def read_state(state_dir):
    path = get_current_path(state_dir)
    if os.path.exists(path):
        with open(path, encoding='utf-8-sig') as f:
            return json.load(f)
    return default_state()


def default_state():
    return {
        "current": {
            "book": None,
            "chapter": None,
            "section": None,
            "stage": "idle",
            "turn_count": 0,
            "user_goal": None,
            "last_transition": str(date.today())
        },
        "blindspots": [],
        "concepts_covered": [],
        "pending_connections": [],
        "session_summary": "",
        "profile_notes": []
    }


def write_state(state_dir, state):
    os.makedirs(state_dir, exist_ok=True)
    path = get_current_path(state_dir)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def archive_state(state_dir, state):
    history_dir = get_history_dir(state_dir)
    os.makedirs(history_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%dT%H%M%S")
    fname = f"{ts}.json"
    path = os.path.join(history_dir, fname)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def cmd_show(state_dir, args):
    state = read_state(state_dir)
    c = state.get("current", {})
    print(f"书名:   {c.get('book') or '(未开始)'}")
    print(f"章节:   {c.get('chapter') or '-'}")
    print(f"小节:   {c.get('section') or '-'}")
    print(f"阶段:   {c.get('stage', 'idle')}")
    print(f"目标:   {c.get('user_goal') or '-'}")
    print(f"轮次:   {c.get('turn_count', 0)}")
    print(f"更新:   {c.get('last_transition', '-')}")
    print(f"盲点:   {len(state.get('blindspots', []))} 个")
    print(f"概念:   {len(state.get('concepts_covered', []))} 个")
    print(f"摘要:   {state.get('session_summary') or '-'}")
    if args.json:
        print(json.dumps(state, ensure_ascii=False, indent=2))


def cmd_set(state_dir, args):
    state = read_state(state_dir)
    c = state["current"]

    if args.stage:
        old_stage = c.get("stage")
        if old_stage and old_stage != args.stage:
            # 归档旧状态（修改前）
            archive_state(state_dir, state)
        c["stage"] = args.stage
        c["turn_count"] = 0
        c["last_transition"] = str(date.today())

    if args.book:
        c["book"] = args.book
    if args.chapter:
        c["chapter"] = args.chapter
    if args.section:
        c["section"] = args.section
    if args.goal:
        c["user_goal"] = args.goal
    if args.turn is not None:
        c["turn_count"] = args.turn
    if args.summary:
        state["session_summary"] = args.summary

    # 追加到列表字段
    if args.add_blindspot:
        if args.add_blindspot not in state["blindspots"]:
            state["blindspots"].append(args.add_blindspot)
    if args.add_concept:
        if args.add_concept not in state["concepts_covered"]:
            state["concepts_covered"].append(args.add_concept)
    if args.add_profile:
        if args.add_profile not in state["profile_notes"]:
            state["profile_notes"].append(args.add_profile)

    write_state(state_dir, state)
    print(f"状态已更新: stage={c['stage']}, book={c.get('book')}, chapter={c.get('chapter')}")


def cmd_reset(state_dir, args):
    if args.hard:
        state = default_state()
        write_state(state_dir, state)
        print("状态已完全重置")
    else:
        state = read_state(state_dir)
        archive_state(state_dir, state)
        state["current"]["stage"] = "idle"
        state["current"]["turn_count"] = 0
        state["current"]["last_transition"] = str(date.today())
        state["session_summary"] = ""
        write_state(state_dir, state)
        print("状态已重置为空闲（旧状态已归档）")


def cmd_history(state_dir, args):
    history_dir = get_history_dir(state_dir)
    if not os.path.exists(history_dir):
        print("(无历史记录)")
        return
    files = sorted(os.listdir(history_dir), reverse=True)
    for f in files[:args.limit]:
        path = os.path.join(history_dir, f)
        with open(path, encoding='utf-8') as fh:
            s = json.load(fh)
            c = s.get("current", {})
            print(f"{f.replace('.json', '')}  {c.get('book') or '-'}  {c.get('chapter') or '-'}  {c.get('stage', '-')}")


def main():
    parser = argparse.ArgumentParser(description="DeepRead 状态管理")
    parser.add_argument("--user", default="default", help="用户 ID（默认: default）")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")

    sub = parser.add_subparsers(dest="command")

    p_show = sub.add_parser("show", help="显示当前状态")

    p_set = sub.add_parser("set", help="更新状态")
    p_set.add_argument("--stage", help="阶段: idle/init/feynman/socratic/associate/wrapup")
    p_set.add_argument("--book", help="书名")
    p_set.add_argument("--chapter", help="章节")
    p_set.add_argument("--section", help="小节")
    p_set.add_argument("--goal", help="阅读目标")
    p_set.add_argument("--turn", type=int, help="轮次计数")
    p_set.add_argument("--summary", help="一句话摘要")
    p_set.add_argument("--add-blindspot", help="追加盲点")
    p_set.add_argument("--add-concept", help="追加概念")
    p_set.add_argument("--add-profile", help="追加画像记录")

    p_reset = sub.add_parser("reset", help="重置状态")
    p_reset.add_argument("--hard", action="store_true", help="完全重置（不归档）")

    p_hist = sub.add_parser("history", help="查看历史")
    p_hist.add_argument("--limit", type=int, default=20, help="显示最近 N 条")

    args = parser.parse_args()
    config_state_dir = load_config()
    state_dir = get_state_dir(config_state_dir, args.user)

    if args.command == "show":
        cmd_show(state_dir, args)
    elif args.command == "set":
        cmd_set(state_dir, args)
    elif args.command == "reset":
        cmd_reset(state_dir, args)
    elif args.command == "history":
        cmd_history(state_dir, args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
