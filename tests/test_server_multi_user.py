"""测试 Web 控制台多用户辅助逻辑。"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import server


def test_server_resolves_user_notes_dir_by_config():
    base = os.path.join("tmp", "notes")

    assert server.resolve_user_notes_dir(
        base, "ou_test", {"profile": {"name": "trial"}}
    ) == os.path.join(base, "users", "ou_test")
    assert server.resolve_user_notes_dir(
        base, "ou_test", {"profile": {"name": "personal"}}
    ) == base
    assert server.resolve_user_notes_dir(
        base, "../bad/user", {"note": {"isolate_by_user": True}}
    ) == os.path.join(base, "users", "bad_user")


def test_list_notes_infers_owner_from_isolated_path(tmp_path, monkeypatch):
    notes_root = tmp_path / "notes"
    user_dir = notes_root / "users" / "ou_test" / "《测试书》"
    user_dir.mkdir(parents=True)
    note = user_dir / "概念.md"
    note.write_text("---\n书名: 测试书\n章节: 1\n---\n正文", encoding="utf-8")

    monkeypatch.setattr(server, "load_config", lambda: {"note": {"isolate_by_user": True}})
    monkeypatch.setattr(server, "get_notes_dir", lambda: str(notes_root))

    notes = server.list_notes(str(notes_root))

    assert len(notes) == 1
    assert notes[0]["user_id"] == "ou_test"
    assert notes[0]["book"] == "《测试书》"


def test_known_users_reads_sessions_and_state_dirs(tmp_path, monkeypatch):
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    (sessions / "s1.json").write_text(
        json.dumps({"user_id": "ou_session"}, ensure_ascii=False),
        encoding="utf-8",
    )
    state_root = tmp_path / "state"
    state_root.mkdir()
    (state_root / "ou_state").mkdir()

    monkeypatch.setattr(server, "SESSIONS_DIR", sessions)
    monkeypatch.setattr(server, "BASE", tmp_path)

    users = {u["id"] for u in server.known_users()}

    assert "ou_session" in users
    assert "ou_state" in users
