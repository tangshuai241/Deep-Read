"""测试飞书适配器（不调用真实 lark-cli）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from adapters import feishu_bot


def test_format_reply_text_flattens_multiline():
    text = "第一行\n\n第二行\n- 第三行"

    result = feishu_bot.format_reply_text(text)

    # 双换行 → 单换行，保留基本可读性
    assert "\n\n" not in result
    assert "第一行" in result
    assert "第二行" in result
    assert "• 第三行" in result


def test_format_reply_text_strips_markdown():
    text = "**系统1**的*认知放松*很重要\n\n`代码`和~~删除~~\n\n[链接](http://x)"
    result = feishu_bot.format_reply_text(text)
    assert "**" not in result
    assert "*" not in result
    assert "`" not in result
    assert "~~" not in result
    assert "[链接]" not in result
    assert "系统1" in result
    assert "认知放松" in result


def test_send_reply_prefers_chat_id(monkeypatch):
    captured = {}

    class DummyResult:
        returncode = 0
        stderr = ""

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return DummyResult()

    monkeypatch.setattr(feishu_bot.subprocess, "run", fake_run)

    assert feishu_bot.send_reply("oc_test", "hello", target_type="chat") is True
    cmd = captured["cmd"]

    assert "--chat-id" in cmd
    assert "oc_test" in cmd
    assert "--text" in cmd
    assert "--user-id" not in cmd
    assert "--as" in cmd
    assert cmd[cmd.index("--as") + 1] == "bot"


def test_send_reply_can_fallback_to_user_id(monkeypatch):
    captured = {}

    class DummyResult:
        returncode = 0
        stderr = ""

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return DummyResult()

    monkeypatch.setattr(feishu_bot.subprocess, "run", fake_run)

    assert feishu_bot.send_reply("ou_test", "hello", target_type="user") is True
    cmd = captured["cmd"]

    assert "--user-id" in cmd
    assert "ou_test" in cmd
    assert "--chat-id" not in cmd


def test_thinking_commands_go_to_agent():
    assert feishu_bot.match_command("/深思 总结我的回答") == "agent"
    assert feishu_bot.match_command("/普通 你好") == "agent"
