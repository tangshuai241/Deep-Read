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


def load_profile_defaults(profile_name):
    """加载 profile 默认配置，不存在则返回空。"""
    profile_dir = Path(__file__).parent / "profiles" / profile_name
    example_yaml = profile_dir / "config.example.yaml"
    if not example_yaml.exists():
        return {}
    try:
        import yaml
        with open(example_yaml, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def main():
    import argparse
    deepread_dir = Path(__file__).parent
    config_path = deepread_dir / "config.yaml"

    parser = argparse.ArgumentParser(description="DeepRead 初始化向导")
    parser.add_argument("--profile", default="", choices=["trial", "personal"],
                        help="发行形态: trial 体验版 / personal 完整版")
    args, _ = parser.parse_known_args()
    profile_name = getattr(args, "profile", "") or ""

    print()
    if profile_name:
        print(bold(f"=== DeepRead 初始化向导 [{profile_name.upper()}] ==="))
    else:
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
    if config_path.exists():
        print(f"\n检测到已有配置文件: {config_path}")
        if not prompt_yesno("是否覆盖？", default=False):
            print("已取消。要重新配置请删除 config.yaml 后重试。")
            return

    # 选择 profile（如果未通过 --profile 指定）
    if not profile_name:
        profile_choice = prompt_choice("选择发行形态", [
            "trial (体验版：手机 IM 主路径，无需 Obsidian)",
            "personal (完整版：Obsidian + Wiki + 概念卡全链路)"
        ], default=1)
        profile_name = profile_choice.split()[0]

    # 加载 profile 默认配置
    profile_defaults = load_profile_defaults(profile_name)
    is_trial = (profile_name == "trial")

    config = {"user": {}, "paths": {}, "note": {}, "reading": {}, "integrations": {}, "cognition": {},
              "advanced": {}, "llm": {}, "profile": {"name": profile_name}}

    # 使用 profile 默认值
    if profile_defaults:
        for section in ("note", "reading", "integrations", "cognition", "advanced", "profile"):
            if section in profile_defaults:
                config[section].update(profile_defaults[section])

    default_vault = get_default_vault()
    default_books = os.path.dirname(str(deepread_dir))
    state_dir = os.path.join(str(deepread_dir), "state")

    # 1. 用户信息
    print(f"\n{bold('1. 基本信息')}")
    config["user"]["name"] = prompt("你的名字", "读者")
    config["user"]["preferred_name"] = prompt("怎么称呼你", config["user"]["name"])

    # 2. 路径
    print(f"\n{bold('2. 路径设置')} ({get_platform()})")
    if is_trial:
        vault_dir = prompt("Obsidian vault 目录（可选，留空跳过）", "")
        config["paths"]["vault_dir"] = validate_path(vault_dir) if vault_dir else ""
        notes_default = os.path.join(str(deepread_dir), "notes")
        config["paths"]["notes_dir"] = prompt("笔记保存目录", notes_default)
        config["paths"]["wiki_integration_dir"] = ""
    else:
        vault_dir = prompt("Obsidian vault 目录", default_vault)
        config["paths"]["vault_dir"] = validate_path(vault_dir) or vault_dir
        config["paths"]["notes_dir"] = prompt("笔记保存目录",
            os.path.join(config["paths"]["vault_dir"], "读书", "笔记"))
        config["paths"]["wiki_integration_dir"] = os.path.join(
            config["paths"]["vault_dir"], "读书", "笔记", "📚 LLM-Wiki 整合")

    config["paths"]["books_dir"] = prompt("EPUB 书籍目录", default_books)
    config["paths"]["state_dir"] = prompt("状态文件目录", state_dir)
    config["paths"]["reading_notes"] = os.path.join(str(deepread_dir), "reading-notes.md")
    config["paths"]["cognition_profile"] = os.path.join(str(deepread_dir), "cognition_profile.json")

    # 3. 笔记格式（trial: 跳过，用默认；personal: 交互式）
    if is_trial:
        config["note"]["use_wikilinks"] = config["paths"]["vault_dir"] != ""
        config["integrations"]["obsidian"]["enabled"] = bool(config["paths"]["vault_dir"])
    else:
        print(f"\n{bold('3. 笔记格式')}")
        template = prompt_choice("笔记模板", [
            "obsidian-three-section (Obsidian 三段式，推荐)",
            "plain (纯 Markdown)"
        ], default=1)
        config["note"]["template"] = template.split()[0]
        config["note"]["use_wikilinks"] = prompt_yesno("使用 Obsidian wikilinks [[ ]]", True)
        config["note"]["date_in_frontmatter"] = prompt_yesno("在笔记 frontmatter 中加日期", False)
        config["integrations"]["wiki"]["enabled"] = prompt_yesno("启用 LLM-Wiki 集成？", True)
        config["cognition"]["enabled"] = prompt_yesno("启用认知画像？", False)

    # LLM 配置
    print(f"\n{bold('LLM 配置')}")
    print("  DeepRead 需要 LLM API 来驱动精读对话。")
    print("  支持的 provider: deepseek / anthropic / openai")

    provider = prompt_choice("选择 LLM provider", [
        "deepseek (DeepSeek，推荐)",
        "anthropic (Anthropic Claude)",
        "openai (OpenAI / 兼容接口)"
    ], default=1)
    provider_key = provider.split()[0]

    config["llm"]["provider"] = provider_key

    model_map = {"deepseek": "deepseek-v4-pro", "anthropic": "claude-sonnet-4-6", "openai": "gpt-4o"}
    config["llm"]["model"] = prompt("模型名", model_map.get(provider_key, ""))

    api_key = prompt("API Key（留空则从环境变量读取）", "")
    if api_key:
        masked = api_key[:6] + "..." if len(api_key) > 6 else "***"
        print(f"  API Key 已设置: {masked}")
    config["llm"]["api_key"] = api_key

    config["llm"]["base_url"] = prompt("自定义 base_url（OpenAI 兼容接口/中转站用，留空跳过）", "")
    config["llm"]["thinking"] = "auto"

    # 写入配置
    import yaml
    yaml_text = yaml.dump(config, allow_unicode=True, default_flow_style=False, sort_keys=False)

    with open(config_path, 'w', encoding='utf-8') as f:
        f.write("# DeepRead 配置文件\n")
        f.write(f"# Profile: {profile_name}\n")
        f.write("# 由 deepread init 生成\n")
        f.write("# 可手动编辑，重新运行 init.py 会覆盖\n\n")
        f.write(yaml_text)

    # 创建核心目录
    vault = config["paths"]["vault_dir"]
    core_dirs = [config["paths"]["notes_dir"]]
    if vault:
        core_dirs.extend([
            os.path.join(vault, "概念（抽象概念）"),
            os.path.join(vault, "我的思考"),
        ])
    if config["paths"].get("wiki_integration_dir"):
        core_dirs.append(config["paths"]["wiki_integration_dir"])
    for d in core_dirs:
        if d:
            try:
                os.makedirs(d, exist_ok=True)
            except OSError:
                pass

    state_d = config["paths"]["state_dir"]
    os.makedirs(os.path.join(state_d, "default", "history"), exist_ok=True)
    os.makedirs(os.path.join(state_d, "sessions"), exist_ok=True)
    os.makedirs(os.path.join(str(deepread_dir), "logs"), exist_ok=True)

    print(f"\n{green('✓ 配置已保存到:')} {config_path}")
    print(f"{green('✓ Profile:')} {profile_name}")
    print(f"{green('✓ 核心目录已创建')}")
    print()
    print(bold("快速开始:"))
    if is_trial:
        print(f"  1. 配置飞书 Bot（见 docs/快速启动-新手版.md）")
        print(f"  2. 启动飞书 Bot: .\\start-bot.ps1")
        print(f"  3. 手机给 Bot 发 '你好'")
    else:
        print(f"  1. 把 EPUB 书籍放到: {config['paths']['books_dir']}")
        print(f"  2. 在 Claude Code 中输入: /deepread 读《书名》第1章")
        print(f"  3. 笔记将保存到: {config['paths']['notes_dir']}")
        print(f"  4. 打开 Web 控制台: .\\start.ps1")
    print()


if __name__ == "__main__":
    main()
