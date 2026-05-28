"""测试 Web 控制台多用户辅助逻辑。"""
import json
import os
import sys
import zipfile
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


def test_web_auth_token_roundtrip(monkeypatch):
    monkeypatch.setenv("DEEPREAD_WEB_PASSWORD", "secret")

    token = server.make_auth_token()

    assert server.web_auth_enabled() is True
    assert server.verify_auth_token(token) is True
    assert server.verify_auth_token(token + "bad") is False


def test_user_summary_counts_isolated_notes_and_sessions(tmp_path, monkeypatch):
    notes_root = tmp_path / "notes"
    user_note_dir = notes_root / "users" / "ou_user" / "《测试书》"
    user_note_dir.mkdir(parents=True)
    (user_note_dir / "概念.md").write_text("---\n书名: 测试书\n---\n正文", encoding="utf-8")

    sessions = tmp_path / "sessions"
    sessions.mkdir()
    (sessions / "s1.json").write_text(
        json.dumps({"user_id": "ou_user", "messages": [{"role": "user", "content": "精读"}]}, ensure_ascii=False),
        encoding="utf-8",
    )
    state_root = tmp_path / "state"
    (state_root / "ou_user").mkdir(parents=True)
    (state_root / "ou_user" / "current.json").write_text(
        json.dumps({"current": {"book": "测试书", "stage": "idle"}}, ensure_ascii=False),
        encoding="utf-8",
    )

    monkeypatch.setattr(server, "SESSIONS_DIR", sessions)
    monkeypatch.setattr(server, "load_config", lambda: {
        "note": {"isolate_by_user": True},
        "paths": {"notes_dir": str(notes_root), "state_dir": str(state_root)},
    })

    summary = server.user_summary("ou_user")

    assert summary["sessions"] == 1
    assert summary["notes"] == 1
    assert summary["current"]["book"] == "测试书"


def test_export_user_archive_contains_state_notes_and_sessions(tmp_path, monkeypatch):
    notes_root = tmp_path / "notes"
    note_dir = notes_root / "users" / "ou_user" / "《测试书》"
    note_dir.mkdir(parents=True)
    (note_dir / "概念.md").write_text("正文", encoding="utf-8")
    state_root = tmp_path / "state"
    user_state = state_root / "ou_user"
    user_state.mkdir(parents=True)
    (user_state / "current.json").write_text("{}", encoding="utf-8")
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    (sessions / "s1.json").write_text(json.dumps({"user_id": "ou_user"}), encoding="utf-8")

    monkeypatch.setattr(server, "BASE", tmp_path)
    monkeypatch.setattr(server, "SESSIONS_DIR", sessions)
    monkeypatch.setattr(server, "load_config", lambda: {
        "note": {"isolate_by_user": True},
        "paths": {"notes_dir": str(notes_root), "state_dir": str(state_root)},
    })

    archive = server.export_user_archive("ou_user")

    with zipfile.ZipFile(archive) as zf:
        names = set(zf.namelist())

    assert "state/current.json" in names
    assert "notes/《测试书》/概念.md" in names
    assert "sessions/s1.json" in names


def test_reset_user_data_archives_without_touching_other_user(tmp_path, monkeypatch):
    notes_root = tmp_path / "notes"
    target_note = notes_root / "users" / "ou_target" / "《书》"
    other_note = notes_root / "users" / "ou_other" / "《书》"
    target_note.mkdir(parents=True)
    other_note.mkdir(parents=True)
    (target_note / "a.md").write_text("a", encoding="utf-8")
    (other_note / "b.md").write_text("b", encoding="utf-8")

    state_root = tmp_path / "state"
    (state_root / "ou_target").mkdir(parents=True)
    (state_root / "ou_other").mkdir(parents=True)
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    (sessions / "s1.json").write_text(json.dumps({"user_id": "ou_target"}), encoding="utf-8")
    (sessions / "s2.json").write_text(json.dumps({"user_id": "ou_other"}), encoding="utf-8")

    monkeypatch.setattr(server, "BASE", tmp_path)
    monkeypatch.setattr(server, "SESSIONS_DIR", sessions)
    monkeypatch.setattr(server, "load_config", lambda: {
        "note": {"isolate_by_user": True},
        "paths": {"notes_dir": str(notes_root), "state_dir": str(state_root)},
    })

    result = server.reset_user_data("ou_target")

    assert result["ok"] is True
    assert not (notes_root / "users" / "ou_target").exists()
    assert (notes_root / "users" / "ou_other").exists()
    assert not (sessions / "s1.json").exists()
    assert (sessions / "s2.json").exists()
