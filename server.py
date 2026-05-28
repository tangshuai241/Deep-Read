#!/usr/bin/env python3
"""DeepRead Studio — Web 控制台 (FastAPI)"""
import hashlib, hmac, json, os, re, secrets, shutil, sys, urllib.parse, zipfile
from datetime import datetime, timezone
from pathlib import Path
from difflib import unified_diff

from fastapi import FastAPI, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader

try:
    import psutil
except ImportError:
    psutil = None

BASE = Path(__file__).parent
SCRIPTS = BASE / "scripts"
SESSIONS_DIR = BASE / "state" / "sessions"
LOGS_DIR = BASE / "logs"
BACKUPS_DIR = BASE / "backups"
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(SCRIPTS))

import backup as backup_script
import extract_epub

app = FastAPI(title="DeepRead Studio")
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")
jinja_env = Environment(loader=FileSystemLoader(str(BASE / "templates")), auto_reload=True)


def render(name, ctx):
    """直接渲染 Jinja2 模板，绕过 Starlette 的 TemplateResponse"""
    sl = security_level()
    ctx.setdefault("security_level", sl[0])
    ctx.setdefault("security_message", sl[1])
    ctx.setdefault("auth_enabled", web_auth_enabled())
    tmpl = jinja_env.get_template(name)
    return HTMLResponse(tmpl.render(**ctx))


# ── helpers ────────────────────────────────────────
def _expand_path(path_value, default=None):
    if not path_value:
        return Path(default).resolve() if default else None
    path = Path(os.path.expanduser(str(path_value)))
    if not path.is_absolute():
        path = BASE / path
    return path.resolve()


def load_config():
    try:
        with open(BASE / "config.yaml", encoding="utf-8") as f:
            import yaml; return yaml.safe_load(f) or {}
    except (FileNotFoundError, PermissionError):
        return {}


def web_password():
    config = load_config()
    return (
        os.environ.get("DEEPREAD_WEB_PASSWORD")
        or config.get("web", {}).get("password", "")
        or config.get("server", {}).get("password", "")
    )


def web_auth_enabled():
    return bool(web_password())


def sign_token(value):
    secret = web_password()
    return hmac.new(secret.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()


def make_auth_token():
    nonce = secrets.token_urlsafe(18)
    return f"{nonce}.{sign_token(nonce)}"


def verify_auth_token(token):
    if not web_auth_enabled():
        return True
    if not token or "." not in token:
        return False
    nonce, sig = token.split(".", 1)
    return hmac.compare_digest(sig, sign_token(nonce))


def is_authenticated(request: Request):
    return verify_auth_token(request.cookies.get("deepread_auth", ""))


@app.middleware("http")
async def require_web_auth(request: Request, call_next):
    if not web_auth_enabled():
        return await call_next(request)

    path = request.url.path
    allowed = (
        path == "/login"
        or path.startswith("/static/")
        or path == "/favicon.ico"
    )
    if allowed or is_authenticated(request):
        return await call_next(request)

    if path.startswith("/api/"):
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
    return RedirectResponse(url=f"/login?next={request.url.path}", status_code=303)

def should_isolate_user_notes(config):
    notes_cfg = config.get("note", {})
    if "isolate_by_user" in notes_cfg:
        return bool(notes_cfg.get("isolate_by_user"))
    profile = config.get("profile", {})
    profile_name = str(profile.get("name", "")).lower()
    return bool(profile.get("im_first")) or profile_name == "trial"

def sanitize_user_id(user):
    raw = str(user or "").strip()
    if not raw:
        return "default"
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", raw)
    return safe.strip("._-") or "default"

def resolve_user_notes_dir(base_notes_dir, user, config):
    if not should_isolate_user_notes(config):
        return base_notes_dir
    return os.path.join(base_notes_dir, "users", sanitize_user_id(user))

def user_label(user_id):
    text = str(user_id or "default")
    if text == "default":
        return "default"
    return f"{text[:8]}...{text[-4:]}" if len(text) > 14 else text

def pid_is_running(pid):
    if not pid:
        return False
    if os.name != "nt":
        try:
            os.kill(int(pid), 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        except Exception:
            return False
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, int(pid))  # PROCESS_QUERY_LIMITED_INFORMATION
        running = handle != 0
        if handle:
            kernel32.CloseHandle(handle)
        return running
    except Exception:
        return False

def known_users():
    users = {}
    if SESSIONS_DIR.exists():
        for f in SESSIONS_DIR.glob("*.json"):
            try:
                with open(f, encoding="utf-8") as fh:
                    user_id = json.load(fh).get("user_id", "default")
                users[user_id] = user_label(user_id)
            except Exception:
                pass
    state_root = _expand_path(load_config().get("paths", {}).get("state_dir"), BASE / "state")
    if state_root.exists():
        for child in state_root.iterdir():
            if child.is_dir() and child.name != "sessions":
                users.setdefault(child.name, user_label(child.name))
    if not users:
        users["default"] = "default"
    return [{"id": uid, "label": label} for uid, label in sorted(users.items(), key=lambda item: item[1])]

def _allowed_path(path: str) -> bool:
    """限制文件访问范围：notes_dir / vault_dir / deepread 项目目录"""
    if not path:
        return False
    resolved = os.path.realpath(path)
    config = load_config()
    allowed_roots = [os.path.realpath(str(BASE))]
    for key in ("notes_dir", "vault_dir", "books_dir"):
        p = config.get("paths", {}).get(key, "")
        if p:
            allowed_roots.append(os.path.realpath(str(_expand_path(p))))
    return any(resolved == root or resolved.startswith(root + os.sep) for root in allowed_roots)


def _allowed_user_path(path: Path) -> bool:
    try:
        path = path.resolve()
    except OSError:
        return False
    config = load_config()
    roots = [
        BASE.resolve(),
        _expand_path(config.get("paths", {}).get("state_dir"), BASE / "state"),
        _expand_path(config.get("paths", {}).get("notes_dir"), BASE / "notes"),
    ]
    return any(root and (path == root or root in path.parents) for root in roots)


def _user_state_dir(user):
    config = load_config()
    state_root = _expand_path(config.get("paths", {}).get("state_dir"), BASE / "state")
    return state_root / sanitize_user_id(user)


def _user_note_dir(user):
    config = load_config()
    base_notes = _expand_path(config.get("paths", {}).get("notes_dir"), BASE / "notes")
    return Path(resolve_user_notes_dir(str(base_notes), user, config))

def load_state():
    state_root = _expand_path(load_config().get("paths", {}).get("state_dir"), BASE / "state")
    p = state_root / "default" / "current.json"
    if p.exists():
        with open(p, encoding="utf-8-sig") as f:
            return json.load(f)
    return {}

def load_user_state(user="default"):
    state_root = _expand_path(load_config().get("paths", {}).get("state_dir"), BASE / "state")
    p = state_root / sanitize_user_id(user) / "current.json"
    if not p.exists() and user != "default":
        p = state_root / str(user) / "current.json"
    if p.exists():
        with open(p, encoding="utf-8-sig") as f:
            return json.load(f)
    return {}

def get_notes_dir():
    c = load_config()
    return c.get("paths", {}).get("notes_dir", str(BASE / "notes"))


def get_books_dir():
    c = load_config()
    return c.get("paths", {}).get("books_dir", str(BASE / "books"))

def note_owner_from_path(path, base_dir):
    config = load_config()
    if not should_isolate_user_notes(config):
        return "default"
    try:
        rel = Path(os.path.relpath(path, base_dir))
    except ValueError:
        return ""
    parts = rel.parts
    if len(parts) >= 3 and parts[0] == "users":
        return parts[1]
    return ""

def security_level():
    """返回 (level, message)
    level: 'danger' | 'warn' | 'ok'
    """
    if web_auth_enabled():
        return ("ok", "")
    is_local = os.environ.get("DEEPREAD_HOST", "127.0.0.1") in ("127.0.0.1", "localhost", "::1", "0.0.0.0")
    if is_local:
        return ("warn", "建议设置 DEEPREAD_WEB_PASSWORD 启用 Web 登录保护")
    return ("danger", "控制台暴露在公网且无密码保护！请立即设置 DEEPREAD_WEB_PASSWORD 环境变量")

def server_status():
    info = {"python": sys.version.split()[0]}
    if psutil:
        info["cpu"] = f"{psutil.cpu_percent(interval=0.1):.0f}%"
        mem = psutil.virtual_memory()
        info["mem"] = f"{mem.percent:.0f}% ({mem.available // 1048576} MB 可用)"
        disk = psutil.disk_usage(str(BASE))
        info["disk"] = f"{disk.percent:.0f}% ({disk.free // 1073741824} GB 空闲)"
        info["boot"] = datetime.fromtimestamp(psutil.boot_time()).strftime("%m-%d %H:%M")
    else:
        for k in ("cpu", "mem", "disk", "boot"):
            info[k] = "—"
    return info

def recent_errors(limit=5):
    errors = []
    if not LOGS_DIR.exists():
        return errors
    files = sorted(LOGS_DIR.glob("*.log"), key=os.path.getmtime, reverse=True)
    for fp in files:
        if len(errors) >= limit:
            break
        try:
            for line in open(fp, encoding="utf-8", errors="replace"):
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg = str(entry.get("error", "") or entry.get("content", "") or "")
                if not msg or all(kw not in msg.lower() for kw in ("error", "fail", "exception", "traceback")):
                    continue
                errors.append({
                    "ts": entry.get("ts", ""),
                    "type": entry.get("type", ""),
                    "msg": msg[:200],
                    "file": fp.name,
                    "user_id": entry.get("user_id", ""),
                })
                if len(errors) >= limit:
                    break
        except Exception:
            pass
    return errors

def aggregate_tasks():
    tasks = []
    for user in [u["id"] for u in known_users()]:
        cp = _user_state_dir(user) / "learning_contract.json"
        if not cp.exists():
            continue
        try:
            with open(cp, encoding="utf-8") as f:
                c = json.load(f)
        except Exception:
            continue
        scope = c.get("scope", {})
        km = c.get("knowledge_map", {})
        mode = c.get("reading_mode", "")
        mode_cn = ""
        if mode:
            try:
                from reading_modes import READING_MODES
                mode_cn = READING_MODES.get(mode, {}).get("name", mode)
            except ImportError:
                mode_cn = mode
        tasks.append({
            "user_id": user,
            "user_label": user_label(user),
            "book": scope.get("book", ""),
            "chapter": str(scope.get("chapter", "")),
            "section": str(scope.get("section", "")),
            "goal": scope.get("goal", ""),
            "reading_mode": mode,
            "mode_name": mode_cn,
            "book_type": c.get("book_type", ""),
            "profile": c.get("profile", ""),
            "A_core": len(km.get("A_core", [])),
            "B_important": len(km.get("B_important", [])),
            "C_evidence": len(km.get("C_evidence", [])),
            "D_application": len(km.get("D_application", [])),
            "updated": c.get("updated_at", ""),
        })
    return sorted(tasks, key=lambda t: t.get("updated", ""), reverse=True)

def list_log_files():
    if not LOGS_DIR.exists():
        return []
    files = []
    for fp in sorted(LOGS_DIR.glob("*.log"), key=os.path.getmtime, reverse=True):
        fsize = fp.stat().st_size
        mtime = datetime.fromtimestamp(fp.stat().st_mtime).isoformat(timespec="seconds")
        files.append({"name": fp.name, "size": fsize, "size_str": f"{fsize/1024:.0f}KB" if fsize < 1048576 else f"{fsize/1048576:.1f}MB", "mtime": mtime})
    return files

def read_log_file(filename, filter_user="", filter_error=False, limit=200):
    fp = LOGS_DIR / filename
    if not fp.exists() or not _allowed_path(str(fp)):
        return []
    lines = []
    try:
        with open(fp, encoding="utf-8", errors="replace") as f:
            for line in f:
                if len(lines) >= limit:
                    break
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if filter_user and entry.get("user_id", "") != filter_user:
                    continue
                if filter_error:
                    msg = str(entry.get("error", "") or entry.get("content", "") or "")
                    if not msg or all(kw not in msg.lower() for kw in ("error", "fail", "exception")):
                        continue
                entry["elapsed_str"] = f"{entry.get('elapsed_ms',0)/1000:.1f}s" if entry.get("elapsed_ms") else ""
                lines.append(entry)
    except Exception:
        pass
    return list(reversed(lines))[-limit:]

def compress_notes(dir_path, user=""):
    config = load_config()
    base_dir = dir_path or get_notes_dir()
    notes = list_notes(base_dir, user=user)
    if not notes:
        return None
    tmp = BASE / "exports"
    tmp.mkdir(exist_ok=True)
    label = sanitize_user_id(user) if user else "all"
    zip_path = tmp / f"deepread-notes-{label}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for n in notes:
            fp = n["path"]
            if os.path.exists(fp):
                arcname = os.path.relpath(fp, base_dir)
                zf.write(fp, arcname)
    return zip_path

def list_notes(base_dir, user=""):
    notes = []
    if not os.path.isdir(base_dir):
        return notes
    config = load_config()
    base_notes = get_notes_dir()
    target_user = sanitize_user_id(user) if user else ""
    for root, dirs, files in os.walk(base_dir):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in sorted(files):
            if not f.endswith(".md"): continue
            fp = os.path.join(root, f)
            owner = note_owner_from_path(fp, base_notes)
            if target_user and should_isolate_user_notes(config) and owner and owner != target_user:
                continue
            rel = os.path.relpath(fp, base_dir)
            book = rel.split(os.sep)[0] if os.sep in rel else ""
            if owner and rel.startswith(os.path.join("users", owner) + os.sep):
                rest = rel.split(os.sep, 2)
                book = rest[2].split(os.sep)[0] if len(rest) >= 3 and os.sep in rest[2] else ""
            mtime = os.path.getmtime(fp)
            # 读 frontmatter
            fm = {}
            try:
                with open(fp, encoding="utf-8") as fh:
                    raw = fh.read(2000)
                if raw.startswith("---"):
                    end = raw.find("---", 3)
                    if end > 0:
                        for line in raw[3:end].strip().split("\n"):
                            if ":" in line:
                                k, v = line.split(":", 1)
                                fm[k.strip()] = v.strip()
            except Exception: pass
            notes.append({
                "path": fp, "rel": rel, "book": book, "name": f.replace(".md", ""),
                "mtime": mtime, "fm": fm, "user_id": owner or "default",
                "user_label": user_label(owner or "default")
            })
    return sorted(notes, key=lambda x: x["mtime"], reverse=True)

DEEPREAD_KW = ["精读", "读《", "深度阅读", "deepread", "deep-read", "费曼", "苏格拉底",
               "write_note", "extract_epub", "state.py", "思考快与慢",
               "Obsidian", "obsidian", "知识库", "读书笔记"]

def list_sessions():
    sess = []
    if not SESSIONS_DIR.exists(): return sess
    for f in sorted(SESSIONS_DIR.glob("*.json"), key=os.path.getmtime, reverse=True):
        try:
            with open(f, encoding="utf-8") as fh:
                d = json.load(fh)
            msgs = d.get("messages", [])
            users = sum(1 for m in msgs if m.get("role") == "user")
            assistants = sum(1 for m in msgs if m.get("role") == "assistant")
            tools = sum(1 for m in msgs if m.get("role") == "tool")
            # 标题：book + chapter，或第一条用户消息
            book = d.get("book", "") or ""
            ch = d.get("chapter", "") or ""
            title = f"{book} {ch}".strip() if (book or ch) else ""
            if not title:
                for m in msgs:
                    if m.get("role") == "user" and isinstance(m.get("content"), str):
                        title = m["content"][:60]; break
            # 状态
            has_notes = any("write_note" in str(m) for m in msgs)
            has_errors = any(
                m.get("role") == "tool" and
                ('"ok": false' in str(m.get("content","")) or
                 'error_code' in str(m.get("content","")) or
                 'API 错误' in str(m))
                for m in msgs)
            completed = d.get("current", {}).get("stage") == "idle"
            notes_dir = str(f.stem)
            sess.append({
                "id": f.stem, "title": title or "(未命名)",
                "book": book, "chapter": ch,
                "user_id": d.get("user_id", "default"),
                "user_label": user_label(d.get("user_id", "default")),
                "provider": d.get("provider", ""), "model": d.get("model", ""),
                "user_count": users, "ai_count": assistants, "tool_count": tools,
                "has_notes": has_notes, "has_errors": has_errors, "completed": completed,
                "updated": d.get("updated_at", ""), "source": "agent"
            })
        except: pass
    return sess


def sessions_for_user(user):
    user = sanitize_user_id(user)
    return [s for s in list_sessions() if sanitize_user_id(s.get("user_id", "default")) == user]


def user_summary(user):
    user = sanitize_user_id(user)
    state = load_user_state(user)
    current = state.get("current", {})
    config = load_config()
    notes_dir = _user_note_dir(user) if should_isolate_user_notes(config) else _expand_path(get_notes_dir(), BASE / "notes")
    notes = list_notes(str(notes_dir), user=user if should_isolate_user_notes(config) else "")
    sessions = sessions_for_user(user)
    contract_path = _user_state_dir(user) / "learning_contract.json"
    return {
        "id": user,
        "label": user_label(user),
        "state": state,
        "current": current,
        "sessions": len(sessions),
        "notes": len(notes),
        "last_session": sessions[0] if sessions else None,
        "notes_dir": str(notes_dir),
        "state_dir": str(_user_state_dir(user)),
        "has_contract": contract_path.exists(),
        "updated": sessions[0]["updated"] if sessions else "",
    }


def export_user_archive(user):
    user = sanitize_user_id(user)
    export_dir = BASE / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    archive_path = export_dir / f"deepread-user-{user}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.zip"

    state_dir = _user_state_dir(user)
    note_dir = _user_note_dir(user)
    sessions = sessions_for_user(user)
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        manifest = {
            "user": user,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "state_dir": str(state_dir),
            "notes_dir": str(note_dir),
            "session_count": len(sessions),
        }
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        if state_dir.exists():
            for fp in state_dir.rglob("*"):
                if fp.is_file():
                    zf.write(fp, (Path("state") / fp.relative_to(state_dir)).as_posix())
        if note_dir.exists():
            for fp in note_dir.rglob("*"):
                if fp.is_file():
                    zf.write(fp, (Path("notes") / fp.relative_to(note_dir)).as_posix())
        for s in sessions:
            sp = SESSIONS_DIR / f"{s['id']}.json"
            if sp.exists():
                zf.write(sp, (Path("sessions") / sp.name).as_posix())
    return archive_path


def reset_user_data(user):
    user = sanitize_user_id(user)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    reset_root = BASE / "state" / "_reset_archive" / f"{user}-{stamp}"
    reset_root.mkdir(parents=True, exist_ok=True)
    moved = []

    state_dir = _user_state_dir(user)
    note_dir = _user_note_dir(user)
    for label, path in (("state", state_dir), ("notes", note_dir)):
        if path.exists() and _allowed_user_path(path):
            target = reset_root / label
            shutil.move(str(path), str(target))
            moved.append({"label": label, "from": str(path), "to": str(target)})

    session_dir = reset_root / "sessions"
    session_dir.mkdir(exist_ok=True)
    for s in sessions_for_user(user):
        sp = SESSIONS_DIR / f"{s['id']}.json"
        if sp.exists() and _allowed_user_path(sp):
            shutil.move(str(sp), str(session_dir / sp.name))
            moved.append({"label": "session", "from": str(sp), "to": str(session_dir / sp.name)})

    return {"ok": True, "user": user, "archive": str(reset_root), "moved": moved}


def list_books():
    books_dir = _expand_path(get_books_dir(), BASE / "books")
    if not books_dir.exists():
        return []
    books = []
    for fp in sorted(books_dir.rglob("*.epub"), key=lambda p: p.stat().st_mtime, reverse=True):
        books.append({
            "name": fp.name,
            "path": str(fp),
            "rel": str(fp.relative_to(books_dir)),
            "size": fp.stat().st_size,
            "mtime": datetime.fromtimestamp(fp.stat().st_mtime).isoformat(timespec="seconds"),
        })
    return books


def inspect_book(book_arg, preview=20):
    try:
        return extract_epub.inspect_book(book_arg, preview_chapters=preview)
    except SystemExit as exc:
        return {"ok": False, "error": f"EPUB 检查失败: {exc}"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def list_claude_sessions():
    """读取 Claude Code JSONL，仅筛选 DeepRead 相关"""
    cc_dir = Path.home() / ".claude" / "projects"
    if not cc_dir.exists(): return []
    all_sess = []
    for proj_dir in sorted(cc_dir.iterdir()):
        if not proj_dir.is_dir(): continue
        for f in sorted(proj_dir.glob("*.jsonl"), key=os.path.getmtime, reverse=True):
            try:
                lines = open(f, encoding="utf-8").readlines()
                if not lines or len(lines) < 3: continue
                # 收集所有内容，判断是否 DeepRead 相关
                all_text = ""
                first_content = ""
                for line in lines:
                    d = json.loads(line)
                    c = str(d.get("content", "")).strip()
                    all_text += c + " "
                    if not first_content and c and len(c) > 10:
                        if any(skip in c for skip in ("<task-", "system-reminder", "</task", "<current_note")):
                            continue
                        first_content = c
                if not first_content:
                    first_content = f"(Claude Code · {proj_dir.name[:30]})"
                # 清理 XML 标签
                first_content = re.sub(r'<[^>]+>', '', first_content).strip()[:80]
                all_text_lower = all_text.lower()
                # 筛选：包含 DeepRead 关键词，或项目路径匹配
                is_dr = any(kw.lower() in all_text_lower for kw in DEEPREAD_KW)
                is_dr = is_dr or any(kw.lower() in proj_dir.name.lower() for kw in ["deepread", "ӣ", "燕矶", "Claude Code 项目"])
                if not is_dr: continue
                mtime = os.path.getmtime(f)
                ts = datetime.fromtimestamp(mtime).isoformat()
                title = first_content[:80] if first_content else "(空)"
                all_sess.append({
                    "id": f.stem[:16], "sid_full": f.stem,
                    "proj": proj_dir.name, "title": title,
                    "provider": "claude", "model": "Claude Code",
                    "user_count": len([l for l in lines if '"content"' in l]),
                    "ai_count": 0, "tool_count": 0,
                    "has_notes": False, "has_errors": False, "completed": False,
                    "updated": ts, "source": "claude",
                    "msg_count": len(lines)
                })
            except Exception: pass
    return sorted(all_sess, key=lambda x: x["updated"], reverse=True)

def load_session(sid):
    p = SESSIONS_DIR / f"{sid}.json"
    if not p.exists(): return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)

def parse_note_content(path):
    if not os.path.exists(path): return {"raw": "", "sections": {}, "fm": {}}
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    fm = {}
    body = raw
    if raw.startswith("---"):
        end = raw.find("---", 3)
        if end > 0:
            for line in raw[3:end].strip().split("\n"):
                if ":" in line:
                    k, v = line.split(":", 1)
                    fm[k.strip()] = v.strip()
            body = raw[end+3:].strip()
    sections = {}
    current = "_head"
    sections[current] = ""
    for line in body.split("\n"):
        if line.startswith("## "):
            current = line[3:].strip()
            sections[current] = ""
        else:
            sections[current] += line + "\n"
    return {"raw": raw, "fm": fm, "sections": sections}

def note_stats(path):
    data = parse_note_content(path)
    raw = data["raw"]
    quote_count = len(re.findall(r'^> ', raw, re.MULTILINE))
    link_count = len(re.findall(r'\[\[.+?\]\]', raw))
    word_count = len(raw.replace("\n", "").replace(" ", ""))
    has_book = bool(data["fm"].get("书名"))
    has_chapter = bool(data["fm"].get("章节"))
    return {
        "quote_count": quote_count, "link_count": link_count,
        "word_count": word_count, "has_book": has_book,
        "has_chapter": has_chapter, "fm_complete": has_book and has_chapter
    }

def compare_notes(left_path, right_path):
    ls = note_stats(left_path)
    rs = note_stats(right_path)
    left_raw = parse_note_content(left_path)["raw"]
    right_raw = parse_note_content(right_path)["raw"]
    diff = list(unified_diff(
        left_raw.splitlines(keepends=True),
        right_raw.splitlines(keepends=True),
        fromfile="left", tofile="right"
    ))
    return {"left_stats": ls, "right_stats": rs, "diff": "".join(diff)}


# ── pages ──────────────────────────────────────────
@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str = "/"):
    if not web_auth_enabled():
        return RedirectResponse(url="/", status_code=303)
    if not next.startswith("/") or next.startswith("//"):
        next = "/"
    return render("login.html", {
        "request": request,
        "next": next or "/",
        "error": request.query_params.get("error", ""),
    })


@app.post("/login")
async def login_submit(request: Request):
    if not web_auth_enabled():
        return RedirectResponse(url="/", status_code=303)
    body = (await request.body()).decode("utf-8", errors="replace")
    form = urllib.parse.parse_qs(body)
    password = form.get("password", [""])[0]
    next_url = form.get("next", ["/"])[0] or "/"
    if not next_url.startswith("/") or next_url.startswith("//"):
        next_url = "/"
    if hmac.compare_digest(password, web_password()):
        resp = RedirectResponse(url=next_url, status_code=303)
        resp.set_cookie("deepread_auth", make_auth_token(), httponly=True, samesite="lax")
        return resp
    return RedirectResponse(url=f"/login?error=1&next={urllib.parse.quote(next_url)}", status_code=303)


@app.get("/logout")
def logout():
    resp = RedirectResponse(url="/login", status_code=303)
    resp.delete_cookie("deepread_auth")
    return resp


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, user: str = ""):
    users = known_users()
    selected_user = user or (users[0]["id"] if len(users) == 1 else "all")
    state = load_user_state(selected_user) if selected_user != "all" else {}
    current = state.get("current", {})
    concepts_all = [str(c) for c in state.get("concepts_covered", [])]

    # 当前阅读任务（翻译成人话）
    reading = {
        "book": str(current.get("book") or "—"),
        "chapter": str(current.get("chapter") or ""),
        "section": str(current.get("section") or ""),
        "stage": str(current.get("stage", "idle")),
        "goal": str(current.get("user_goal") or ""),
    }
    stage_map = {"idle": "空闲", "init": "初始化", "feynman": "费曼输出",
                  "socratic": "苏格拉底追问", "associate": "联想", "wrapup": "收尾"}
    reading["stage_cn"] = stage_map.get(reading["stage"], reading["stage"])
    if reading["stage"] == "idle" and reading["chapter"]:
        reading["next"] = f"继续第{reading['chapter']}章下一节，或复习本节笔记"
    elif reading["stage"] == "idle":
        reading["next"] = "开始精读一本书"
    else:
        reading["next"] = "继续对话"

    # 知识积累
    config = load_config()
    notes_dir = get_notes_dir() if selected_user == "all" else resolve_user_notes_dir(get_notes_dir(), selected_user, config)
    book_notes = 0
    if os.path.isdir(notes_dir):
        book_dir = os.path.join(notes_dir, f"《{reading['book']}》")
        if os.path.isdir(book_dir):
            book_notes = len([f for f in os.listdir(book_dir) if f.endswith(".md")])
    knowledge = {
        "concepts": len(concepts_all),
        "book_notes": book_notes,
        "recent_5": concepts_all[-5:] if len(concepts_all) > 5 else concepts_all,
    }

    # 最近活动（过滤测试/寒暄）
    all_sessions = list_sessions()
    recent = []
    for s in all_sessions:
        if selected_user and selected_user != "all" and s.get("user_id", "default") != selected_user:
            continue
        title = s.get("title", "")
        # 跳过测试/寒暄/空白
        if any(skip in title for skip in ("你好", "hi", "model_check", "route_check", "测试", "test")):
            continue
        if s["user_count"] < 2 and not s["has_notes"]:
            continue
        recent.append(s)
        if len(recent) >= 8:
            break

    # 系统状态
    claude_count = len(list_claude_sessions())
    system = {
        "provider": os.environ.get("DEEPSEEK_API_KEY") and "DeepSeek" or "—",
        "model": "deepseek-v4-pro",
        "claude_sessions": claude_count,
    }

    return render("dashboard.html", {
        "request": request, "reading": reading, "knowledge": knowledge,
        "recent": recent, "system": system,
        "agent_count": len(all_sessions), "claude_count": claude_count,
        "users": users, "selected_user": selected_user,
        "server_status": server_status(),
        "tasks": aggregate_tasks()[:10],
        "recent_errors": recent_errors(),
    })

@app.get("/sessions", response_class=HTMLResponse)
def sessions_page(request: Request, user: str = ""):
    agent_sessions = list_sessions()
    if user:
        agent_sessions = [s for s in agent_sessions if s.get("user_id", "default") == user]
    claude_sessions = list_claude_sessions()
    return render("sessions.html", {
        "request": request,
        "agent_sessions": agent_sessions,
        "claude_sessions": claude_sessions,
        "users": known_users(),
        "selected_user": user,
    })

@app.get("/sessions/{sid}", response_class=HTMLResponse)
def session_detail(request: Request, sid: str):
    data = load_session(sid)
    if not data: return HTMLResponse("会话不存在", 404)
    return render("session_detail.html", {
        "request": request, "session": data, "sid": sid
    })

@app.get("/notes", response_class=HTMLResponse)
def notes_page(request: Request, dir: str = "", user: str = ""):
    config = load_config()
    base_root = get_notes_dir()
    if dir:
        base_dir = dir
    elif user and should_isolate_user_notes(config):
        base_dir = resolve_user_notes_dir(base_root, user, config)
    else:
        base_dir = base_root
    notes = list_notes(base_dir, user=user if not dir else "")
    return render("notes.html", {
        "request": request, "notes": notes, "dir": base_dir,
        "users": known_users(), "selected_user": user,
        "isolate_by_user": should_isolate_user_notes(config),
    })

@app.get("/notes/view", response_class=HTMLResponse)
def note_view(request: Request, path: str = ""):
    if not path or not os.path.exists(path):
        return HTMLResponse("笔记不存在", 404)
    if not _allowed_path(path):
        return HTMLResponse("路径不在允许范围内", 403)
    data = parse_note_content(path)
    stats = note_stats(path)
    return render("note_detail.html", {
        "request": request, "path": path, "name": os.path.basename(path),
        "fm": data["fm"], "sections": data["sections"], "stats": stats
    })

@app.get("/compare", response_class=HTMLResponse)
def compare_page(request: Request,
                  left_dir: str = "", right_dir: str = ""):
    if left_dir and not _allowed_path(left_dir):
        return HTMLResponse("左侧路径不在允许范围内", 403)
    if right_dir and not _allowed_path(right_dir):
        return HTMLResponse("右侧路径不在允许范围内", 403)
    left_notes = list_notes(left_dir) if left_dir else []
    right_notes = list_notes(right_dir) if right_dir else []
    return render("compare.html", {
        "request": request, "left_dir": left_dir, "right_dir": right_dir,
        "left_notes": left_notes, "right_notes": right_notes
    })

@app.get("/doctor", response_class=HTMLResponse)
def doctor_page(request: Request):
    return render("doctor.html", {"request": request})


@app.get("/setup", response_class=HTMLResponse)
def setup_page(request: Request):
    config = load_config()
    profile = config.get("profile", {})
    return render("setup.html", {
        "request": request,
        "profile": profile,
        "config": {
            "llm_provider": config.get("llm", {}).get("provider", ""),
            "llm_model": config.get("llm", {}).get("model", ""),
            "obsidian": bool(config.get("paths", {}).get("vault_dir", "")),
            "wiki": config.get("integrations", {}).get("wiki", {}).get("enabled", False),
            "cognition": config.get("cognition", {}).get("enabled", False),
            "notes_dir": config.get("paths", {}).get("notes_dir", ""),
            "vault_dir": config.get("paths", {}).get("vault_dir", ""),
        }
    })


@app.get("/modes", response_class=HTMLResponse)
def modes_page(request: Request):
    return render("modes.html", {"request": request})


@app.get("/concepts", response_class=HTMLResponse)
def concepts_page(request: Request):
    return render("concepts.html", {"request": request})


@app.get("/users", response_class=HTMLResponse)
def users_page(request: Request, user: str = ""):
    users = [user_summary(u["id"]) for u in known_users()]
    selected = sanitize_user_id(user or (users[0]["id"] if users else "default"))
    return render("users.html", {
        "request": request,
        "users": users,
        "selected_user": selected,
        "summary": user_summary(selected),
        "sessions": sessions_for_user(selected)[:20],
        "notes": list_notes(str(_user_note_dir(selected)), user=selected)[:20],
    })


@app.get("/books", response_class=HTMLResponse)
def books_page(request: Request, book: str = ""):
    return render("books.html", {
        "request": request,
        "books": list_books(),
        "selected_book": book,
        "books_dir": str(_expand_path(get_books_dir(), BASE / "books")),
    })


@app.get("/backup", response_class=HTMLResponse)
def backup_page(request: Request):
    return render("backup.html", {
        "request": request,
        "backups": backup_script.list_backups(),
    })


@app.get("/tasks", response_class=HTMLResponse)
def tasks_page(request: Request):
    return render("tasks.html", {
        "request": request, "tasks": aggregate_tasks(),
    })


@app.get("/logs", response_class=HTMLResponse)
def logs_page(request: Request, file: str = ""):
    return render("logs.html", {
        "request": request,
        "log_files": list_log_files(),
        "selected_file": file,
        "users": known_users(),
    })


@app.get("/api/tasks")
def api_tasks():
    return {"ok": True, "tasks": aggregate_tasks()}


@app.get("/api/logs")
def api_logs():
    return {"ok": True, "files": list_log_files()}


@app.get("/api/logs/view")
def api_logs_view(file: str = Query(""), user: str = Query(""), error: str = Query(""), limit: int = Query(200)):
    if not file:
        return JSONResponse({"ok": False, "error": "缺少 file 参数"}, 400)
    return {"ok": True, "entries": read_log_file(file, filter_user=user, filter_error=error == "1", limit=min(limit, 500))}


@app.post("/api/books/upload")
async def api_books_upload(file: UploadFile):
    if not file.filename or not file.filename.lower().endswith(".epub"):
        return JSONResponse({"ok": False, "error": "仅支持 .epub 文件"}, 400)
    books_dir = _expand_path(get_books_dir(), BASE / "books")
    books_dir.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^A-Za-z0-9_\-\.\u4e00-\u9fff]+", "_", file.filename)
    dest = books_dir / safe_name
    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        return JSONResponse({"ok": False, "error": "文件不能超过 50MB"}, 400)
    dest.write_bytes(content)
    result = inspect_book(str(dest.resolve()))
    return {"ok": result.get("ok", False), "filename": safe_name, "inspect": result}


@app.get("/api/notes/download")
def api_notes_download(dir: str = Query(""), user: str = Query("")):
    zp = compress_notes(dir, user=user)
    if not zp:
        return JSONResponse({"ok": False, "error": "没有可下载的笔记"}, 404)
    return FileResponse(str(zp), filename=zp.name, media_type="application/zip")


@app.get("/api/profile")
def api_profile():
    config = load_config()
    return {"profile": config.get("profile", {}), "integrations": config.get("integrations", {})}


@app.get("/api/modes")
def api_modes():
    import subprocess
    r = subprocess.run(
        [sys.executable, str(BASE / "cli.py"), "modes", "list"],
        capture_output=True, text=True, encoding="utf-8", timeout=10,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"}
    )
    return {"output": r.stdout}


@app.get("/api/concepts/report")
def api_concepts_report():
    import subprocess
    r = subprocess.run(
        [sys.executable, str(BASE / "cli.py"), "concepts", "report"],
        capture_output=True, text=True, encoding="utf-8", timeout=15,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"}
    )
    return {"output": r.stdout}


# ── API ────────────────────────────────────────────
@app.post("/api/notes/compile")
def api_compile(data: dict):
    path = data.get("path", "")
    if not path or not os.path.exists(path):
        return JSONResponse({"ok": False, "error": "路径不存在"}, 400)
    import subprocess
    r = subprocess.run(
        [sys.executable, str(SCRIPTS / "write_note.py"), "compile", "--path", path],
        capture_output=True, text=True, encoding="utf-8", timeout=15,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"}
    )
    return {"ok": r.returncode == 0, "stdout": r.stdout, "stderr": r.stderr}

@app.get("/api/state")
def api_state(user: str = Query("default")):
    return load_user_state(user)

@app.get("/api/doctor")
def api_doctor(deep: int = Query(0)):
    import subprocess
    cmd = [sys.executable, str(BASE / "cli.py"), "doctor"]
    if deep:
        cmd.append("--deep")
    r = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", timeout=30,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"}
    )
    # 从摘要行解析结构化计数，避免前端 regex 歧义
    m = re.search(r'(\d+)\s+PASS,\s*(\d+)\s+WARN,\s*(\d+)\s+FAIL', r.stdout)
    counts = {"pass": int(m.group(1)), "warn": int(m.group(2)), "fail": int(m.group(3))} if m else {}
    return {"ok": r.returncode == 0, "output": r.stdout, "deep": bool(deep), "counts": counts}


@app.get("/api/backup")
def api_backup_list():
    return {"ok": True, "backups": backup_script.list_backups()}


@app.post("/api/backup")
def api_backup_create(data: dict = None):
    data = data or {}
    try:
        result = backup_script.create_backup(include_books=bool(data.get("include_books")))
        return {"ok": True, "backup": result}
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, 500)


@app.get("/api/users")
def api_users():
    return {"ok": True, "users": [user_summary(u["id"]) for u in known_users()]}


@app.get("/api/users/{user}")
def api_user_detail(user: str):
    user = sanitize_user_id(user)
    return {
        "ok": True,
        "summary": user_summary(user),
        "sessions": sessions_for_user(user),
        "notes": list_notes(str(_user_note_dir(user)), user=user),
    }


@app.get("/api/users/{user}/export")
def api_user_export(user: str):
    archive_path = export_user_archive(user)
    return FileResponse(
        str(archive_path),
        filename=archive_path.name,
        media_type="application/zip",
    )


@app.post("/api/users/{user}/reset")
def api_user_reset(user: str, data: dict = None):
    data = data or {}
    if data.get("confirm") != "RESET":
        return JSONResponse({"ok": False, "error": "需要 confirm=RESET"}, 400)
    return reset_user_data(user)


@app.get("/api/books")
def api_books():
    return {"ok": True, "books_dir": str(_expand_path(get_books_dir(), BASE / "books")), "books": list_books()}


@app.get("/api/books/inspect")
def api_books_inspect(book: str = Query(""), preview: int = Query(20)):
    if not book:
        return JSONResponse({"ok": False, "error": "缺少 book 参数"}, 400)
    result = inspect_book(book, preview=max(1, min(preview, 100)))
    if not result.get("ok"):
        return JSONResponse(result, 400)
    return result


# ── Bot API ──
def _run_bot_cmd(args):
    """内部调用 python cli.py bot <args>"""
    import subprocess
    cmd = [sys.executable, str(BASE / "cli.py"), "bot"] + args
    r = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", timeout=15,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"}
    )
    return {"ok": r.returncode == 0, "output": r.stdout, "stderr": r.stderr}


@app.get("/api/bot/status")
def api_bot_status():
    lock_path = BASE / "state" / "feishu_bot.listen.lock"
    if not lock_path.exists():
        return {"ok": True, "running": False, "stale": False, "pid": None}
    try:
        with open(lock_path, encoding="utf-8") as f:
            lock = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"ok": True, "running": False, "stale": False, "pid": None}
    pid = int(lock.get("pid", 0))
    running = pid_is_running(pid)
    return {
        "ok": True, "running": running, "stale": not running and pid > 0,
        "pid": pid, "started_at": lock.get("started_at", ""),
        "reply": lock.get("reply", False)
    }


@app.post("/api/bot/start")
def api_bot_start(data: dict = None):
    data = data or {}
    args = ["start"]
    if data.get("reply", True):
        args.append("--reply")
    notes_dir = data.get("notes_dir", "")
    if notes_dir:
        args.extend(["--notes-dir", notes_dir])
    return _run_bot_cmd(args)


@app.post("/api/bot/stop")
def api_bot_stop(data: dict = None):
    data = data or {}
    args = ["stop"]
    if data.get("force"):
        args.append("--force")
    return _run_bot_cmd(args)


@app.post("/api/bot/restart")
def api_bot_restart(data: dict = None):
    data = data or {}
    args = ["restart"]
    if data.get("reply", True):
        args.append("--reply")
    notes_dir = data.get("notes_dir", "")
    if notes_dir:
        args.extend(["--notes-dir", notes_dir])
    if data.get("force"):
        args.append("--force")
    return _run_bot_cmd(args)


@app.get("/api/quality")
def api_quality(path: str = Query("")):
    if not path or not os.path.exists(path):
        return JSONResponse({"ok": False, "error": "路径不存在"}, 400)
    if not _allowed_path(path):
        return JSONResponse({"ok": False, "error": "路径不在允许范围内"}, 403)
    import subprocess
    r = subprocess.run(
        [sys.executable, str(SCRIPTS / "note_quality.py"), "--path", path, "--json"],
        capture_output=True, text=True, encoding="utf-8", timeout=15,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"}
    )
    try:
        return {"ok": r.returncode == 0, "result": json.loads(r.stdout)}
    except json.JSONDecodeError:
        return {"ok": False, "error": r.stdout[:500]}

@app.post("/api/compare/diff")
def api_compare(data: dict):
    left = data.get("left", "")
    right = data.get("right", "")
    if not left or not right:
        return JSONResponse({"ok": False, "error": "需要两个路径"}, 400)
    if not os.path.exists(left) or not os.path.exists(right):
        return JSONResponse({"ok": False, "error": "路径不存在"}, 400)
    return {"ok": True, "result": compare_notes(left, right)}

@app.get("/api/sessions")
def api_sessions():
    return list_sessions()

@app.get("/api/sessions/{sid}")
def api_session_detail(sid: str):
    return load_session(sid) or JSONResponse({"error": "not found"}, 404)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8765)
