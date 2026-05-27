#!/usr/bin/env python3
"""
DeepRead CLI —— 统一命令行入口
用法:
  deepread progress              # 读书进度
  deepread review                # 随机复习一篇旧笔记
  deepread think                 # 生成慢思考问题
  deepread search <关键词>       # 搜索 vault
  deepread read <书> <章>        # 提取章节 + 输出 Claude Code 启动提示
  deepread status                # 阅读状态

可从任何外部入口调用（飞书 Bot / 微信桥接 / shell）。
"""

import argparse
import json
import os
import random
import re
import subprocess
import sys
from pathlib import Path

# 统一输出编码：避免 GBK 终端乱码
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

SCRIPTS_DIR = Path(__file__).parent / "scripts"
CONFIG_PATH = Path(__file__).parent / "config.yaml"


def load_config():
    if CONFIG_PATH.exists():
        try:
            import yaml
            with open(CONFIG_PATH, encoding='utf-8') as f:
                return yaml.safe_load(f)
        except ImportError:
            pass
    return {}


def run_script(name, *args):
    """运行 scripts/ 下的脚本并返回 stdout"""
    script = SCRIPTS_DIR / name
    cmd = [sys.executable, str(script)] + list(args)
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(cmd, capture_output=True, text=True,
                            encoding='utf-8', errors='replace', env=env)
    return result.stdout, result.stderr, result.returncode


def cmd_progress():
    config = load_config()
    rn_path = config.get("paths", {}).get("reading_notes",
        str(Path(__file__).parent / "reading-notes.md"))
    if os.path.exists(rn_path):
        with open(rn_path, encoding='utf-8') as f:
            content = f.read()
        # 提取关键行
        for line in content.split('\n'):
            line = line.strip()
            if line.startswith('- 《') or line.startswith('- 「'):
                print(line)
            elif '上次' in line:
                print(line)
    else:
        print("暂无读书进度记录")

    # 补充状态信息
    stdout, _, _ = run_script("state.py", "show")
    print(stdout)


def cmd_review():
    config = load_config()
    notes_dir = config.get("paths", {}).get("notes_dir", "")
    if not notes_dir or not os.path.exists(notes_dir):
        print("笔记目录不存在")
        return

    # 收集所有笔记
    notes = []
    for root, dirs, files in os.walk(notes_dir):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for f in files:
            if f.endswith('.md') and 'LLM-Wiki' not in root:
                notes.append(os.path.join(root, f))

    if not notes:
        print("还没有笔记，先去读一章吧")
        return

    note = random.choice(notes)
    rel = os.path.relpath(note, notes_dir)
    print(f"随机复习: {rel}")
    print()

    with open(note, encoding='utf-8') as f:
        content = f.read()

    # 只显示 frontmatter 后的内容（跳过元数据）
    parts = content.split('---', 2)
    body = parts[2] if len(parts) >= 3 else content
    print(body[:1500])
    print()
    print("---")
    print('试试用大白话重新解释这篇笔记的核心观点。然后输入 "/苏格拉底" 进入深化。')


def cmd_think():
    config = load_config()
    state_path = config.get("paths", {}).get("state_dir",
        str(Path(__file__).parent / "state"))
    current = os.path.join(state_path, "default", "current.json")

    book = "未知"
    chapter = "?"
    summary = ""
    if os.path.exists(current):
        with open(current, encoding='utf-8-sig') as f:
            s = json.load(f)
            c = s.get("current", {})
            book = c.get("book", "未知")
            chapter = c.get("chapter", "?")
            summary = s.get("session_summary", "")

    print(f"基于《{book}》第{chapter}章")
    if summary:
        print(f"最近讨论: {summary}")
    print()
    print("今天只想这一个问题，不用急着回：")
    print()
    print("如果你今天观察到的所有'确定无疑'的判断，其实都是系统1替你选了其中一个解释——")
    print("你现在能想起今天哪个时刻，你可能被系统1替你做主了？")
    print()
    print("（看到任何让你立刻相信、立刻反感、立刻下结论的事，都记一下。）")


def cmd_search(keyword):
    stdout, stderr, rc = run_script(
        "search_vault.py",
        "--query", keyword,
        "--mode", "hybrid",
        "--scope", "core",
        "--include-wiki",
        "--limit", "10",
    )
    if rc != 0:
        print(stderr, file=sys.stderr)
        return
    print(stdout)


def cmd_doctor(args=None):
    """自检：检查依赖、路径、配置、LLM、飞书、Obsidian"""
    import importlib
    deep = getattr(args, "deep", False)
    errors = []
    warnings = []
    ok = []

    def check(condition, label, severity="error"):
        if severity == "error":
            (errors if not condition else ok).append(label)
        else:
            (warnings if not condition else ok).append(label)

    # 1. Python 版本
    py_ok = sys.version_info >= (3, 9)
    check(py_ok, f"Python {sys.version.split()[0]} >= 3.9")

    # 2. 依赖包
    for mod, pkg in [("ebooklib", "ebooklib"), ("bs4", "beautifulsoup4"),
                      ("lxml", "lxml"), ("chardet", "chardet"), ("yaml", "pyyaml")]:
        try:
            importlib.import_module(mod)
            check(True, f"包 {pkg} 可用")
        except ImportError:
            check(False, f"缺少包: pip install {pkg}")

    # 3. config.yaml
    config = load_config()
    check(bool(config), "config.yaml 可读取")

    # 4. 路径检查
    for key, label in [("books_dir", "书籍目录"), ("vault_dir", "Obsidian Vault"),
                        ("notes_dir", "笔记目录"), ("state_dir", "状态目录")]:
        p = config.get("paths", {}).get(key, "")
        if p:
            exists = os.path.exists(p)
            if key == "notes_dir":
                parent_ok = os.path.exists(os.path.dirname(p))
                check(parent_ok, f"{label}: {p} (可创建)", "warning" if not exists else None)
            elif key == "state_dir":
                check(exists, f"{label}: {p}", "warning" if not exists else None)
            else:
                check(exists, f"{label}: {p}")
        else:
            check(False, f"{label} 未配置")

    # 5. LLM 配置
    llm_cfg = config.get("llm", {})
    provider = llm_cfg.get("provider", "")
    model = llm_cfg.get("model", "")
    base_url = llm_cfg.get("base_url", "")
    thinking = llm_cfg.get("thinking", "auto")
    check(bool(model), f"LLM 模型已配置: {model}")

    # API Key 检查
    if provider:
        api_key = llm_cfg.get("api_key", "")
        env_key_map = {
            "deepseek": "DEEPSEEK_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "openai": "OPENAI_API_KEY",
        }
        env_key = env_key_map.get(provider, "")
        if api_key:
            check(True, f"LLM API Key (config): {provider}")
        elif env_key and os.environ.get(env_key):
            check(True, f"LLM API Key (env {env_key}): {provider}")
        else:
            check(False, f"LLM API Key 缺失: 在 config 或环境变量 {env_key} 中设置", "warning" if deep else "error")
    else:
        # 自动检测
        found_keys = []
        for pname, env_key in [("deepseek", "DEEPSEEK_API_KEY"), ("anthropic", "ANTHROPIC_API_KEY"), ("openai", "OPENAI_API_KEY")]:
            if os.environ.get(env_key):
                found_keys.append(pname)
        if found_keys:
            check(True, f"检测到 API Key: {', '.join(found_keys)}", "warning" if len(found_keys) > 1 else None)
        else:
            check(False, "未检测到任何 LLM API Key (DEEPSEEK/ANTHROPIC/OPENAI)", "warning" if deep else "error")

    if base_url:
        check(True, f"LLM 自定义 base_url: {base_url}")

    # 6. 飞书 CLI
    from adapters.feishu_bot import _find_lark_cli
    lark_path = _find_lark_cli()
    if lark_path != "lark-cli":
        check(True, f"lark-cli: {lark_path}")
    else:
        # 尝试从 PATH 找
        from shutil import which
        if which("lark-cli") or which("lark-cli.cmd"):
            check(True, "lark-cli 在 PATH 中")
        else:
            check(False, "lark-cli 未找到，飞书功能不可用", "warning")

    # 7. 模板文件
    tmpl_dir = Path(__file__).parent / "templates"
    if tmpl_dir.exists():
        tmpls = list(tmpl_dir.glob("*.md"))
        check(len(tmpls) >= 1, f"模板目录: {len(tmpls)} 个模板 ({', '.join(t.name for t in tmpls)})")
    else:
        check(False, "模板目录不存在")

    # 8. EPUB 连通性
    books_dir = config.get("paths", {}).get("books_dir", "")
    if books_dir and os.path.exists(books_dir):
        epubs = [f for f in os.listdir(books_dir) if f.endswith('.epub')]
        if epubs:
            check(True, f"找到 {len(epubs)} 个 EPUB: {', '.join(epubs[:3])}")
        else:
            check(False, f"未找到 EPUB 文件在 {books_dir}", "warning")
    else:
        check(False, "书籍目录不存在或未配置", "warning")

    # 9. 脚本自检（含 note_quality.py）
    for script in ["extract_epub.py", "state.py", "write_note.py", "search_vault.py",
                   "learning_contract.py", "note_quality.py"]:
        sp = SCRIPTS_DIR / script
        check(sp.exists(), f"脚本 {script} 存在")

    # 10. Obsidian 核心目录
    vault = config.get("paths", {}).get("vault_dir", "")
    if vault and os.path.exists(vault):
        for subdir in ["读书", "概念（抽象概念）", "我的思考"]:
            spath = os.path.join(vault, subdir)
            check(os.path.exists(spath), f"Obsidian/{subdir} 存在", "warning" if "概念" in subdir else None)
        wiki_dir = os.path.join(vault, "读书", "笔记", "📚 LLM-Wiki 整合") if vault else ""
        if os.path.exists(wiki_dir):
            check(True, "LLM-Wiki 整合目录存在")
        else:
            check(False, "LLM-Wiki 整合目录不存在", "warning")

    # 11. 概念卡数量（用户 vault + trial 基础包）
    concept_count = 0
    trial_count = 0
    concept_dir = os.path.join(vault, "概念（抽象概念）") if vault else ""
    if os.path.exists(concept_dir):
        concept_count = len([f for f in Path(concept_dir).rglob("*.md")])
    trial_dir = _get_trial_concept_dir()
    if os.path.exists(trial_dir):
        trial_count = len([f for f in Path(trial_dir).rglob("*.md")])
    total_concepts = concept_count + trial_count
    if total_concepts > 0:
        parts = []
        if concept_count:
            parts.append(f"用户 {concept_count}")
        if trial_count:
            parts.append(f"基础包 {trial_count}")
        check(True, f"概念卡: {', '.join(parts)} ({total_concepts} 张)")
    else:
        check(False, "概念卡数量为 0", "warning")

    # 11b. Profile 健康检查
    profile_name, is_legacy = _resolve_profile(config)
    if is_legacy:
        check(False, "config.yaml 未声明 profile.name，已按 personal 处理。建议添加 profile.name: personal", "warning")
    else:
        check(True, f"Profile: {profile_name}")
    if profile_name == "trial":
        if not config.get("integrations", {}).get("wiki", {}).get("enabled"):
            check(True, "Trial: LLM-Wiki 已关闭（预期行为）")
        if trial_count > 0:
            check(True, f"Trial: 基础概念包 {trial_count} 张可用")
        else:
            check(False, "Trial: 基础概念包缺失", "warning")
    else:
        if config.get("integrations", {}).get("wiki", {}).get("enabled", True):
            wiki_dir = config.get("paths", {}).get("wiki_integration_dir", "")
            if wiki_dir and os.path.exists(wiki_dir):
                check(True, "Personal: LLM-Wiki 已启用")
            else:
                check(False, "Personal: LLM-Wiki 已启用但目录不存在", "warning")

    # 12. 飞书 Bot 锁文件状态
    lock = _read_lock()
    if lock:
        lock_pid = int(lock.get("pid", 0))
        if _pid_is_running(lock_pid):
            check(True, f"飞书 Bot 监听运行中 (PID={lock_pid})")
            # 检查重复
            dups = _find_duplicate_listeners(lock_pid)
            if dups:
                check(False, f"发现 {len(dups)} 个重复 listener 进程", "warning")
        else:
            check(False, f"飞书 Bot 锁文件陈旧 (PID={lock_pid} 已退出)", "warning")

    # ═══ --deep 额外检查 ═══
    if deep:
        # EPUB 连通性
        if books_dir and os.path.exists(books_dir):
            epubs = [f for f in os.listdir(books_dir) if f.endswith('.epub')]
            if epubs:
                stdout, stderr, rc = run_script("extract_epub.py", "--book", epubs[0], "--meta", "--json")
                if rc == 0 and stdout.strip():
                    try:
                        json.loads(stdout)
                        check(True, f"EPUB 解析连通: {epubs[0]}")
                    except json.JSONDecodeError:
                        check(False, f"EPUB 解析输出异常: {epubs[0]}", "warning")
                else:
                    check(False, f"EPUB 解析失败: {epubs[0]} ({stderr.strip()})", "warning")

        # LLM 连通性
        api_key = llm_cfg.get("api_key", "")
        base_url = llm_cfg.get("base_url", "")
        if provider == "deepseek" or (not provider and os.environ.get("DEEPSEEK_API_KEY")):
            api_key = api_key or os.environ.get("DEEPSEEK_API_KEY", "")
            base_url = base_url or "https://api.deepseek.com/v1"
            try:
                import openai
                client = openai.OpenAI(api_key=api_key, base_url=base_url)
                r = client.models.list()
                check(True, f"DeepSeek API 连通: {len(list(r))} models")
            except Exception as e:
                check(False, f"DeepSeek API 不通: {str(e)[:80]}", "warning")
        elif provider == "anthropic" or (not provider and os.environ.get("ANTHROPIC_API_KEY")):
            api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
            try:
                import anthropic
                client = anthropic.Anthropic(api_key=api_key)
                r = client.messages.create(
                    model=model or "claude-sonnet-4-6",
                    max_tokens=10,
                    messages=[{"role": "user", "content": "ping"}],
                )
                check(True, "Anthropic API 连通")
            except Exception as e:
                check(False, f"Anthropic API 不通: {str(e)[:80]}", "warning")

        # 飞书 CLI 基础能力
        if lark_path != "lark-cli" or which("lark-cli") or which("lark-cli.cmd"):
            try:
                result = subprocess.run(
                    [lark_path, "im", "+messages-send", "--help"],
                    capture_output=True, text=True, encoding="utf-8", errors="replace",
                    timeout=10,
                )
                check(result.returncode == 0, f"飞书 CLI 基础能力正常")
            except Exception as e:
                check(False, f"飞书 CLI 检测失败: {str(e)[:80]}", "warning")

        # 笔记质量抽样
        notes_dir = config.get("paths", {}).get("notes_dir", "")
        if notes_dir and os.path.exists(notes_dir):
            md_files = list(Path(notes_dir).rglob("*.md"))
            sample_files = [f for f in md_files if "LLM-Wiki" not in str(f)]
            if sample_files:
                sample = random.choice(sample_files)
                try:
                    stdout, _, rc = run_script("note_quality.py", "--path", str(sample), "--json")
                    if rc == 0 and stdout.strip():
                        qr = json.loads(stdout)
                        score = qr.get("score", 0)
                        check(True, f"笔记质量抽样 ({sample.name}): 得分 {score}", "warning" if score < 50 else None)
                    else:
                        check(False, f"笔记质量检查失败: {stderr.strip()[:80]}", "warning")
                except Exception as e:
                    check(False, f"笔记质量异常: {str(e)[:80]}", "warning")

    # ── 输出报告 ──
    total = len(ok) + len(warnings) + len(errors)
    print(f"DeepRead 健康检查 — {len(ok)} PASS, {len(warnings)} WARN, {len(errors)} FAIL (共 {total} 项)")
    if deep:
        print("  (深度检查模式)")
    print()

    if errors:
        for item in errors:
            print(f"  FAIL  {item}")
        print()

    if warnings:
        for item in warnings:
            print(f"  WARN  {item}")
        print()

    if ok:
        for item in ok[:5]:
            print(f"  PASS  {item}")
        if len(ok) > 5:
            print(f"  ... 还有 {len(ok) - 5} 项通过")

    if not errors:
        print("\n  全部必检项通过。可以开始精读了。")


def cmd_read(book, chapter):
    """提取章节并输出 Claude Code 启动提示"""
    stdout, stderr, rc = run_script("extract_epub.py", "--book", book, "--chapter", chapter, "--json")
    if rc != 0:
        print(f"提取失败: {stderr}", file=sys.stderr)
        return

    data = json.loads(stdout)
    ch = data["chapter"]
    print(f"# {data['book']['title']} — {ch['title']}")
    print(f"# 字数: {ch['word_count']} | 小节: {len(data['sections'])}")
    print()

    # 显示第一节的前 300 字
    if data["sections"]:
        first = data["sections"][0]
        preview = first["text"][:300]
        print(f"## {first['title']}")
        print(preview)
        if len(first["text"]) > 300:
            print("...")
        print()

    print("---")
    print("在 Claude Code 中输入以下命令开始精读:")
    print(f"  /deepread 读《{data['book']['title']}》第{ch['index']}章")
    print()
    if ch["word_count"] > 8000:
        print(f"[!] 本章 {ch['word_count']} 字，建议分次读")


def cmd_status():
    stdout, _, _ = run_script("state.py", "show")
    print(stdout)


def cmd_contract(args):
    stdout, stderr, rc = run_script("learning_contract.py", *(args.contract_args or []))
    if rc != 0:
        print(stderr, file=sys.stderr)
        return
    print(stdout)


def cmd_chat(args):
    """启动独立 Agent 对话"""
    agent_path = Path(__file__).parent / "agent.py"
    if not agent_path.exists():
        print("agent.py 不存在，请确认文件完整")
        return
    cmd = [sys.executable, str(agent_path)]
    if args.resume:
        cmd.extend(["--resume", args.resume])
    if args.model:
        cmd.extend(["--model", args.model])
    if args.provider:
        cmd.extend(["--provider", args.provider])
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    subprocess.run(cmd, env=env)


def cmd_quality(args):
    """笔记质量检查"""
    stdout, stderr, rc = run_script("note_quality.py", "--path", args.note_path,
                                     *(["--json"] if getattr(args, "json", False) else []))
    if rc != 0:
        print(stderr, file=sys.stderr)
        print(stdout)
    else:
        print(stdout)


# ═══════════════════════════════════════════════════════════════
# Profile 管理命令
# ═══════════════════════════════════════════════════════════════

READING_MODES = {
    "concept_deep_read": {
        "name": "概念精读",
        "desc": "四阶段费曼+苏格拉底+联想，适合概念密集型书籍",
        "target": "理解核心概念及其认知机制",
        "sections": ["引用原文", "我的理解", "让我想到", "待探索"],
        "trial": True,
        "suggest_patterns": ["思考快与慢", "认知", "心理学", "行为经济学",
                            "思维", "判断", "决策", "思考"],
    },
    "proposition_dialogue": {
        "name": "命题辨析",
        "desc": "逐命题挑战和重构，适合观点型、哲学类书籍",
        "target": "辨析命题的前提、边界和隐含假设",
        "sections": ["核心命题", "作者论证", "我的质疑", "待探索"],
        "trial": True,
        "suggest_patterns": ["被讨厌的勇气", "哲学", "人生", "意义",
                            "存在", "自由", "幸福", "勇气"],
    },
    "method_conversion": {
        "name": "方法转化",
        "desc": "提取方法→验证→改造→归档，适合工具书/方法论",
        "target": "将书中方法转化为个人可执行的步骤",
        "sections": ["方法提取", "前提条件", "我的场景", "改造方案", "行动清单"],
        "trial": True,
        "suggest_patterns": ["方法", "工具", "技巧", "指南", "手册",
                            "How To", "搞定", "GTD", "效率"],
    },
    "exam_mastery": {
        "name": "考试掌握",
        "desc": "高频考点→理解→记忆→自测，适合教材/资格证考试",
        "target": "掌握考点并能通过自测验证",
        "sections": ["考点梳理", "核心理解", "易错对比", "自测题", "待复习"],
        "trial": True,
        "suggest_patterns": ["一级建造师", "考试", "教材", "资格证",
                            "备考", "真题", "考点", "习题"],
    },
    "textbook_derivation": {
        "name": "教材推导",
        "desc": "逐章还原推导链，适合理论教材/数学/物理",
        "target": "理解每一步推导的前提和逻辑",
        "sections": ["推导链还原", "关键步理解", "边界条件", "课后验证"],
        "trial": False,
        "suggest_patterns": ["数学", "物理", "推导", "公式", "定理",
                            "证明", "原理"],
    },
    "standard_lookup": {
        "name": "规范检索",
        "desc": "快速定位→理解条文→关联实际场景，适合工程规范/标准",
        "target": "理解条文并能定位到实际工程场景",
        "sections": ["条文定位", "条文理解", "工程场景", "边界说明"],
        "trial": False,
        "suggest_patterns": ["规范", "标准", "GB", "JT", "条文",
                            "设计", "施工", "验收"],
    },
    "case_review": {
        "name": "案例复盘",
        "desc": "案例→决策链→替代方案→教训提炼，适合商业/工程案例",
        "target": "从案例中提炼可复用的决策模式",
        "sections": ["案例事实", "决策链还原", "替代方案", "教训提炼", "可复用原则"],
        "trial": False,
        "suggest_patterns": ["案例", "复盘", "事故", "失败", "教训",
                            "项目", "实践"],
    },
    "literature_experience": {
        "name": "文学体验",
        "desc": "沉浸→感受→共鸣→表达，适合小说/散文/传记",
        "target": "深度体验文本，形成个人化的感受和表达",
        "sections": ["情境还原", "人物/主题理解", "我的共鸣", "延伸联想"],
        "trial": False,
        "suggest_patterns": ["小说", "散文", "传记", "文学", "故事",
                            "回忆录", "随笔"],
    },
}


def _resolve_profile(config):
    """解析 profile：旧配置无 profile.name 则默认 personal。"""
    profile = config.get("profile", {})
    name = profile.get("name", "")
    if name in ("trial", "personal"):
        return name, False  # 已声明
    return "personal", True  # 旧配置自动兼容为 personal


def cmd_profile(args):
    """查看当前 profile"""
    config = load_config()
    profile = config.get("profile", {})
    profile_name, is_legacy = _resolve_profile(config)

    print(f"当前 Profile: {profile_name}")
    if is_legacy:
        print("  (旧配置未声明 profile.name，已按 personal 处理)")
        print("  建议在 config.yaml 的 profile: 段添加 name: personal")
    print(f"  配置路径: {CONFIG_PATH}")
    print()

    if profile_name == "trial":
        print("  [Trial 体验版]")
        print("  - IM-first 手机入口")
        print("  - Obsidian: " + ("启用" if config.get("integrations", {}).get("obsidian", {}).get("enabled") else "可选"))
        print("  - LLM-Wiki: 关闭")
        print("  - 概念卡: 基础包")
        print("  - 阅读模式: 4 个常用")
        print("  - 认知画像: 关闭")
    else:
        print("  [Personal 完整版]")
        print("  - Obsidian: " + ("启用" if config.get("integrations", {}).get("obsidian", {}).get("enabled") else "未启用"))
        print("  - LLM-Wiki: " + ("启用" if config.get("integrations", {}).get("wiki", {}).get("enabled") else "关闭"))
        print("  - 概念卡: 完整扫描 + trial 基础包 fallback")
        print("  - 阅读模式: 全部 8 个")
        print("  - 认知画像: " + ("启用" if config.get("cognition", {}).get("enabled") else "关闭"))
    print()
    print("运行 python cli.py doctor 检查配置健康度")


def cmd_modes(args):
    """阅读模式管理"""
    config = load_config()
    profile_name, _ = _resolve_profile(config)
    is_trial = (profile_name == "trial")

    sub_cmd = getattr(args, "modes_cmd", "list")

    if sub_cmd == "list":
        _modes_list(is_trial)
    elif sub_cmd == "suggest":
        book_hint = getattr(args, "book_hint", "")
        _modes_suggest(book_hint, is_trial)
    elif sub_cmd == "show":
        mode_key = getattr(args, "mode_key", "")
        _modes_show(mode_key, is_trial)
    else:
        print("用法: python cli.py modes {list|suggest|show}")
        print("  list     — 列出可用阅读模式")
        print("  suggest  — 根据书名建议模式")
        print("  show     — 展示某模式的详细说明")


def _modes_list(is_trial=False):
    print(f"可用阅读模式（{'Trial 体验版' if is_trial else 'Personal 完整版'}）:")
    print()
    for key, mode in READING_MODES.items():
        if is_trial and not mode["trial"]:
            continue
        print(f"  {key}")
        print(f"    {mode['name']} — {mode['desc']}")
        print(f"    目标: {mode['target']}")
        print()


def _modes_suggest(book_hint, is_trial=False):
    if not book_hint:
        print("请提供书名: python cli.py modes suggest \"书名\"")
        return

    best_mode = None
    best_score = 0

    for key, mode in READING_MODES.items():
        if is_trial and not mode["trial"]:
            continue
        score = sum(1 for p in mode.get("suggest_patterns", [])
                   if p.lower() in book_hint.lower())
        if score > best_score:
            best_score = score
            best_mode = key

    if best_mode and best_score > 0:
        mode = READING_MODES[best_mode]
        print(f"《{book_hint}》建议使用: {mode['name']} ({best_mode})")
        print(f"  原因: {mode['desc']}")
        print(f"  目标: {mode['target']}")
    else:
        print(f"《{book_hint}》推荐: 概念精读 (concept_deep_read)")
        print("  无法自动判断类型，默认使用概念精读模式")
        print("  可手动指定: 切换成考试模式 / 用工具书模式读")


def _modes_show(mode_key, is_trial=False):
    if mode_key not in READING_MODES:
        print(f"未知模式: {mode_key}")
        print(f"运行 python cli.py modes list 查看可用模式")
        return

    mode = READING_MODES[mode_key]
    if is_trial and not mode["trial"]:
        print(f"{mode['name']} 在 Trial 版中不可用")
        return

    print(f"{mode['name']} ({mode_key})")
    print(f"  说明: {mode['desc']}")
    print(f"  目标: {mode['target']}")
    print(f"  笔记段落: {', '.join(mode['sections'])}")
    print()


# ═══════════════════════════════════════════════════════════════
# 概念卡管理命令
# ═══════════════════════════════════════════════════════════════

def _get_concept_dir(config):
    vault = config.get("paths", {}).get("vault_dir", "")
    if vault:
        return os.path.join(vault, "概念（抽象概念）")
    return ""


def _get_trial_concept_dir():
    return os.path.join(str(Path(__file__).parent), "profiles", "trial", "concepts")


def _get_all_concept_dirs(config):
    """返回所有概念卡目录列表（用户 vault + trial 基础包）。"""
    dirs = []
    user_dir = _get_concept_dir(config)
    if user_dir and os.path.exists(user_dir):
        dirs.append(("用户 vault", user_dir))
    trial_dir = _get_trial_concept_dir()
    if os.path.exists(trial_dir):
        dirs.append(("Trial 基础包", trial_dir))
    return dirs


def _get_notes_dir_from_config(config):
    return config.get("paths", {}).get("notes_dir", "")


def _iter_concept_files(config):
    for _, d in _get_all_concept_dirs(config):
        for f in Path(d).rglob("*.md"):
            yield f


def cmd_concepts(args):
    sub_cmd = getattr(args, "concepts_cmd", None)
    config = load_config()

    if sub_cmd == "scan":
        _concepts_scan(config)
    elif sub_cmd == "aliases":
        _concepts_aliases(config)
    elif sub_cmd == "missing":
        _concepts_missing(config)
    elif sub_cmd == "report":
        _concepts_report(config)
    else:
        print("用法: python cli.py concepts {scan|aliases|missing|report}")
        print("  scan     — 盘点已有概念卡")
        print("  aliases  — 检查概念卡别名覆盖")
        print("  missing  — 发现读书笔记中的高频概念候选")
        print("  report   — 概念卡覆盖率报告")


def _concepts_scan(config):
    """扫描已有概念卡（用户 vault + trial 基础包）"""
    dirs = _get_all_concept_dirs(config)
    if not dirs:
        print("未找到任何概念卡目录")
        print("  - 用户 vault: 请在 Obsidian 中创建 '概念（抽象概念）' 目录")
        print("  - Trial 基础包: profiles/trial/concepts/")
        return

    from collections import defaultdict
    total = 0

    for source_label, d in dirs:
        cards = list(Path(d).rglob("*.md"))
        total += len(cards)
        print(f"[{source_label}] ({len(cards)} 张)")

        groups = defaultdict(list)
        for f in cards:
            rel = os.path.relpath(f, d)
            parts = rel.split(os.sep)
            group = parts[0] if len(parts) > 1 else "(根目录)"
            groups[group].append(os.path.splitext(parts[-1])[0])

        for group, names in sorted(groups.items()):
            if len(dirs) > 1 or group != "(根目录)":
                print(f"  [{group}] ({len(names)} 张)")
            for name in sorted(names)[:10]:
                print(f"    - {name}")
            if len(names) > 10:
                print(f"    ... 还有 {len(names) - 10} 张")
        print()

    print(f"概念卡总计: {total} 张")


def _concepts_aliases(config):
    """检查概念卡的别名覆盖"""
    cards = list(_iter_concept_files(config))
    if not cards:
        print("未找到概念卡")
        return

    with_aliases = []
    without_aliases = []

    for f in cards:
        try:
            with open(f, encoding="utf-8") as fh:
                fm = fh.read(3000)
            if fm.startswith("---"):
                end = fm.find("---", 3)
                fm = fm[3:end] if end > 0 else ""
            else:
                fm = ""
        except Exception:
            fm = ""

        has = bool(re.search(r"^(aliases|alias|别名):", fm, re.M))
        name = os.path.splitext(os.path.basename(f))[0]
        if has:
            with_aliases.append(name)
        else:
            without_aliases.append(name)

    total = len(cards)
    print(f"概念卡别名覆盖: {len(with_aliases)}/{total} "
          f"({100 * len(with_aliases) // max(total, 1)}%)")
    print()

    if without_aliases:
        print(f"缺少别名的概念卡 ({len(without_aliases)} 张):")
        for name in sorted(without_aliases):
            print(f"  - {name}")
    else:
        print("所有概念卡都有别名配置。")


def _concepts_missing(config):
    """从读书笔记中发现高频概念候选"""
    notes_dir = _get_notes_dir_from_config(config)
    if not notes_dir or not os.path.exists(notes_dir):
        print("笔记目录不存在")
        return

    # 收集已有概念卡标题
    existing = set()
    for f in _iter_concept_files(config):
        existing.add(os.path.splitext(os.path.basename(f))[0])

    # 从笔记正文中提取 wikilinks 和潜在概念
    from collections import Counter
    link_counter = Counter()
    concept_pattern = re.compile(r"\[\[(.+?)(?:\|.+?)?\]\]")

    for md_file in Path(notes_dir).rglob("*.md"):
        if "LLM-Wiki" in str(md_file):
            continue
        try:
            with open(md_file, encoding="utf-8") as f:
                content = f.read()
            # 只统计我的理解和让我想到中的链接
            for section in ("💭 我的理解", "🔗 让我想到"):
                sec_match = re.search(rf"##\s+{re.escape(section)}\s*\n(.*?)(?=\n##\s+|\Z)", content, re.S)
                if sec_match:
                    for link in concept_pattern.findall(sec_match.group(1)):
                        link_counter[link] += 1
        except Exception:
            continue

    # 过滤掉已有概念卡和低频率的
    missing = [(title, count) for title, count in link_counter.most_common(50)
               if title not in existing and count >= 1]

    if not missing:
        # 放宽：也检查笔记中的粗体文本（可能是概念名）
        bold_pattern = re.compile(r"\*\*(.+?)\*\*")
        for md_file in Path(notes_dir).rglob("*.md"):
            if "LLM-Wiki" in str(md_file):
                continue
            try:
                with open(md_file, encoding="utf-8") as f:
                    for match in bold_pattern.findall(f.read()):
                        name = match.strip()
                        if len(name) >= 2 and len(name) <= 20 and name not in existing:
                            link_counter[name] += 1
            except Exception:
                continue
        missing = [(title, count) for title, count in link_counter.most_common(50)
                   if title not in existing and count >= 2]

    if missing:
        print(f"发现 {len(missing)} 个候选概念（未建卡）:")
        print()
        for title, count in missing[:20]:
            print(f"  [{count}] {title}")
        if len(missing) > 20:
            print(f"  ... 还有 {len(missing) - 20} 个")
    else:
        print("未发现缺失概念。所有常用概念都已建卡。")


def _concepts_report(config):
    """概念卡覆盖率报告（profile-aware：用户 vault + trial 基础包）"""
    profile_name, _ = _resolve_profile(config)

    # 按来源分别统计
    dirs = _get_all_concept_dirs(config)
    all_cards = []
    source_counts = {}

    for source_label, d in dirs:
        cards = list(Path(d).rglob("*.md"))
        all_cards.extend(cards)
        source_counts[source_label] = len(cards)

    total = len(all_cards)

    # 别名覆盖
    with_aliases = 0
    for f in all_cards:
        try:
            with open(f, encoding="utf-8") as fh:
                fm = fh.read(3000)
            if fm.startswith("---"):
                end = fm.find("---", 3)
                fm = fm[3:end] if end > 0 else ""
            else:
                fm = ""
        except Exception:
            fm = ""
        if re.search(r"^(aliases|alias|别名):", fm, re.M):
            with_aliases += 1

    # 笔记链接覆盖
    notes_dir = _get_notes_dir_from_config(config)
    existing_titles = {os.path.splitext(os.path.basename(f))[0] for f in all_cards}
    linked_concepts = set()
    total_notes = 0

    if notes_dir and os.path.exists(notes_dir):
        for md_file in Path(notes_dir).rglob("*.md"):
            if "LLM-Wiki" in str(md_file):
                continue
            total_notes += 1
            try:
                with open(md_file, encoding="utf-8") as f:
                    for link in re.findall(r"\[\[(.+?)\]\]", f.read()):
                        title = link.split("|", 1)[0].strip()
                        if title in existing_titles:
                            linked_concepts.add(title)
            except Exception:
                continue

    print("概念卡覆盖率报告")
    print("─" * 40)

    # 按来源展示
    for source_label, count in source_counts.items():
        print(f"  [{source_label}]: {count} 张")
    print(f"  总计:           {total}")
    print(f"  有别名:         {with_aliases} ({100 * with_aliases // max(total, 1)}%)")
    print(f"  被笔记引用:     {len(linked_concepts)} ({100 * len(linked_concepts) // max(total, 1)}%)")
    print(f"  笔记总数:       {total_notes}")

    # trial 用户额外提示
    if profile_name == "trial":
        trial_count = source_counts.get("Trial 基础包", 0)
        user_count = source_counts.get("用户 vault", 0)
        print()
        print(f"  Trial 版: {trial_count} 张基础包可用，无需用户建卡")
        if not notes_dir or total_notes == 0:
            print("  尚未有读书笔记，链接覆盖暂无数据")
    print()

    if total > 0:
        unlinked = existing_titles - linked_concepts
        if unlinked and total_notes > 0:
            print(f"未被任何笔记引用的概念卡 ({len(unlinked)}):")
            for name in sorted(unlinked)[:10]:
                print(f"  - {name}")
            if len(unlinked) > 10:
                print(f"  ... 还有 {len(unlinked) - 10} 个")


# ═══════════════════════════════════════════════════════════════
# Bot 管理命令
# ═══════════════════════════════════════════════════════════════

BASE_DIR = Path(__file__).parent
LOCK_PATH = BASE_DIR / "state" / "feishu_bot.listen.lock"
BOT_LOG_PATH = BASE_DIR / "logs" / "feishu_bot.log"


def _safe_print(text):
    """安全打印，绕过 GBK 终端编码问题。"""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", errors="replace").decode("ascii"))


def _pid_is_running(pid):
    """Windows: 通过 tasklist 检查 PID 是否存在。"""
    if not pid:
        return False
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=5,
        )
        return str(pid) in result.stdout
    except Exception:
        return False


def _read_lock():
    """读取锁文件，返回 dict 或 None"""
    if not LOCK_PATH.exists():
        return None
    try:
        return json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def _get_child_processes(parent_pid):
    """获取指定 PID 的子进程列表（Windows: wmic）。"""
    children = []
    try:
        result = subprocess.run(
            ["wmic", "process", "where", f"ParentProcessId={parent_pid}",
             "get", "ProcessId,CommandLine", "/format:csv"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=10,
        )
        for line in result.stdout.strip().split("\n")[2:]:  # 跳过头
            line = line.strip()
            if not line:
                continue
            parts = line.rsplit(",", 2)
            if len(parts) >= 2:
                children.append({"pid": parts[-1].strip(), "cmd": parts[-2].strip() if len(parts) >= 3 else ""})
    except Exception:
        # 简化：通过 tasklist 查找 lark-cli 相关进程
        try:
            result = subprocess.run(
                ["tasklist", "/FO", "CSV", "/NH"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=5,
            )
            for line in result.stdout.strip().split("\n"):
                if "lark-cli" in line.lower():
                    parts = [p.strip('"') for p in line.split(",")]
                    if len(parts) >= 2:
                        children.append({"pid": parts[1].strip(), "cmd": parts[0].strip()})
        except Exception:
            pass
    return children


def cmd_bot(args):
    """飞书 Bot 进程管理"""
    sub_cmd = getattr(args, "bot_cmd", None)

    if sub_cmd == "status":
        _bot_status()
    elif sub_cmd == "start":
        _bot_start(args)
    elif sub_cmd == "stop":
        _bot_stop(args)
    elif sub_cmd == "restart":
        _bot_restart(args)
    else:
        print("用法: python cli.py bot {status|start|stop|restart}")
        print("  status   — 查看监听状态")
        print("  start    — 后台启动监听 (--reply 开启回复)")
        print("  stop     — 停止监听 (--force 强制清理陈旧锁)")
        print("  restart  — 重启监听")


def _bot_status():
    """显示飞书 Bot 监听状态"""
    lock = _read_lock()

    if lock is None:
        print("飞书 Bot 未在运行（无锁文件）")
        if LOCK_PATH.exists():
            print(f"  [!] 锁文件存在但无法解析: {LOCK_PATH}")
        return

    pid = int(lock.get("pid", 0))
    started_at = lock.get("started_at", "未知")
    notes_dir = lock.get("notes_dir", "")
    reply_enabled = lock.get("reply", False)
    cmd_line = lock.get("cmd", "")

    running = _pid_is_running(pid)

    print("飞书 Bot 监听状态")
    print("─" * 40)
    if running:
        print(f"  状态:  [OK] 运行中")
    else:
        print(f"  状态:  [STALE] 锁文件存在但进程已退出（陈旧锁）")
    print(f"  PID:   {pid}")
    print(f"  启动:  {started_at}")
    print(f"  命令:  {cmd_line}")
    print(f"  回复:  {'开启' if reply_enabled else '关闭'}")
    if notes_dir:
        print(f"  笔记:  {notes_dir}")
    print(f"  锁文件: {LOCK_PATH}")

    # 检查子进程
    children = _get_child_processes(pid) if running else []
    lark_children = [c for c in children if "lark-cli" in c.get("cmd", "").lower() or "event" in c.get("cmd", "").lower()]
    if lark_children:
        print(f"  lark-cli 子进程: {len(lark_children)} 个")
        for c in lark_children[:5]:
            _safe_print(f"    - PID {c['pid']}: {c['cmd'][:80]}")

    # 检查重复 listener
    if running:
        duplicates = _find_duplicate_listeners(pid)
        if duplicates:
            print(f"\n  [!] 发现 {len(duplicates)} 个重复 listener 进程:")
            for dp in duplicates:
                _safe_print(f"    - PID {dp['pid']}: {dp['cmd'][:80]}")


def _find_duplicate_listeners(current_pid):
    """查找其他 feishu_bot.py listen 进程"""
    dups = []
    try:
        result = subprocess.run(
            ["wmic", "process", "where", "name='python.exe'",
             "get", "ProcessId,CommandLine", "/format:csv"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=10,
        )
        for line in result.stdout.strip().split("\n")[2:]:
            line = line.strip().lower()
            if not line or "feishu_bot" not in line or "listen" not in line:
                continue
            parts = line.rsplit(",", 2)
            if len(parts) >= 2:
                other_pid = parts[-1].strip()
                if other_pid.isdigit() and int(other_pid) != current_pid:
                    dups.append({"pid": other_pid, "cmd": parts[-2].strip() if len(parts) >= 3 else ""})
    except Exception:
        pass
    return dups


def _bot_start(args):
    """后台启动飞书 Bot 监听"""
    lock = _read_lock()
    if lock:
        old_pid = int(lock.get("pid", 0))
        if _pid_is_running(old_pid):
            print(f"飞书 Bot 已在运行 (PID={old_pid})")
            print("如需重启: python cli.py bot restart --reply")
            return
        else:
            print(f"清理陈旧锁文件 (PID={old_pid} 已退出)")
            try:
                LOCK_PATH.unlink()
            except OSError:
                pass

    feishu_bot = BASE_DIR / "adapters" / "feishu_bot.py"
    if not feishu_bot.exists():
        print(f"错误: 找不到 {feishu_bot}")
        return

    reply_flag = getattr(args, "reply", False)
    notes_dir = getattr(args, "notes_dir", "")

    # 构建启动命令
    cmd_parts = [sys.executable, str(feishu_bot), "listen"]
    if reply_flag:
        cmd_parts.append("--reply")
    if notes_dir:
        cmd_parts.append("--notes-dir")
        cmd_parts.append(notes_dir)

    # 确保日志目录存在
    BOT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    # 后台启动
    CREATE_NEW_PROCESS_GROUP = 0x00000200
    DETACHED_PROCESS = 0x00000008
    try:
        proc = subprocess.Popen(
            cmd_parts,
            stdout=open(str(BOT_LOG_PATH), "a", encoding="utf-8"),
            stderr=subprocess.STDOUT,
            creationflags=CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS,
            cwd=str(BASE_DIR),
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
    except Exception as e:
        print(f"启动失败: {e}")
        return

    print(f"飞书 Bot 已后台启动")
    print(f"  PID:    {proc.pid}")
    print(f"  回复:   {'开启' if reply_flag else '关闭'}")
    if notes_dir:
        print(f"  笔记:   {notes_dir}")
    print(f"  日志:   {BOT_LOG_PATH}")
    print(f"\n查看状态: python cli.py bot status")
    print(f"停止监听: python cli.py bot stop")


def _bot_stop(args):
    """停止飞书 Bot 监听"""
    force = getattr(args, "force", False)
    lock = _read_lock()

    if lock is None:
        if LOCK_PATH.exists():
            print("锁文件存在但无法解析，使用 --force 清理")
            if force:
                try:
                    LOCK_PATH.unlink()
                    print("已清理锁文件")
                except OSError as e:
                    print(f"清理失败: {e}")
            return
        print("飞书 Bot 未在运行（无锁文件）")
        return

    pid = int(lock.get("pid", 0))
    running = _pid_is_running(pid)

    if not running:
        print(f"PID {pid} 已退出（陈旧锁文件）")
        if force:
            try:
                LOCK_PATH.unlink()
                print("已清理锁文件")
            except OSError as e:
                print(f"清理失败: {e}")
        else:
            print("使用 --force 清理锁文件")
        return

    # 先杀子进程 (lark-cli)
    children = _get_child_processes(pid)
    for child in children:
        child_pid = int(child["pid"])
        try:
            subprocess.run(["taskkill", "/PID", str(child_pid), "/F"],
                           capture_output=True, timeout=5)
            print(f"已停止子进程 PID={child_pid} ({child['cmd'][:60]})")
        except Exception as e:
            print(f"停止子进程 {child_pid} 失败: {e}")

    # 杀主进程
    try:
        subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                       capture_output=True, timeout=5)
        print(f"已停止 listener 进程 PID={pid}")
    except Exception as e:
        print(f"停止主进程 {pid} 失败: {e}")

    # 清理锁文件
    try:
        if LOCK_PATH.exists():
            LOCK_PATH.unlink()
            print("已清理锁文件")
    except OSError as e:
        print(f"清理锁文件失败: {e}")

    print("\n飞书 Bot 已停止")


def _bot_restart(args):
    """重启飞书 Bot"""
    print("--- 停止 ---")
    _bot_stop(args)

    import time
    time.sleep(1)

    print("\n--- 启动 ---")
    _bot_start(args)


def main():
    parser = argparse.ArgumentParser(description="DeepRead CLI")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("progress", help="读书进度")
    sub.add_parser("review", help="随机复习一篇笔记")
    sub.add_parser("think", help="生成慢思考问题")
    sub.add_parser("status", help="当前阅读状态")
    p_doc = sub.add_parser("doctor", help="健康检查：依赖/路径/配置/EPUB连通性")
    p_doc.add_argument("--deep", action="store_true", help="深度检查：LLM连通性、飞书CLI、笔记质量抽样")
    p_contract = sub.add_parser("contract", help="学习契约工具（转发到 scripts/learning_contract.py）")
    p_contract.add_argument("contract_args", nargs=argparse.REMAINDER)
    p_chat = sub.add_parser("chat", help="启动独立 Agent 对话（需要 DEEPSEEK_API_KEY 或 ANTHROPIC_API_KEY）")
    p_chat.add_argument("--resume", help="恢复会话 ID")
    p_chat.add_argument("--model", default="", help="模型 ID")
    p_chat.add_argument("--provider", default="", help="deepseek / anthropic / openai")

    p_bot = sub.add_parser("bot", help="飞书 Bot 进程管理")
    p_bot_sub = p_bot.add_subparsers(dest="bot_cmd")
    p_bot_status = p_bot_sub.add_parser("status", help="查看监听状态")
    p_bot_start = p_bot_sub.add_parser("start", help="后台启动监听")
    p_bot_start.add_argument("--reply", action="store_true", help="开启回复模式")
    p_bot_start.add_argument("--notes-dir", default="", help="笔记输出目录")
    p_bot_stop = p_bot_sub.add_parser("stop", help="停止监听")
    p_bot_stop.add_argument("--force", action="store_true", help="强制清理陈旧锁文件")
    p_bot_restart = p_bot_sub.add_parser("restart", help="重启监听")
    p_bot_restart.add_argument("--reply", action="store_true", help="开启回复模式")
    p_bot_restart.add_argument("--notes-dir", default="", help="笔记输出目录")
    p_bot_restart.add_argument("--force", action="store_true", help="停止时强制清理")

    p_quality = sub.add_parser("quality", help="笔记质量检查")
    p_quality.add_argument("note_path", help="笔记文件路径")
    p_quality.add_argument("--json", action="store_true", help="JSON 输出")

    p_concepts = sub.add_parser("concepts", help="概念卡管理")
    p_concepts_sub = p_concepts.add_subparsers(dest="concepts_cmd")
    p_concepts_sub.add_parser("scan", help="盘点已有概念卡")
    p_concepts_sub.add_parser("aliases", help="检查概念卡别名覆盖")
    p_concepts_sub.add_parser("missing", help="发现缺失的概念候选")
    p_concepts_sub.add_parser("report", help="概念卡覆盖率报告")

    sub.add_parser("profile", help="显示当前 profile")

    p_modes = sub.add_parser("modes", help="阅读模式管理")
    p_modes_sub = p_modes.add_subparsers(dest="modes_cmd")
    p_modes_sub.add_parser("list", help="列出可用阅读模式")
    p_suggest = p_modes_sub.add_parser("suggest", help="根据书名建议模式")
    p_suggest.add_argument("book_hint", help="书名或描述")
    p_show = p_modes_sub.add_parser("show", help="展示某模式详情")
    p_show.add_argument("mode_key", help="模式键名")

    p_search = sub.add_parser("search", help="搜索 vault")
    p_search.add_argument("keyword", help="搜索关键词")

    p_read = sub.add_parser("read", help="提取章节（为 Claude Code 准备）")
    p_read.add_argument("book", help="书名或 EPUB 文件名")
    p_read.add_argument("chapter", help="章节号")

    args = parser.parse_args()

    if args.command == "progress":
        cmd_progress()
    elif args.command == "review":
        cmd_review()
    elif args.command == "think":
        cmd_think()
    elif args.command == "search":
        cmd_search(args.keyword)
    elif args.command == "read":
        cmd_read(args.book, args.chapter)
    elif args.command == "status":
        cmd_status()
    elif args.command == "doctor":
        cmd_doctor(args)
    elif args.command == "contract":
        cmd_contract(args)
    elif args.command == "chat":
        cmd_chat(args)
    elif args.command == "bot":
        cmd_bot(args)
    elif args.command == "quality":
        cmd_quality(args)
    elif args.command == "concepts":
        cmd_concepts(args)
    elif args.command == "profile":
        cmd_profile(args)
    elif args.command == "modes":
        cmd_modes(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
