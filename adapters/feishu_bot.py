#!/usr/bin/env python3
"""
DeepRead 飞书 Bot 适配器

流程:
  飞书消息 → 解析 user_id + text
  → agent.process_message() → 回复文本
  → lark-cli im +messages-send 发回飞书

用法:
  python feishu_bot.py listen                    # 启动事件监听（长驻）
  python feishu_bot.py listen --max-events 5     # 处理前5条后退出
  python feishu_bot.py --once "精读xx" --user tangshuai  # 单次测试

前置条件:
  - DEEPSEEK_API_KEY (或 ANTHROPIC_API_KEY / OPENAI_API_KEY) 已设置
  - lark-cli 已登录 (lark-cli auth login)
  - 飞书应用已配置 im.message.receive_v1 事件订阅
  - 机器人有 im:message.p2p_msg:readonly 权限
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from agent import DeepReadAgent, find_session_for_user


def get_agent_for_user(user_id):
    """获取或创建用户的 Agent 实例（磁盘恢复）"""
    sid = find_session_for_user(user_id)
    if sid:
        try:
            return DeepReadAgent(session_id=sid, user_id=user_id)
        except SystemExit:
            pass
    return DeepReadAgent(user_id=user_id)


def handle_message(text, user_id="default"):
    """处理一条消息，返回回复文本"""
    agent = get_agent_for_user(user_id)
    response, _tools = agent.process_message(text)
    return response


def send_reply(user_id, text):
    """通过 lark-cli 发送回复"""
    # 截断过长回复（飞书单条消息有长度限制）
    if len(text) > 4000:
        text = text[:4000] + "\n\n(回复过长，已截断。在终端用 python agent.py --resume 继续)"

    try:
        result = subprocess.run(
            ["lark-cli", "im", "+messages-send",
             "--user-id", user_id,
             "--markdown", text,
             "--as", "bot"],
            capture_output=True, text=True, timeout=15, encoding='utf-8',
            env={**os.environ, "PYTHONIOENCODING": "utf-8"}
        )
        if result.returncode != 0:
            print(f"  [发送失败: {result.stderr.strip()[:200]}]")
            return False
        return True
    except Exception as e:
        print(f"  [发送异常: {e}]")
        return False


def handle_once(text, user_id="default"):
    """单次处理模式"""
    agent = get_agent_for_user(user_id)
    print(f"用户: {user_id} | 会话: {agent.session_id}")
    print(f"后端: {agent.llm.name}/{agent.llm.model}")
    print()
    response, _tools = agent.process_message(text)
    print(response)
    print()
    print(f"会话已保存: {agent.session_id}")
    return response


def listen_events(max_events=0, reply_enabled=False):
    """监听飞书 IM 消息事件"""
    print("飞书事件监听启动")
    print(f"回复模式: {'开启' if reply_enabled else '关闭（仅打印）'}")
    if max_events:
        print(f"最大事件数: {max_events}")
    print()

    cmd = ["lark-cli", "event", "consume", "im.message.receive_v1"]
    if max_events:
        cmd.extend(["--max-events", str(max_events)])

    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding='utf-8',
        env={**os.environ, "PYTHONIOENCODING": "utf-8"}
    )

    event_count = 0
    try:
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue

            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            # 提取字段
            sender_id = event.get("sender_id", "")
            content = event.get("content", "")

            if not sender_id or not content:
                continue

            # 处理 JSON content（可能是字符串也可能是对象）
            if isinstance(content, str) and content.startswith("{"):
                try:
                    content_obj = json.loads(content)
                    content = content_obj.get("text", content)
                except json.JSONDecodeError:
                    pass

            event_count += 1
            ts = time.strftime("%H:%M:%S")
            print(f"[{ts}] #{event_count} 来自 {sender_id}: {content[:80]}")

            # 处理消息
            response = handle_message(content, sender_id)

            # 显示回复预览
            preview = response[:100].replace('\n', ' ') + "..." if len(response) > 100 else response
            print(f"  → {preview}")

            # 发送回复
            if reply_enabled:
                ok = send_reply(sender_id, response)
                if ok:
                    print(f"  ✓ 已发送")
                else:
                    print(f"  ✗ 发送失败")

            if max_events and event_count >= max_events:
                break

    except KeyboardInterrupt:
        print("\n监听已停止")
    finally:
        proc.terminate()

    print(f"\n共处理 {event_count} 条事件")


def main():
    parser = argparse.ArgumentParser(description="DeepRead 飞书 Bot 适配器")
    sub_cmds = parser.add_subparsers(dest="mode")

    p_listen = sub_cmds.add_parser("listen", help="启动事件监听")
    p_listen.add_argument("--max-events", type=int, default=0, help="最大事件数（0=不限）")
    p_listen.add_argument("--reply", action="store_true", help="自动回复（默认只打印）")

    p_once = sub_cmds.add_parser("once", help="单次处理")
    p_once.add_argument("text", help="消息文本")
    p_once.add_argument("--user", default="default", help="用户 ID")

    args = parser.parse_args()

    if args.mode == "listen":
        listen_events(max_events=args.max_events, reply_enabled=args.reply)
    elif args.mode == "once":
        handle_once(args.text, args.user)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
