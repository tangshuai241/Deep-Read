"""测试飞书适配器（不调用真实 lark-cli）。"""
import json
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


def test_long_user_answer_goes_to_agent():
    text = "其实我觉得它消除的还是特质之间的关联，第一题和第二题所考察的重点不一样。"
    qr, need_agent = feishu_bot.quick_reply(text)

    assert qr is None
    assert need_agent is True


def test_natural_reading_request_goes_to_agent():
    assert feishu_bot.normalize_user_text("现在进行第七章第三节的学习") == "精读 现在进行第七章第三节的学习"
    qr, need_agent = feishu_bot.quick_reply("现在进行第七章第三节的学习")

    assert qr is None
    assert need_agent is True


def test_common_typo_is_normalized():
    assert feishu_bot.normalize_user_text("精度《思考快与慢》第七章") == "精读《思考快与慢》第七章"
    qr, need_agent = feishu_bot.quick_reply("精度《思考快与慢》第七章第三节")

    assert qr is None
    assert need_agent is True


def test_unknown_short_text_goes_to_agent():
    qr, need_agent = feishu_bot.quick_reply("精度")

    assert qr is None
    assert need_agent is True


def test_listen_lock_rejects_running_pid(tmp_path, monkeypatch):
    lock = tmp_path / "feishu.lock"
    lock.write_text('{"pid": 12345}', encoding="utf-8")
    monkeypatch.setattr(feishu_bot, "LOCK_PATH", lock)
    monkeypatch.setattr(feishu_bot, "_pid_is_running", lambda pid: pid == 12345)

    assert feishu_bot.acquire_listen_lock() is False
    assert lock.exists()


def test_listen_lock_replaces_stale_pid(tmp_path, monkeypatch):
    lock = tmp_path / "feishu.lock"
    lock.write_text('{"pid": 12345}', encoding="utf-8")
    monkeypatch.setattr(feishu_bot, "LOCK_PATH", lock)
    monkeypatch.setattr(feishu_bot, "_pid_is_running", lambda pid: False)
    monkeypatch.setattr(feishu_bot.os, "getpid", lambda: 999)

    assert feishu_bot.acquire_listen_lock() is True
    assert '"pid": 999' in lock.read_text(encoding="utf-8")
    feishu_bot.release_listen_lock()
    assert not lock.exists()


def test_acquire_listen_lock_records_metadata(tmp_path, monkeypatch):
    lock = tmp_path / "feishu.lock"
    monkeypatch.setattr(feishu_bot, "LOCK_PATH", lock)
    monkeypatch.setattr(feishu_bot, "_pid_is_running", lambda pid: False)
    monkeypatch.setattr(feishu_bot.os, "getpid", lambda: 555)

    assert feishu_bot.acquire_listen_lock(reply=True, notes_dir="C:\\test\\notes") is True

    data = json.loads(lock.read_text(encoding="utf-8"))
    assert data["pid"] == 555
    assert data["reply"] is True
    assert data["notes_dir"] == "C:\\test\\notes"
    assert "started_at" in data
    assert "cmd" in data

    feishu_bot.release_listen_lock()
    assert not lock.exists()


def test_send_reply_truncates_long_text(monkeypatch):
    captured = {}

    class DummyResult:
        returncode = 0
        stderr = ""

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return DummyResult()

    monkeypatch.setattr(feishu_bot.subprocess, "run", fake_run)

    long_text = "A" * 5000
    assert feishu_bot.send_reply("ou_test", long_text, target_type="user") is True
    cmd = captured["cmd"]
    text_arg = cmd[cmd.index("--text") + 1]
    assert len(text_arg) <= 4100  # 4000 + truncation suffix
