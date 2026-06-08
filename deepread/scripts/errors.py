"""
DeepRead 统一错误格式
所有脚本输出错误时使用此模块。
"""

import json
import sys

# 错误码
BOOK_NOT_FOUND = "BOOK_NOT_FOUND"
EPUB_PARSE_FAILED = "EPUB_PARSE_FAILED"
CHAPTER_NOT_FOUND = "CHAPTER_NOT_FOUND"
FILE_NOT_FOUND = "FILE_NOT_FOUND"
SECTION_NOT_FOUND = "SECTION_NOT_FOUND"
CONFIG_MISSING = "CONFIG_MISSING"
DEPENDENCY_MISSING = "DEPENDENCY_MISSING"
INVALID_ARGS = "INVALID_ARGS"
IO_ERROR = "IO_ERROR"
UNKNOWN = "UNKNOWN"


def error(code, message, hint="", **extra):
    """输出统一 JSON 错误并退出。
    用法: error(BOOK_NOT_FOUND, "找不到书籍", "请检查 paths.books_dir")
    """
    out = {"ok": False, "error_code": code, "message": message}
    if hint:
        out["hint"] = hint
    out.update(extra)
    if extra.get("_no_exit"):
        return out
    print(json.dumps(out, ensure_ascii=False), file=sys.stderr)
    sys.exit(1)


def ok(data=None, **extra):
    """输出统一 JSON 成功响应。
    用法: ok({"path": "/notes/xxx.md"})
    """
    out = {"ok": True}
    if data:
        out["data"] = data
    out.update(extra)
    return out
