"""测试 agent.py 会话管理（不调用 API）"""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from agent import (save_session, load_session, find_session_for_user,
                    list_sessions, SESSION_DIR)


def setup_module():
    os.environ["PYTHONIOENCODING"] = "utf-8"


def test_save_and_load_session(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        # 临时覆盖 SESSION_DIR
        import agent
        old_dir = agent.SESSION_DIR
        agent.SESSION_DIR = Path(tmp)

        try:
            sid = "test_001"
            messages = [
                {"role": "user", "content": "读第1章"},
                {"role": "assistant", "content": "好的"}
            ]
            meta = {"book": "测试", "chapter": "1", "user_id": "user_a",
                    "provider": "deepseek", "model": "deepseek-chat"}

            save_session(sid, messages, meta)

            loaded = load_session(sid)
            assert loaded is not None
            assert loaded["session_id"] == "test_001"
            assert loaded["book"] == "测试"
            assert loaded["user_id"] == "user_a"
            assert len(loaded["messages"]) == 2
        finally:
            agent.SESSION_DIR = old_dir


def test_find_session_for_user(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        import agent
        old_dir = agent.SESSION_DIR
        agent.SESSION_DIR = Path(tmp)

        try:
            # 创建两个用户各一个会话
            save_session("s1", [], {"user_id": "user_a", "book": "书A"})
            import time
            time.sleep(0.1)
            save_session("s2", [], {"user_id": "user_b", "book": "书B"})

            # user_a 应该找到 s1
            found = find_session_for_user("user_a")
            assert found == "s1"

            found = find_session_for_user("user_b")
            assert found == "s2"

            # 不存在的用户
            found = find_session_for_user("nobody")
            assert found is None
        finally:
            agent.SESSION_DIR = old_dir


def test_list_sessions(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        import agent
        old_dir = agent.SESSION_DIR
        agent.SESSION_DIR = Path(tmp)

        try:
            save_session("a", [], {"user_id": "u1"})
            save_session("b", [], {"user_id": "u2"})

            sessions = list_sessions()
            assert len(sessions) >= 2
        finally:
            agent.SESSION_DIR = old_dir


def test_session_contains_required_fields(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        import agent
        old_dir = agent.SESSION_DIR
        agent.SESSION_DIR = Path(tmp)

        try:
            save_session("fields_test", [], {"user_id": "u"})
            loaded = load_session("fields_test")
            assert "session_id" in loaded
            assert "created_at" in loaded
            assert "updated_at" in loaded
            assert "provider" in loaded
            assert "model" in loaded
            assert "user_id" in loaded
            assert "messages" in loaded
        finally:
            agent.SESSION_DIR = old_dir
