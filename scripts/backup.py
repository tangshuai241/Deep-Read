#!/usr/bin/env python3
"""DeepRead server backup helper.

The default backup is intentionally data-focused: config, state, notes and logs.
Books are optional because EPUB libraries can be large and are usually easier to
re-upload than user state.
"""

import argparse
import json
import os
import zipfile
from datetime import datetime
from pathlib import Path


BASE = Path(__file__).resolve().parent.parent


def load_config():
    config_path = BASE / "config.yaml"
    if not config_path.exists():
        return {}
    try:
        import yaml

        with open(config_path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        return {}


def resolve_path(path_value, default=None):
    if not path_value:
        return Path(default).resolve() if default else None
    path = Path(os.path.expanduser(str(path_value)))
    if not path.is_absolute():
        path = BASE / path
    return path.resolve()


def iter_files(path):
    path = Path(path)
    if path.is_file():
        yield path
        return
    if not path.is_dir():
        return
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for name in files:
            file_path = Path(root) / name
            if file_path.suffix == ".lock":
                continue
            yield file_path


def add_path_to_zip(zf, source, arc_root):
    added = []
    source = Path(source)
    if not source.exists():
        return added

    if source.is_file():
        arcname = Path(arc_root) / source.name
        zf.write(source, arcname.as_posix())
        added.append(str(source))
        return added

    for file_path in iter_files(source):
        rel = file_path.relative_to(source)
        arcname = Path(arc_root) / rel
        zf.write(file_path, arcname.as_posix())
        added.append(str(file_path))
    return added


def backup_sources(config, include_books=False):
    paths = config.get("paths", {})
    sources = [
        ("config", BASE / "config.yaml"),
        ("reading-notes", BASE / "reading-notes.md"),
        ("state", resolve_path(paths.get("state_dir"), BASE / "state")),
        ("notes", resolve_path(paths.get("notes_dir"), BASE / "notes")),
        ("logs", BASE / "logs"),
    ]
    if include_books:
        sources.append(("books", resolve_path(paths.get("books_dir"), BASE / "books")))
    return sources


def create_backup(include_books=False, output_dir=None):
    config = load_config()
    out_dir = resolve_path(output_dir, BASE / "backups")
    out_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    zip_path = out_dir / f"deepread-backup-{timestamp}.zip"
    manifest = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "include_books": bool(include_books),
        "base": str(BASE),
        "sources": [],
        "files": 0,
        "bytes": 0,
        "skipped": [],
    }

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for label, source in backup_sources(config, include_books=include_books):
            if not source or not Path(source).exists():
                manifest["skipped"].append({"label": label, "path": str(source or "")})
                continue
            added = add_path_to_zip(zf, source, label)
            manifest["sources"].append({
                "label": label,
                "path": str(source),
                "files": len(added),
            })
            manifest["files"] += len(added)
            manifest["bytes"] += sum(Path(p).stat().st_size for p in added if Path(p).exists())

        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

    manifest["path"] = str(zip_path)
    manifest["size"] = zip_path.stat().st_size
    return manifest


def list_backups(output_dir=None):
    out_dir = resolve_path(output_dir, BASE / "backups")
    if not out_dir.exists():
        return []
    backups = []
    for file_path in sorted(out_dir.glob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True):
        backups.append({
            "path": str(file_path),
            "name": file_path.name,
            "size": file_path.stat().st_size,
            "mtime": datetime.fromtimestamp(file_path.stat().st_mtime).isoformat(timespec="seconds"),
        })
    return backups


def main():
    parser = argparse.ArgumentParser(description="DeepRead server backup")
    parser.add_argument("--include-books", action="store_true", help="同时备份 books_dir 下的 EPUB")
    parser.add_argument("--output-dir", default="", help="备份输出目录，默认 ./backups")
    parser.add_argument("--list", action="store_true", help="列出已有备份")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    if args.list:
        result = {"ok": True, "backups": list_backups(args.output_dir or None)}
    else:
        result = {"ok": True, "backup": create_backup(args.include_books, args.output_dir or None)}

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.list:
        for item in result["backups"]:
            print(f"{item['mtime']}  {item['size']:>10}  {item['path']}")
    else:
        backup = result["backup"]
        print(f"备份完成: {backup['path']}")
        print(f"文件: {backup['files']} 个，原始大小: {backup['bytes']} bytes，压缩包: {backup['size']} bytes")


if __name__ == "__main__":
    main()
