"""
DeepRead 日志模块
记录工具调用、API 请求、错误到 logs/ 目录
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path

LOGS_DIR = Path(__file__).parent.parent / "logs"


def get_log(session_id):
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    return LOGS_DIR / f"{session_id}.log"


def log_event(session_id, event_type, **data):
    """写入一条结构化日志"""
    entry = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "type": event_type,
        "session": session_id
    }
    entry.update(data)
    try:
        with open(get_log(session_id), 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def log_tool_call(session_id, tool_name, params, result, elapsed_ms):
    log_event(session_id, "tool_call", tool=tool_name,
              params=str(params)[:200], result_preview=str(result)[:200],
              elapsed_ms=elapsed_ms)


def log_api_call(session_id, model, messages_count, elapsed_ms, error=None):
    data = {"model": model, "messages_count": messages_count, "elapsed_ms": elapsed_ms}
    if error:
        data["error"] = str(error)[:300]
    log_event(session_id, "api_call", **data)


def log_error(session_id, source, error):
    log_event(session_id, "error", source=source, error=str(error)[:500])


def log_session_start(session_id, provider, model, user_id):
    log_event(session_id, "session_start", provider=provider, model=model, user_id=user_id)


def log_session_end(session_id, reason):
    log_event(session_id, "session_end", reason=reason)
