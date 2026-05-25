#!/usr/bin/env python3
"""
DeepRead 飞书 Bot 适配器

流程:
  飞书消息 → 解析意图 → 加载/创建用户 session
  → agent.process_message() → 返回回复 → 发回飞书

用法:
  python feishu_bot.py                    # 启动事件监听
  python feishu_bot.py --once "精读《思考快与慢》第5章"  # 单次处理
  python feishu_bot.py --once "继续" --user tangshuai  # 指定用户

前置条件:
  - DEEPSEEK_API_KEY / ANTHROPIC_API_KEY 已设置
  - (完整版) lark-cli 已登录 + 飞书应用已配置事件订阅
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from agent import DeepReadAgent, find_session_for_user


def get_agent_for_user(user_id):
    """获取或创建用户的 Agent 实例（从磁盘恢复会话）"""
    # 查找磁盘上已有的会话
    sid = find_session_for_user(user_id)
    if sid:
        try:
            agent = DeepReadAgent(session_id=sid, user_id=user_id)
            return agent
        except SystemExit:
            pass

    return DeepReadAgent(user_id=user_id)


def handle_message(text, user_id="default"):
    """处理一条消息，返回回复文本"""
    agent = get_agent_for_user(user_id)
    response, _tools = agent.process_message(text)
    return response


def handle_once(text, user_id="default"):
    """单次处理（--once 模式）"""
    agent = get_agent_for_user(user_id)
    print(f"用户: {user_id} | 会话: {agent.session_id}")
    print(f"后端: {agent.llm.name}/{agent.llm.model}")
    print()
    response, _tools = agent.process_message(text)
    print(response)
    print()
    print(f"会话已保存: {agent.session_id}")
    print(f"(下次用 --once '...' --user {user_id} 继续)")
    return response


def listen_events():
    """监听飞书消息事件（需要 lark-cli）"""
    print("飞书 Bot 事件监听（需要 lark-cli）")
    print()
    print("完整实现步骤:")
    print("  1. lark-cli event consume im.message.receive_v1")
    print("  2. 解析 NDJSON → 提取 user_id + text")
    print("  3. handle_message(text, user_id) → 得到回复")
    print("  4. 通过 lark-cli im send 发送回复")
    print()
    print("当前可用: 单次处理模式")
    print("  python feishu_bot.py --once '精读《思考快与慢》第5章'")


def main():
    parser = argparse.ArgumentParser(description="DeepRead 飞书 Bot 适配器")
    parser.add_argument("--once", help="单次处理一条消息")
    parser.add_argument("--user", default="default", help="用户 ID（用于会话保持）")
    args = parser.parse_args()

    if args.once:
        handle_once(args.once, args.user)
    else:
        listen_events()


if __name__ == "__main__":
    main()
