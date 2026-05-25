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

# 自动定位 lark-cli 可执行文件
def _find_lark_cli():
    """查找 lark-cli 路径（处理 Windows .cmd 后缀）"""
    npm_dir = os.path.join(os.environ.get("APPDATA", ""), "npm")
    for candidate in [
        os.path.join(npm_dir, "node_modules", "@larksuite", "cli", "bin", "lark-cli.exe"),
        os.path.join(npm_dir, "lark-cli.cmd"),   # Windows npm
        os.path.join(npm_dir, "lark-cli"),        # Unix/Git Bash wrapper
    ]:
        if os.path.exists(candidate):
            return candidate
    return "lark-cli"  # fallback: hope it's in PATH

LARK_CLI = _find_lark_cli()

# ── 消息去重 ──
RECENT_IDS = set()
MAX_RECENT = 200


def is_duplicate(message_id):
    if not message_id:
        return False
    if message_id in RECENT_IDS:
        return True
    RECENT_IDS.add(message_id)
    if len(RECENT_IDS) > MAX_RECENT:
        RECENT_IDS.clear()  # 简单轮转
    return False


# ── 命令白名单 ──
COMMAND_KEYWORDS = ["精读", "读《", "继续", "进入下一阶段", "跳过", "收尾",
                     "复习", "进度", "慢思考", "搜索", "联想", "批判",
                     "费曼", "苏格拉底", "/deepread", "/费曼", "/苏格拉底",
                     "/联想", "/批判", "/复习", "/进度", "/慢思考", "/卡片",
                     "深思", "/深思", "/thinking", "/think", "/reason",
                     "普通", "快答", "/普通", "/快答", "/normal"]

GREETINGS = {"你好", "hi", "hello", "在吗", "在不在", "嗨", "哈喽", "哈啰",
             "早上好", "下午好", "晚上好", "早", "好啊", "hey", "yo"}


def match_command(text):
    """匹配命令→返回 command_type 或 None"""
    stripped = text.strip()
    if stripped.lower() in GREETINGS:
        return "greeting"
    for kw in COMMAND_KEYWORDS:
        if kw in stripped:
            return "agent"
    return None


def quick_reply(text):
    """无需 LLM 的快捷回复，返回 (reply_text, should_log_agent)"""
    cmd = match_command(text)
    if cmd == "greeting":
        return ("你好～我是 DeepRead 阅读教练。\n"
                "你可以：\n"
                "• 精读《书名》第N章\n"
                "• 查看进度\n"
                "• 复习 / 慢思考\n"
                "• 搜索 关键词"), False
    if cmd == "agent":
        return None, True  # 需要走 Agent
    # 未知命令
    return ("支持的命令：\n"
            "  精读《书名》第N章\n"
            "  继续 / 1跳过\n"
            "  查看进度 / 复习 / 慢思考\n"
            "  搜索 关键词"), False


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


def format_reply_text(text):
    """Agent 回复 → 飞书纯文本。

    1. 去除纯文本无意义的 Markdown 标记（飞书不渲染）
    2. 多行压成单条，手机端更稳定
    """
    # 去 Markdown（飞书纯文本不需要）
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)   # **粗体**
    text = re.sub(r'\*(.+?)\*', r'\1', text)        # *斜体*
    text = re.sub(r'`(.+?)`', r'\1', text)          # `代码`
    text = re.sub(r'~~(.+?)~~', r'\1', text)        # ~~删除线~~
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)  # 标题
    text = re.sub(r'^>\s+', '', text, flags=re.MULTILINE)       # 引用
    text = re.sub(r'^[-*+]\s+', '• ', text, flags=re.MULTILINE) # 无序列表
    text = re.sub(r'^\d+\.\s+', '', text, flags=re.MULTILINE)   # 有序列表
    text = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', text) # 链接
    text = re.sub(r'\|', ' ', text)                 # 表格分隔符
    text = re.sub(r'-{3,}', '', text)               # 水平线

    # 多行 → 单条
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    text = re.sub(r"\n\s*\n+", "\n", text)
    text = re.sub(r"[ \t]{3,}", "  ", text)
    return text


def send_reply(receive_id, text, target_type="user"):
    """通过 lark-cli 发送回复"""
    text = format_reply_text(text)
    # 截断过长回复（飞书单条消息有长度限制）
    if len(text) > 4000:
        text = text[:4000] + "\n\n(回复过长，已截断。在终端用 python agent.py --resume 继续)"

    target_flag = "--chat-id" if target_type == "chat" else "--user-id"
    print(f"  [发送内容: {len(text)} 字符, target={target_type}]")
    try:
        result = subprocess.run(
            [LARK_CLI, "im", "+messages-send",
             target_flag, receive_id,
             "--text", text,
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

    cmd = [LARK_CLI, "event", "consume", "im.message.receive_v1", "--as", "bot"]
    if max_events:
        cmd.extend(["--max-events", str(max_events)])

    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding='utf-8',
        env={**os.environ, "PYTHONIOENCODING": "utf-8"}
    )

    # 等待启动完成
    time.sleep(3)

    # 检查进程是否启动失败
    if proc.poll() is not None:
        err = proc.stderr.read()
        print(f"  lark-cli 启动失败 (code={proc.returncode})")
        if err:
            for line in err.strip().split('\n')[:10]:
                print(f"  [lark-cli] {line}")
        return

    print("  lark-cli 已启动，等待飞书消息...")
    print("  现在用手机给 Bot 发一条消息")
    print()

    event_count = 0
    try:
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue

            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue

            # ── 提取 sender_id / chat_id（兼容扁平和嵌套）──
            sender_id = raw.get("sender_id", "")
            chat_id = raw.get("chat_id", "")
            if not sender_id and "event" in raw:
                ev = raw["event"]
                sender = ev.get("sender", {})
                if isinstance(sender, dict):
                    sid = sender.get("sender_id", {})
                    if isinstance(sid, dict):
                        sender_id = sid.get("open_id", "")
                    elif isinstance(sid, str):
                        sender_id = sid
                if not sender_id:
                    sender_id = ev.get("sender_id", "")
                if not chat_id:
                    chat_id = ev.get("chat_id", "")
                    msg = ev.get("message", {})
                    if isinstance(msg, dict):
                        chat_id = chat_id or msg.get("chat_id", "")

            # ── 提取 content（兼容扁平和嵌套）──
            content = raw.get("content", "")
            if not content and "event" in raw:
                ev = raw["event"]
                msg = ev.get("message", {})
                if isinstance(msg, dict):
                    content = msg.get("content", "")
                if not content:
                    content = ev.get("content", "")

            # 首条打印完整原始结构用于调试
            if event_count == 0:
                ts0 = time.strftime("%H:%M:%S")
                print(f"[{ts0}] 首条原始事件结构:")
                print(json.dumps(raw, ensure_ascii=False, indent=2)[:500])

            if not sender_id or not content:
                if event_count == 0:
                    print("  ⚠ sender_id 或 content 为空，请检查上方结构并调整解析")
                continue

            # ── 消息去重 ──
            msg_id = raw.get("message_id", raw.get("id", ""))
            if is_duplicate(msg_id):
                ts = time.strftime("%H:%M:%S")
                print(f"[{ts}] 跳过重复消息 {msg_id}")
                continue

            # JSON content → text
            if isinstance(content, str) and content.startswith("{"):
                try:
                    content_obj = json.loads(content)
                    content = content_obj.get("text", content)
                except json.JSONDecodeError:
                    pass

            if not content:
                continue

            event_count += 1
            ts = time.strftime("%H:%M:%S")
            print(f"[{ts}] #{event_count} sender={sender_id[:20]}... text={content[:60]}")

            # ── 命令白名单 ──
            qr, need_agent = quick_reply(content)
            if qr:
                response = qr
            else:
                response = handle_message(content, sender_id)

            preview = response[:100].replace('\n', ' ') + "..." if len(response) > 100 else response
            label = "(快捷)" if qr else ""
            print(f"  → {label} {preview}")

            # 回复（需显式开启）
            if reply_enabled:
                target = chat_id or sender_id
                target_type = "chat" if chat_id else "user"
                ok = send_reply(target, response, target_type=target_type)
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
    p_listen.add_argument("--max-events", type=int, default=0)
    p_listen.add_argument("--reply", action="store_true")
    p_listen.add_argument("--notes-dir", default="", help="笔记输出目录（覆盖 config.yaml）")

    p_once = sub_cmds.add_parser("once", help="单次处理")
    p_once.add_argument("text", help="消息文本")
    p_once.add_argument("--user", default="default", help="用户 ID")
    p_once.add_argument("--notes-dir", default="", help="笔记输出目录（覆盖 config.yaml）")

    args = parser.parse_args()

    # 笔记输出目录覆盖
    if getattr(args, "notes_dir", ""):
        os.environ["DEEPREAD_NOTES_DIR"] = args.notes_dir
        print(f"笔记输出: {args.notes_dir}")

    if args.mode == "listen":
        listen_events(max_events=args.max_events, reply_enabled=args.reply)
    elif args.mode == "once":
        handle_once(args.text, args.user)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
