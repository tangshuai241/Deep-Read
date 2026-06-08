#!/usr/bin/env python3
"""
Book Toolchain — 健康检查
用法: python doctor.py
"""

import json
import os
import sys
import py_compile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent

def check(msg, ok):
    symbol = "✅" if ok else "❌"
    print(f"  {symbol} {msg}")
    return ok

def main():
    print("=" * 50)
    print("  Book Toolchain Doctor")
    print("=" * 50)
    print()

    all_ok = True

    # ── 1. 文件完整性 ──
    print("【1】文件完整性")
    scripts = {
        "book_downloader/book_downloader.py": "下载器",
        "deepread/agent.py": "DeepRead Agent",
        "deepread/scripts/extract_epub.py": "EPUB 提取",
        "deepread/scripts/preload_analysis.py": "4D 预读桥接",
        "deepread/scripts/errors.py": "错误定义",
        "deepread/scripts/state.py": "会话状态",
        "deepread/scripts/learning_contract.py": "学习契约",
        "deepread/scripts/write_note.py": "笔记写入",
        "deepread/scripts/search_vault.py": "知识库搜索",
        "deepread/scripts/logger.py": "日志",
        "deepread/scripts/reading_modes.py": "阅读模式",
        "config.example.yaml": "配置模板",
        "requirements.txt": "依赖清单",
        "LICENSE": "许可证",
    }

    py_files = []
    for path, desc in scripts.items():
        fp = REPO_ROOT / path
        ok = fp.exists()
        if not check(f"{desc} ({path})", ok):
            all_ok = False
        elif path.endswith(".py"):
            py_files.append(fp)

    # ── 2. Python 语法 ──
    print("\n【2】Python 语法检查")
    for f in py_files:
        try:
            py_compile.compile(str(f), doraise=True)
            check(f"语法 OK: {f.name}", True)
        except py_compile.PyCompileError as e:
            check(f"语法错误: {f.name} — {e}", False)
            all_ok = False

    # ── 3. 配置 ──
    print("\n【3】配置检查")
    config_path = REPO_ROOT / "config.yaml"
    if not config_path.exists():
        check("config.yaml 不存在（运行 install.py 创建）", False)
        all_ok = False
    else:
        check("config.yaml 存在", True)
        try:
            import yaml
            with open(config_path, encoding='utf-8') as f:
                cfg = yaml.safe_load(f) or {}

            api_key = cfg.get("llm", {}).get("api_key", "")
            if not api_key:
                check("llm.api_key（⚠️ 未配置——这是正常的，请先获取 DeepSeek API Key）", True)
                print("       获取地址：https://platform.deepseek.com")
            else:
                check("llm.api_key（已配置）", True)

            model = cfg.get("llm", {}).get("model", "")
            check(f"llm.model: {model}", bool(model))

            base_url = cfg.get("llm", {}).get("base_url", "")
            check(f"llm.base_url: {base_url}", bool(base_url))

            books_dir = cfg.get("paths", {}).get("books_dir", "")
            if books_dir:
                books_path = Path(os.path.expanduser(books_dir))
                if books_path.exists():
                    check(f"paths.books_dir: {books_dir}（目录存在）", True)
                else:
                    check(f"paths.books_dir: {books_dir}（目录不存在，首次运行会自动创建）", True)
            else:
                check("paths.books_dir（未设置，将用默认值 ~/TaskOS/books）", True)

            notes_dir = cfg.get("paths", {}).get("notes_dir", "")
            if notes_dir:
                check(f"paths.notes_dir: {notes_dir}", True)
            else:
                check("paths.notes_dir（未设置）", False)
                all_ok = False
        except Exception as e:
            check(f"config.yaml 解析失败: {e}", False)
            all_ok = False

    # ── 4. 依赖 ──
    print("\n【4】Python 依赖")
    for pkg, import_name in [("requests", "requests"), ("pyyaml", "yaml")]:
        try:
            __import__(import_name)
            check(f"{pkg}", True)
        except ImportError:
            check(f"{pkg}（pip install {pkg}）", False)
            all_ok = False

    # ── 5. 功能验证 ──
    print("\n【5】功能验证")
    try:
        from book_downloader.book_downloader import load_config
        cfg = load_config()
        if cfg:
            check("book_downloader 配置加载", True)
        else:
            check("book_downloader 配置加载（config.yaml 不存在或 PyYAML 未安装）", False)
    except Exception as e:
        check(f"book_downloader 导入失败: {e}", False)
        all_ok = False

    try:
        from deepread.scripts.preload_analysis import find_analysis_dir
        check("preload_analysis 模块导入", True)
    except Exception as e:
        check(f"preload_analysis 导入失败: {e}", False)
        all_ok = False

    # ── 汇总 ──
    print()
    print("=" * 50)
    if all_ok:
        print("  ✅ 全部检查通过！可以开始使用了。")
    else:
        print("  ⚠️  有检查未通过，请根据上述提示修复。")
    print("=" * 50)

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
