#!/usr/bin/env python3
"""
DeepRead 初始化向导
用法: python init.py

交互式配置，生成 config.yaml。已有配置则询问是否覆盖。
"""

import os
import sys
import platform
from pathlib import Path


def get_platform():
    system = platform.system()
    if system == "Windows":
        return "windows"
    elif system == "Darwin":
        return "mac"
    else:
        return "linux"


def get_default_vault():
    """根据平台返回默认 Obsidian vault 路径"""
    home = Path.home()
    system = get_platform()
    if system == "mac":
        # macOS Obsidian 常见路径
        icloud = home / "Library" / "Mobile Documents" / "iCloud~md~obsidian" / "Documents"
        if icloud.exists():
            return str(icloud)
    return str(home / "Documents" / "知识库")


def green(text):
    return f"\033[92m{text}\033[0m"


def bold(text):
    return f"\033[1m{text}\033[0m"


def dim(text):
    return f"\033[90m{text}\033[0m"


def check_python():
    v = sys.version_info
    if v.major < 3 or (v.major == 3 and v.minor < 9):
        print(f"需要 Python >= 3.9，当前: {sys.version}")
        return False
    return True


def check_deps():
    missing = []
    for mod in ["ebooklib", "bs4", "lxml"]:
        try:
            __import__(mod.replace("bs4", "bs4"))
        except ImportError:
            missing.append(mod)
    if missing:
        print(f"缺少 Python 依赖: {', '.join(missing)}")
        print(f"请运行: pip install ebooklib beautifulsoup4 lxml chardet")
        return False
    return True


def prompt(prompt_text, default=""):
    if default:
        result = input(f"{prompt_text} [{default}]: ").strip()
        return result if result else default
    return input(f"{prompt_text}: ").strip()


def prompt_choice(prompt_text, options, default=1):
    print(f"\n{prompt_text}")
    for i, opt in enumerate(options, 1):
        marker = " (默认)" if i == default else ""
        print(f"  [{i}] {opt}{marker}")
    while True:
        result = input("> ").strip()
        if not result:
            return options[default - 1]
        try:
            idx = int(result) - 1
            if 0 <= idx < len(options):
                return options[idx]
        except ValueError:
            pass
        print(f"请输入 1-{len(options)}")


def prompt_yesno(prompt_text, default=True):
    default_str = "Y/n" if default else "y/N"
    result = input(f"{prompt_text} [{default_str}]: ").strip().lower()
    if not result:
        return default
    return result in ("y", "yes")


def validate_path(path_text, must_exist=False):
    """验证路径，展开 ~ 和环境变量"""
    path = os.path.expandvars(os.path.expanduser(path_text))
    if must_exist and not os.path.exists(path):
        return None
    return os.path.abspath(path)


def main():
    print()
    print(bold("=== DeepRead 初始化向导 ==="))
    print()

    # 环境检查
    if not check_python():
        sys.exit(1)
    if not check_deps():
        response = input("继续初始化？(依赖缺失可能导致 EPUB 解析失败) [y/N]: ")
        if response.lower() not in ("y", "yes"):
            sys.exit(1)

    # 检测现有配置
    deepread_dir = Path(__file__).parent
    config_path = deepread_dir / "config.yaml"
    if config_path.exists():
        print(f"\n检测到已有配置文件: {config_path}")
        if not prompt_yesno("是否覆盖？", default=False):
            print("已取消。要重新配置请删除 config.yaml 后重试。")
            return

    config = {"user": {}, "paths": {}, "note": {}, "reading": {}, "integrations": {}, "cognition": {}, "advanced": {}}

    # 1. 用户信息
    print(f"\n{bold('1. 基本信息')}")
    config["user"]["name"] = prompt("你的名字", "读者")
    config["user"]["preferred_name"] = prompt("怎么称呼你", config["user"]["name"])

    # 2. 路径
    print(f"\n{bold('2. 路径设置')} ({get_platform()})")
    default_vault = get_default_vault()
    vault_dir = prompt("Obsidian vault 目录", default_vault)
    config["paths"]["vault_dir"] = validate_path(vault_dir) or vault_dir
    config["paths"]["notes_dir"] = prompt("笔记保存目录", os.path.join(config["paths"]["vault_dir"], "读书", "笔记"))

    default_books = os.path.dirname(str(deepread_dir))
    config["paths"]["books_dir"] = prompt("EPUB 书籍目录", default_books)

    state_dir = os.path.join(str(deepread_dir), "state")
    config["paths"]["state_dir"] = prompt("状态文件目录", state_dir)

    config["paths"]["reading_notes"] = os.path.join(str(deepread_dir), "reading-notes.md")
    config["paths"]["cognition_profile"] = os.path.join(str(deepread_dir), "cognition_profile.json")
    config["paths"]["wiki_integration_dir"] = os.path.join(config["paths"]["vault_dir"], "读书", "笔记", "📚 LLM-Wiki 整合")

    # 3. 笔记格式
    print(f"\n{bold('3. 笔记格式')}")
    template = prompt_choice("笔记模板", [
        "obsidian-three-section (Obsidian 三段式，推荐)",
        "plain (纯 Markdown)",
        "cornell (康奈尔笔记)",
        "zettelkasten (卡片盒笔记)"
    ], default=1)
    template_key = template.split()[0]
    config["note"]["template"] = template_key
    config["note"]["use_wikilinks"] = prompt_yesno("使用 Obsidian wikilinks [[ ]]", True)
    config["note"]["date_in_frontmatter"] = prompt_yesno("在笔记 frontmatter 中加日期", False)

    # 4. 阅读设置
    print(f"\n{bold('4. 阅读偏好')}")
    config["reading"]["max_words_per_session"] = 8000
    config["reading"]["auto_advance_stage"] = False

    # 5. 集成
    print(f"\n{bold('5. 外部集成')}")
    config["integrations"]["weread"] = {
        "enabled": prompt_yesno("启用微信读书集成？", False),
        "api_key_env": "WEREAD_API_KEY",
        "api_entry": "https://i.weread.qq.com/api/agent/gateway"
    }
    config["integrations"]["obsidian"] = {"enabled": True}
    config["integrations"]["wiki"] = {"enabled": prompt_yesno("启用 LLM-Wiki 集成？", True)}

    # 6. 认知画像
    print(f"\n{bold('6. 认知画像')}")
    config["cognition"]["enabled"] = prompt_yesno("启用认知画像？（记录思维模式，让AI更懂你）", False)
    config["cognition"]["update_frequency"] = "chapter_end"

    # 7. 高级
    config["advanced"]["log_level"] = "info"
    config["advanced"]["backup_notes"] = True

    # 写入配置
    import yaml
    yaml_text = yaml.dump(config, allow_unicode=True, default_flow_style=False, sort_keys=False)

    with open(config_path, 'w', encoding='utf-8') as f:
        f.write("# DeepRead 配置文件\n")
        f.write("# 由 deepread init 生成\n")
        f.write("# 可手动编辑，重新运行 init.py 会覆盖\n\n")
        f.write(yaml_text)

    # 创建目录
    for d in [config["paths"]["state_dir"], config["paths"]["notes_dir"]]:
        os.makedirs(d, exist_ok=True)
    os.makedirs(os.path.join(config["paths"]["state_dir"], "default", "history"), exist_ok=True)

    print(f"\n{green('✓ 配置已保存到:')} {config_path}")
    print(f"{green('✓ 目录已创建')}")
    print()
    print(bold("快速开始:"))
    print(f"  1. 把 EPUB 书籍放到: {config['paths']['books_dir']}")
    print(f"  2. 在 Claude Code 中输入: /deepread 读《书名》第1章")
    print(f"  3. 笔记将保存到: {config['paths']['notes_dir']}")
    print()


if __name__ == "__main__":
    main()
