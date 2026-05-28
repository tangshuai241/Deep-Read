import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import backup


def test_create_backup_includes_core_data(tmp_path, monkeypatch):
    base = tmp_path / "deepread"
    base.mkdir()
    state = base / "state" / "ou_user"
    notes = base / "notes" / "users" / "ou_user"
    logs = base / "logs"
    state.mkdir(parents=True)
    notes.mkdir(parents=True)
    logs.mkdir()
    (base / "config.yaml").write_text("paths: {}\n", encoding="utf-8")
    (state / "current.json").write_text("{}", encoding="utf-8")
    (notes / "note.md").write_text("# note", encoding="utf-8")
    (logs / "bot.log").write_text("ok", encoding="utf-8")

    monkeypatch.setattr(backup, "BASE", base)
    monkeypatch.setattr(backup, "load_config", lambda: {
        "paths": {"state_dir": str(base / "state"), "notes_dir": str(base / "notes")}
    })

    result = backup.create_backup(output_dir=tmp_path / "backups")

    assert result["files"] >= 4
    with zipfile.ZipFile(result["path"]) as zf:
        names = set(zf.namelist())
        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))

    assert "config/config.yaml" in names
    assert "state/ou_user/current.json" in names
    assert "notes/users/ou_user/note.md" in names
    assert manifest["include_books"] is False


def test_list_backups_orders_newest_first(tmp_path, monkeypatch):
    monkeypatch.setattr(backup, "BASE", tmp_path)
    out = tmp_path / "backups"
    out.mkdir()
    old = out / "deepread-backup-old.zip"
    new = out / "deepread-backup-new.zip"
    old.write_bytes(b"old")
    new.write_bytes(b"new")

    backups = backup.list_backups()

    assert backups[0]["name"] == "deepread-backup-new.zip"
