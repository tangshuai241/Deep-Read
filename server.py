#!/usr/bin/env python3
"""DeepRead Studio — Web 控制台 (FastAPI)"""
import json, os, re, sys
from datetime import datetime
from pathlib import Path
from difflib import unified_diff

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader

BASE = Path(__file__).parent
SCRIPTS = BASE / "scripts"
SESSIONS_DIR = BASE / "state" / "sessions"
LOGS_DIR = BASE / "logs"
sys.path.insert(0, str(BASE))

app = FastAPI(title="DeepRead Studio")
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")
jinja_env = Environment(loader=FileSystemLoader(str(BASE / "templates")), auto_reload=True)


def render(name, ctx):
    """直接渲染 Jinja2 模板，绕过 Starlette 的 TemplateResponse"""
    tmpl = jinja_env.get_template(name)
    return HTMLResponse(tmpl.render(**ctx))


# ── helpers ────────────────────────────────────────
def load_config():
    try:
        with open(BASE / "config.yaml", encoding="utf-8") as f:
            import yaml; return yaml.safe_load(f) or {}
    except (FileNotFoundError, PermissionError):
        return {}

def _allowed_path(path: str) -> bool:
    """限制文件访问范围：notes_dir / vault_dir / deepread 项目目录"""
    if not path:
        return False
    resolved = os.path.realpath(path)
    config = load_config()
    allowed_roots = [str(BASE)]
    for key in ("notes_dir", "vault_dir", "books_dir"):
        p = config.get("paths", {}).get(key, "")
        if p:
            allowed_roots.append(os.path.realpath(p))
    return any(resolved.startswith(root) for root in allowed_roots)

def load_state():
    p = BASE / "state" / "default" / "current.json"
    if p.exists():
        with open(p, encoding="utf-8-sig") as f:
            return json.load(f)
    return {}

def get_notes_dir():
    c = load_config()
    return c.get("paths", {}).get("notes_dir", str(BASE / "notes"))

def list_notes(base_dir):
    notes = []
    if not os.path.isdir(base_dir):
        return notes
    for root, dirs, files in os.walk(base_dir):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in sorted(files):
            if not f.endswith(".md"): continue
            fp = os.path.join(root, f)
            rel = os.path.relpath(fp, base_dir)
            book = rel.split(os.sep)[0] if os.sep in rel else ""
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
                "mtime": mtime, "fm": fm
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
                "provider": d.get("provider", ""), "model": d.get("model", ""),
                "user_count": users, "ai_count": assistants, "tool_count": tools,
                "has_notes": has_notes, "has_errors": has_errors, "completed": completed,
                "updated": d.get("updated_at", ""), "source": "agent"
            })
        except: pass
    return sess


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
@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    state = load_state()
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
    notes_dir = get_notes_dir()
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
        "agent_count": len(all_sessions), "claude_count": claude_count
    })

@app.get("/sessions", response_class=HTMLResponse)
def sessions_page(request: Request):
    agent_sessions = list_sessions()
    claude_sessions = list_claude_sessions()
    return render("sessions.html", {
        "request": request,
        "agent_sessions": agent_sessions,
        "claude_sessions": claude_sessions
    })

@app.get("/sessions/{sid}", response_class=HTMLResponse)
def session_detail(request: Request, sid: str):
    data = load_session(sid)
    if not data: return HTMLResponse("会话不存在", 404)
    return render("session_detail.html", {
        "request": request, "session": data, "sid": sid
    })

@app.get("/notes", response_class=HTMLResponse)
def notes_page(request: Request, dir: str = ""):
    base_dir = dir if dir else get_notes_dir()
    notes = list_notes(base_dir)
    return render("notes.html", {
        "request": request, "notes": notes, "dir": base_dir
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
def api_state():
    return load_state()

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
    import ctypes
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    running = handle != 0
    if handle:
        kernel32.CloseHandle(handle)
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
