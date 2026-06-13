#!/usr/bin/env python3
"""
Book Toolchain — 一键安装引导
用法: python install.py
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent


def _ok():
    """Return encoding-safe OK marker."""
    try:
        "✅".encode(sys.stdout.encoding)
        return "✅"
    except (UnicodeEncodeError, UnicodeError):
        return "[OK]"


def _fail():
    """Return encoding-safe FAIL marker."""
    try:
        "❌".encode(sys.stdout.encoding)
        return "❌"
    except (UnicodeEncodeError, UnicodeError):
        return "[FAIL]"


def _warn():
    """Return encoding-safe WARN marker."""
    try:
        "⚠️".encode(sys.stdout.encoding)
        return "⚠️"
    except (UnicodeEncodeError, UnicodeError):
        return "[WARN]"


def detect_agent():
    """Detect which AI agent environment we're running in."""
    home = Path.home()

    if (home / ".hermes").exists():
        return "hermes"
    if (home / ".claude").exists() or (REPO_ROOT / ".claude").exists():
        return "claude-code"
    if (REPO_ROOT / ".trae").exists():
        return "trae"
    return "unknown"


def install_dependencies():
    """Install Python dependencies."""
    req_file = REPO_ROOT / "requirements.txt"
    if not req_file.exists():
        print(f"  {_warn()} requirements.txt 不存在，跳过依赖安装")
        return

    print(f"  {_warn()} 安装 Python 依赖...")
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "-r", str(req_file)]
        )
        print(f"  {_ok()} 依赖安装完成")
    except subprocess.CalledProcessError:
        print(f"  {_warn()} 依赖安装失败，请手动执行：")
        print(f"     pip install -r {req_file}")


def install_hermes():
    """Install skills to ~/.hermes/skills/"""
    print(f"  {_warn()} 检测到 Hermes 环境\n")

    skill_dir = Path.home() / ".hermes" / "skills"
    skill_dir.mkdir(parents=True, exist_ok=True)

    skills = {
        "book_downloader/SKILL.md": "productivity/book-downloader/SKILL.md",
        "4d_pipeline/SKILL.md": "productivity/multi-dimensional-book-analysis/SKILL.md",
        "deepread/SKILL.md": "note-taking/deep-read/SKILL.md",
    }

    for src_rel, dst_rel in skills.items():
        src = REPO_ROOT / src_rel
        dst = skill_dir / dst_rel
        if src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            print(f"  {_ok()} {dst_rel}")
        else:
            print(f"  {_warn()} 跳过（文件不存在）: {src_rel}")

    # Remind user to keep the repo directory
    print()
    print(f"  {_warn()} 重要：请保留本仓库目录（不要删除）")
    print(f"      Skill 中引用的 Python 脚本位于：{REPO_ROOT}")
    print("      如果移动或删除了仓库目录，Skill 将无法找到脚本。")

    print(f"\n{_ok()} 安装完成！重启 Hermes 或执行 `hermes skills reload`")


def install_claude_code():
    """Set up Claude Code project context."""
    print(f"  {_warn()} 检测到 Claude Code 环境\n")

    claude_dir = REPO_ROOT / ".claude"
    claude_dir.mkdir(exist_ok=True)

    # Copy deepread CLAUDE.md as project-level context
    deepread_claude = REPO_ROOT / "deepread" / "CLAUDE.md"
    if deepread_claude.exists():
        shutil.copy2(deepread_claude, claude_dir / "CLAUDE.md")
        print(f"  {_ok()} .claude/CLAUDE.md（DeepRead 教练指令）")

    pipeline_claude = REPO_ROOT / "4d_pipeline" / "CLAUDE.md"
    if pipeline_claude.exists():
        commands_dir = claude_dir / "commands"
        commands_dir.mkdir(exist_ok=True)
        shutil.copy2(pipeline_claude, commands_dir / "4d-analyze.md")
        print(f"  {_ok()} .claude/commands/4d-analyze.md（4D 拆解指令）")

    print(f"\n{_ok()} Claude Code 配置完成！使用方式：")
    print("   对话中说 \"读《xxx》第N章\" → 触发 DeepRead 教练")
    print("   对话中说 \"4D 拆解《xxx》\" → 触发四维拆解管线")


def check_config():
    """Check if config.yaml exists and guide configuration."""
    config_path = REPO_ROOT / "config.yaml"
    example_path = REPO_ROOT / "config.example.yaml"

    if config_path.exists():
        try:
            import yaml
            with open(config_path, encoding='utf-8') as f:
                cfg = yaml.safe_load(f) or {}
            api_key = cfg.get("llm", {}).get("api_key", "")
            books_dir = cfg.get("paths", {}).get("books_dir", "")

            issues = []
            if not api_key:
                issues.append("llm.api_key（DeepSeek API Key）")
            if not books_dir:
                issues.append("paths.books_dir（EPUB 存放目录）")

            if issues:
                print(f"\n{_warn()} config.yaml 存在但以下必填项为空：")
                for i in issues:
                    print(f"   - {i}")
                print("   请编辑 config.yaml 补全。")
                print("   获取 DeepSeek API Key：https://platform.deepseek.com")
            else:
                print(f"\n{_ok()} config.yaml 已配置完整")
        except ImportError:
            print(f"\n{_warn()} 无法加载 config.yaml——请先安装 PyYAML：pip install pyyaml")
        except Exception as e:
            print(f"\n{_warn()} config.yaml 解析失败：{e}")
    else:
        if example_path.exists():
            shutil.copy2(example_path, config_path)
            print(f"\n{_warn()} 已创建 config.yaml（从 config.example.yaml 复制）")
            print(f"   {_warn()} 请编辑 config.yaml 并填入：")
            print("      1. llm.api_key — DeepSeek API Key")
            print("         获取地址：https://platform.deepseek.com")
            print("      2. paths.books_dir — EPUB 存放目录（如 ~/TaskOS/books）")
        else:
            print(f"\n{_fail()} config.example.yaml 不存在，仓库可能不完整")


def install_unknown():
    """CLI-only setup guidance."""
    print(f"  {_warn()} 未检测到特定 AI Agent 环境\n")
    print("   本工具可通过以下方式使用：")
    print("   1. 直接运行 Python 脚本：")
    print("      python book_downloader/book_downloader.py search \"书名\"")
    print("      python deepread/agent.py --book \"书名\"")
    print("   2. 将 SKILL.md 文件手动导入你的 AI Agent")
    print("   3. 参考 CLAUDE.md 中的指令模板\n")
    check_config()


def main():
    print("=" * 60)
    print("  Book Toolchain — 安装引导")
    print("=" * 60)
    print()

    agent = detect_agent()

    # Install dependencies first (all platforms)
    install_dependencies()

    print()

    if agent == "hermes":
        install_hermes()
    elif agent == "claude-code":
        install_claude_code()
    else:
        install_unknown()

    if agent != "unknown":
        check_config()

    print()
    print("-" * 60)
    print("快速验证：python doctor.py")
    print("=" * 60)


if __name__ == "__main__":
    main()
