#!/usr/bin/env python3
"""
DeepRead Agent — 独立 LLM Agent 运行时（多后端）
替代 Claude Code 在 DeepRead 中的角色：对话循环 + 工具调度 + 会话管理

支持后端: Anthropic / DeepSeek / OpenAI 兼容

用法:
  python agent.py                          # 新对话
  python agent.py --resume <session_id>    # 恢复会话
  python agent.py --list-sessions          # 列出会话
  python agent.py --provider deepseek --model deepseek-chat

配置: config.yaml 中 llm 段，或环境变量
  ANTHROPIC_API_KEY / DEEPSEEK_API_KEY / OPENAI_API_KEY
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from scripts.logger import (log_session_start, log_session_end, log_tool_call,
                              log_api_call, log_error)

SCRIPTS_DIR = Path(__file__).parent / "scripts"
SKILL_DIR = None  # 延迟初始化
SESSION_DIR = Path(__file__).parent / "state" / "sessions"


# ═══════════════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════════════

def load_config():
    config_path = Path(__file__).parent / "config.yaml"
    if config_path.exists():
        try:
            import yaml
            with open(config_path, encoding='utf-8') as f:
                return yaml.safe_load(f)
        except ImportError:
            pass
    return {}


def resolve_skill_dir(config):
    """解析 Skill 目录：config → env → 项目自带 → Claude Code 默认"""
    global SKILL_DIR
    if SKILL_DIR:
        return SKILL_DIR

    # 1. config.yaml
    cfg_path = config.get("paths", {}).get("skill_dir", "")
    if cfg_path and Path(cfg_path).exists():
        SKILL_DIR = Path(cfg_path)
        return SKILL_DIR

    # 2. 环境变量
    env_path = os.environ.get("DEEPREAD_SKILL_DIR", "")
    if env_path and Path(env_path).exists():
        SKILL_DIR = Path(env_path)
        return SKILL_DIR

    # 3. 项目自带 skill/ 目录
    bundled = Path(__file__).parent / "skill"
    if bundled.exists():
        SKILL_DIR = bundled
        return SKILL_DIR

    # 4. Claude Code 默认路径（开发者回退）
    claude_skill = Path.home() / ".claude" / "skills" / "deep-read"
    if claude_skill.exists():
        SKILL_DIR = claude_skill
        return SKILL_DIR

    SKILL_DIR = bundled  # 返回默认值，即使不存在
    return SKILL_DIR


def load_system_prompt(config):
    skill_dir = resolve_skill_dir(config)
    skill = skill_dir / "SKILL.md"
    if not skill.exists():
        return "你是 DeepRead 深度阅读教练。运用费曼学习法和苏格拉底提问引导用户理解阅读内容。"

    with open(skill, encoding='utf-8') as f:
        prompt = f.read()

    for ref in ["dialogue-flow.md", "note-format.md", "fsm-spec.md"]:
        rp = skill_dir / "references" / ref
        if rp.exists():
            with open(rp, encoding='utf-8') as f:
                prompt += f"\n\n---\n## {ref}\n\n{f.read()}"

    prompt += "\n\n重要：你必须调用工具来操作数据。不知道 EPUB 内容→调 extract_epub。不要直接写笔记→调 write_note。不知道状态→调 read_state。搜索知识库→调 search_vault。"
    return prompt


# ═══════════════════════════════════════════════════════
# 脚本执行
# ═══════════════════════════════════════════════════════

def run_script(name, *args):
    script = SCRIPTS_DIR / name
    if not script.exists():
        return json.dumps({"ok": False, "error": f"脚本不存在: {name}"})
    cmd = [sys.executable, str(script)] + list(args)
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        result = subprocess.run(cmd, capture_output=True, text=True,
                                encoding='utf-8', errors='replace', env=env,
                                timeout=30)
    except subprocess.TimeoutExpired:
        return json.dumps({"ok": False, "error": "脚本执行超时"})

    out = result.stdout.strip()
    if result.returncode != 0:
        err = result.stderr.strip()
        if err.startswith("{"):
            return err
        return json.dumps({"ok": False, "error": err[:500]})
    return out if out else "{}"


def execute_tool(name, params):
    p = params or {}
    if name == "extract_epub":
        return run_script("extract_epub.py", "--book", str(p.get("book", "")),
                          "--chapter", str(p.get("chapter", "")), "--json")
    elif name == "write_note":
        action = p.get("action", "create")
        args = []
        for key, flag in [("book", "--book"), ("concept", "--concept"),
                          ("chapter", "--chapter"), ("author", "--author"),
                          ("category", "--category"), ("tags", "--tags"),
                          ("quote", "--quote"), ("understanding", "--understanding"),
                          ("path", "--path"), ("section", "--section"),
                          ("content", "--content"), ("explore", "--explore")]:
            if key in p and p[key]:
                args.extend([flag, str(p[key])])
        return run_script("write_note.py", action, *args)
    elif name == "read_state":
        return run_script("state.py", "show")
    elif name == "update_state":
        args = []
        for key, flag in [("stage", "--stage"), ("book", "--book"),
                          ("chapter", "--chapter"), ("section", "--section"),
                          ("goal", "--goal"), ("summary", "--summary")]:
            if key in p and p[key]:
                args.extend([flag, str(p[key])])
        for key, flag in [("blindspot", "--add-blindspot"),
                          ("concept", "--add-concept"),
                          ("profile", "--add-profile")]:
            if key in p and p[key]:
                args.extend([flag, str(p[key])])
        return run_script("state.py", "set", *args) if args else json.dumps({"ok": True})
    elif name == "search_vault":
        return run_script("search_vault.py", "--keyword", str(p.get("keyword", "")),
                          "--json", "--limit", str(p.get("limit", 10)))
    return json.dumps({"ok": False, "error": f"未知工具: {name}"})


# ═══════════════════════════════════════════════════════
# 工具定义（两种格式）
# ═══════════════════════════════════════════════════════

TOOLS_ANTHROPIC = [
    {
        "name": "extract_epub",
        "description": "从 EPUB 提取指定章节文本。必须先调用此工具获取原文，不能假装读过。章节号用数字。",
        "input_schema": {
            "type": "object",
            "properties": {
                "book": {"type": "string", "description": "EPUB 文件名，如 思考快与慢.epub"},
                "chapter": {"type": "string", "description": "章节号，如 5"}
            },
            "required": ["book", "chapter"]
        }
    },
    {
        "name": "write_note",
        "description": "写入/更新 Obsidian 笔记。渐进式：create(阶段1)→update(阶段2)→append(阶段3)→finalize(阶段4)。",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["create", "update", "append", "finalize"]},
                "book": {"type": "string"}, "concept": {"type": "string"},
                "chapter": {"type": "string"}, "author": {"type": "string"},
                "category": {"type": "string"}, "tags": {"type": "string"},
                "quote": {"type": "string"}, "understanding": {"type": "string"},
                "path": {"type": "string", "description": "笔记路径（update/append/finalize必填）"},
                "section": {"type": "string", "description": "引用原文/我的理解/让我想到/待探索"},
                "content": {"type": "string"}, "explore": {"type": "string"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "read_state", "description": "读取当前阅读状态：书、章节、阶段、概念、盲点。每次对话开始和阶段切换前必须调用。",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "update_state",
        "description": "更新阅读状态。阶段切换时必须调用。",
        "input_schema": {
            "type": "object",
            "properties": {
                "stage": {"type": "string", "enum": ["idle", "init", "feynman", "socratic", "associate", "wrapup"]},
                "book": {"type": "string"}, "chapter": {"type": "string"},
                "section": {"type": "string"}, "goal": {"type": "string"},
                "summary": {"type": "string"}, "blindspot": {"type": "string"},
                "concept": {"type": "string"}, "profile": {"type": "string"}
            },
            "required": []
        }
    },
    {
        "name": "search_vault",
        "description": "搜索 Obsidian 知识库找关联旧笔记。阶段3（联想）时使用。",
        "input_schema": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "搜索关键词"},
                "limit": {"type": "integer", "description": "返回数量，默认10"}
            },
            "required": ["keyword"]
        }
    }
]


def to_openai_tools():
    """转换为 OpenAI/DeepSeek function calling 格式"""
    result = []
    for t in TOOLS_ANTHROPIC:
        result.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": {
                    "type": "object",
                    "properties": t["input_schema"]["properties"],
                    "required": t["input_schema"].get("required", [])
                }
            }
        })
    return result


# ═══════════════════════════════════════════════════════
# LLM Provider 抽象
# ═══════════════════════════════════════════════════════

PROVIDER_CONFIGS = {
    "deepseek": {
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com",
        "key_env": "DEEPSEEK_API_KEY",
        "default_model": "deepseek-chat",
        "type": "openai",
    },
    "anthropic": {
        "name": "Anthropic",
        "base_url": None,
        "key_env": "ANTHROPIC_API_KEY",
        "default_model": "claude-sonnet-4-6",
        "type": "anthropic",
    },
    "openai": {
        "name": "OpenAI",
        "base_url": "https://api.openai.com",
        "key_env": "OPENAI_API_KEY",
        "default_model": "gpt-4o",
        "type": "openai",
    },
}


def detect_provider(config, cli_provider):
    """检测使用哪个后端"""
    # 1. CLI 参数优先
    if cli_provider and cli_provider in PROVIDER_CONFIGS:
        return cli_provider, PROVIDER_CONFIGS[cli_provider]

    # 2. config.yaml 指定
    cfg_provider = config.get("llm", {}).get("provider", "")
    if cfg_provider and cfg_provider in PROVIDER_CONFIGS:
        return cfg_provider, PROVIDER_CONFIGS[cfg_provider]

    # 3. 根据环境变量自动检测
    for pid, pcfg in PROVIDER_CONFIGS.items():
        if os.environ.get(pcfg["key_env"]):
            return pid, pcfg

    # 4. 默认 DeepSeek
    return "deepseek", PROVIDER_CONFIGS["deepseek"]


def get_api_key(pcfg, config):
    """获取 API Key：环境变量 > config.yaml"""
    key = os.environ.get(pcfg["key_env"], "")
    if key:
        return key
    return config.get("llm", {}).get("api_key", "")


def get_model(pcfg, config, cli_model):
    """获取模型名：CLI > config > provider 默认"""
    if cli_model:
        return cli_model
    cfg_model = config.get("llm", {}).get("model", "")
    return cfg_model if cfg_model else pcfg["default_model"]


class LLMProvider:
    """统一 LLM 调用接口"""

    def __init__(self, provider_id, pcfg, api_key, model, config=None):
        self.provider_id = provider_id
        self.name = pcfg["name"]
        self.api_type = pcfg["type"]
        self.model = model
        self.client = None

        # 自定义 base_url（config 优先于 provider 默认）
        base_url = pcfg.get("base_url", "")
        if config:
            custom_url = config.get("llm", {}).get("base_url", "")
            if custom_url:
                base_url = custom_url

        if self.api_type == "anthropic":
            import anthropic
            self.client = anthropic.Anthropic(api_key=api_key)
        else:
            import openai
            kwargs = {"api_key": api_key}
            if base_url:
                kwargs["base_url"] = base_url
            self.client = openai.OpenAI(**kwargs)

    def chat(self, system_prompt, messages, tools):
        """发送消息，返回 (text, tool_calls, raw_response)"""
        if self.api_type == "anthropic":
            return self._chat_anthropic(system_prompt, messages, tools)
        else:
            return self._chat_openai(system_prompt, messages, tools)

    def _chat_anthropic(self, system_prompt, messages, tools):
        clean = []
        for m in messages:
            role = m["role"]
            if role in ("user", "assistant"):
                content = m["content"]
                # 已经是结构化 content（数组）就保留
                if isinstance(content, list):
                    clean.append({"role": role, "content": content})
                else:
                    clean.append({"role": role, "content": content})
            elif role == "tool":
                clean.append({
                    "role": "user",
                    "content": [{"type": "tool_result",
                                 "tool_use_id": m["tool_use_id"],
                                 "content": m["content"]}]
                })

        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system_prompt,
            tools=tools,
            messages=clean
        )

        text = ""
        tool_calls = []
        for block in response.content:
            if block.type == "text":
                text += block.text
            elif block.type == "tool_use":
                tool_calls.append({
                    "id": block.id,
                    "name": block.name,
                    "input": dict(block.input) if block.input else {}
                })

        return text, tool_calls, response

    def _chat_openai(self, system_prompt, messages, tools):
        # 构建 OpenAI 格式消息
        openai_messages = [{"role": "system", "content": system_prompt}]
        for m in messages:
            role = m["role"]
            if role == "tool":
                openai_messages.append({
                    "role": "tool",
                    "tool_call_id": m.get("tool_use_id", ""),
                    "content": m["content"]
                })
            elif role == "assistant" and isinstance(m.get("content"), list):
                # 有 tool_calls 的 assistant 消息
                tc_list = []
                text_content = ""
                for block in m["content"]:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        tc_list.append({
                            "id": block["id"],
                            "type": "function",
                            "function": {"name": block["name"], "arguments": json.dumps(block.get("input", {}), ensure_ascii=False)}
                        })
                    elif isinstance(block, dict) and block.get("type") == "text":
                        text_content += block.get("text", "")
                    elif isinstance(block, str):
                        text_content += block
                msg = {"role": "assistant", "content": text_content or None}
                if tc_list:
                    msg["tool_calls"] = tc_list
                openai_messages.append(msg)
            else:
                content = m.get("content", "")
                if isinstance(content, list):
                    # 提取 text
                    texts = [b.get("text", "") if isinstance(b, dict) else str(b) for b in content]
                    content = "".join(texts)
                openai_messages.append({"role": role, "content": content})

        response = self.client.chat.completions.create(
            model=self.model,
            messages=openai_messages,
            tools=tools,
            max_tokens=4096
        )

        choice = response.choices[0]
        msg = choice.message
        text = msg.content or ""

        tool_calls = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                try:
                    inp = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    inp = {}
                tool_calls.append({
                    "id": tc.id,
                    "name": tc.function.name,
                    "input": inp
                })

        return text, tool_calls, response


# ═══════════════════════════════════════════════════════
# 会话
# ═══════════════════════════════════════════════════════

def load_session(session_id):
    path = SESSION_DIR / f"{session_id}.json"
    if path.exists():
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    return None


def save_session(session_id, messages, meta):
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "session_id": session_id,
        "created_at": meta.get("created_at", datetime.now().isoformat()),
        "updated_at": datetime.now().isoformat(),
        "provider": meta.get("provider", ""),
        "model": meta.get("model", ""),
        "book": meta.get("book", ""),
        "chapter": meta.get("chapter", ""),
        "user_id": meta.get("user_id", "default"),
        "messages": messages
    }
    with open(SESSION_DIR / f"{session_id}.json", 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def find_session_for_user(user_id):
    """查找用户最近的会话"""
    if not SESSION_DIR.exists():
        return None
    best = None
    best_time = ""
    for f in SESSION_DIR.glob("*.json"):
        try:
            with open(f, encoding='utf-8') as fh:
                d = json.load(fh)
            if d.get("user_id", "default") == user_id:
                updated = d.get("updated_at", "")
                if updated > best_time:
                    best_time = updated
                    best = d.get("session_id")
        except Exception:
            pass
    return best


def list_sessions():
    if not SESSION_DIR.exists():
        return []
    sessions = []
    for f in sorted(SESSION_DIR.glob("*.json"), key=os.path.getmtime, reverse=True):
        try:
            with open(f, encoding='utf-8') as fh:
                d = json.load(fh)
            sessions.append((
                d.get("session_id", f.stem),
                d.get("book", "?"),
                d.get("provider", ""),
                d.get("model", ""),
                d.get("updated_at", "")[:16],
                len(d.get("messages", []))
            ))
        except Exception:
            pass
    return sessions


# ═══════════════════════════════════════════════════════
# Agent 主循环
# ═══════════════════════════════════════════════════════

class DeepReadAgent:
    def __init__(self, session_id=None, provider=None, model=None, user_id="default"):
        self.config = load_config()
        pid, pcfg = detect_provider(self.config, provider)
        model = get_model(pcfg, self.config, model)
        api_key = get_api_key(pcfg, self.config)

        if not api_key:
            print(f"错误: 未设置 {pcfg['key_env']}")
            sys.exit(1)

        self.llm = LLMProvider(pid, pcfg, api_key, model, self.config)
        print(f"后端: {self.llm.name} | 模型: {model}")

        self.system_prompt = load_system_prompt(self.config)
        self.tools_anthropic = TOOLS_ANTHROPIC
        self.tools_openai = to_openai_tools()
        self.use_tools = self.tools_anthropic if self.llm.api_type == "anthropic" else self.tools_openai

        self.user_id = user_id
        self.session_id = session_id or datetime.now().strftime("%Y%m%dT%H%M%S")
        self.messages = []
        self.meta = {"book": "", "chapter": "", "provider": pid, "model": model, "user_id": user_id}
        self._last_user_input = ""

        if not session_id:
            log_session_start(self.session_id, pid, model, user_id)

        if session_id:
            saved = load_session(session_id)
            if saved:
                self.messages = saved.get("messages", [])
                self.meta["book"] = saved.get("book", "")
                self.meta["chapter"] = saved.get("chapter", "")
                self.meta["created_at"] = saved.get("created_at", "")
                print(f"恢复 {session_id}: 《{self.meta['book']}》({len(self.messages)} 轮)")

    def _update_meta(self, text, tool_calls, tool_results):
        """从工具调用结果回填 book/chapter meta"""
        if self.meta.get("book") and self.meta.get("chapter"):
            return  # 已有，不覆盖

        for tid, tname, tresult in tool_results:
            if tname == "read_state":
                try:
                    # 解析人类可读输出
                    for line in tresult.split('\n'):
                        line = line.strip()
                        if line.startswith("书名:") and not self.meta.get("book"):
                            book = line.split(":", 1)[1].strip()
                            if book and book != "(未开始)" and book != "-":
                                self.meta["book"] = book
                        if line.startswith("章节:") and not self.meta.get("chapter"):
                            ch = line.split(":", 1)[1].strip()
                            if ch and ch != "-":
                                self.meta["chapter"] = ch
                except Exception:
                    pass
            elif tname == "extract_epub":
                try:
                    data = json.loads(tresult)
                    bk = data.get("book", {})
                    ch = data.get("chapter", {})
                    if bk.get("title") and not self.meta.get("book"):
                        # 清理书名中的副标题
                        title = bk["title"].split("(")[0].split("（")[0]
                        self.meta["book"] = title
                    if ch.get("index") is not None and not self.meta.get("chapter"):
                        self.meta["chapter"] = str(ch["index"])
                except (json.JSONDecodeError, KeyError):
                    pass

    def _save_recovery(self):
        """保存最后用户输入，用于崩溃恢复"""
        try:
            recovery = SESSION_DIR / f"{self.session_id}.recovery"
            with open(recovery, 'w', encoding='utf-8') as f:
                f.write(self._last_user_input)
        except Exception:
            pass

    def process_message(self, user_input, silent=True):
        """可编程接口：处理一条消息，返回 (response_text, tool_calls_info)
        供飞书/微信/Web 等外部入口调用。
        """
        self._last_user_input = user_input
        self.messages.append({"role": "user", "content": user_input})
        return self._call_api_internal(silent=silent)

    def _call_api_internal(self, silent=True):
        """内部 API 调用，返回 (text, tool_summary)"""
        last_tool_results = []

        while True:
            # 保存最后一条用户输入用于失败恢复
            if self._last_user_input:
                self._save_recovery()

            t0 = time.time()
            attempt = 0
            max_retries = 2
            raw = None
            text = ""
            tool_calls = []

            while attempt < max_retries:
                try:
                    text, tool_calls, raw = self.llm.chat(
                        self.system_prompt, self.messages,
                        self.use_tools
                    )
                    break
                except Exception as e:
                    attempt += 1
                    if attempt >= max_retries:
                        elapsed = int((time.time() - t0) * 1000)
                        log_api_call(self.session_id, self.llm.model,
                                     len(self.messages), elapsed, error=e)
                        log_error(self.session_id, "api", e)
                        error_msg = f"API 错误（重试{max_retries}次后）: {e}"
                        if not silent:
                            print(f"\n{error_msg}")
                        return error_msg, []
                    time.sleep(1)

            elapsed = int((time.time() - t0) * 1000)
            log_api_call(self.session_id, self.llm.model, len(self.messages), elapsed)

            if not silent and text:
                print(f"\n{text}\n")

            if tool_calls:
                last_tool_results = []
                tool_summary = []
                for tc in tool_calls:
                    tname = tc["name"]
                    tinp = tc["input"]
                    t0 = time.time()
                    result = execute_tool(tname, tinp)
                    elapsed = int((time.time() - t0) * 1000)
                    log_tool_call(self.session_id, tname, tinp, result, elapsed)
                    last_tool_results.append((tc["id"], tname, result))
                    tool_summary.append(f"{tname}: {result[:100]}")

                if self.llm.api_type == "anthropic":
                    assistant_content = []
                    for block in raw.content:
                        if block.type == "text":
                            assistant_content.append({"type": "text", "text": block.text})
                        elif block.type == "tool_use":
                            assistant_content.append({
                                "type": "tool_use", "id": block.id,
                                "name": block.name, "input": block.input
                            })
                    self.messages.append({"role": "assistant", "content": assistant_content})
                    for tid, tname, tresult in last_tool_results:
                        self.messages.append({
                            "role": "tool", "tool_use_id": tid,
                            "name": tname, "content": tresult
                        })
                else:
                    self.messages.append({
                        "role": "assistant",
                        "content": [{"type": "text", "text": text}] + [
                            {"type": "tool_use", "id": tc["id"],
                             "name": tc["name"], "input": tc["input"]}
                            for tc in tool_calls
                        ]
                    })
                    for tid, tname, tresult in last_tool_results:
                        self.messages.append({
                            "role": "tool", "tool_use_id": tid,
                            "name": tname, "content": tresult
                        })
                continue  # 继续工具调用循环
            else:
                self.messages.append({"role": "assistant", "content": text})
                self._update_meta(text, [], last_tool_results)
                try:
                    save_session(self.session_id, self.messages, self.meta)
                except Exception:
                    pass
                return text, last_tool_results

    def run(self):
        print(f"会话: {self.session_id}")
        print("输入 /help 查看命令, /exit 退出")
        print()

        while True:
            try:
                ui = input("DeepRead > ").strip()
            except (EOFError, KeyboardInterrupt):
                log_session_end(self.session_id, "interrupt")
                print(f"\n会话已保存: {self.session_id}")
                break

            if not ui:
                continue
            if ui == "/exit":
                log_session_end(self.session_id, "exit")
                print(f"会话已保存: {self.session_id}")
                break

            self._last_user_input = ui
            if ui == "/help":
                print("命令: /exit 退出 | /state 查看状态 | /tools 列出工具 | /session 会话信息")
                print("精读: 读《书名》第N章 | 继续: 进入下一阶段")
                continue
            if ui == "/state":
                print(execute_tool("read_state", {}))
                continue
            if ui == "/tools":
                for t in TOOLS_ANTHROPIC:
                    print(f"  {t['name']}: {t['description'][:80]}")
                continue
            if ui == "/session":
                print(f"ID: {self.session_id} | {self.llm.name}/{self.llm.model}")
                print(f"书: {self.meta.get('book', '-')} | 消息: {len(self.messages)}")
                continue

            self.messages.append({"role": "user", "content": ui})
            self._call_api()

    def _call_api(self):
        """CLI 模式（带工具调用打印）"""
        self._call_api_internal(silent=False)


# ═══════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="DeepRead Agent")
    parser.add_argument("--resume", help="恢复会话 ID")
    parser.add_argument("--list-sessions", action="store_true")
    parser.add_argument("--provider", help="deepseek / anthropic / openai")
    parser.add_argument("--model", help="模型 ID")
    args = parser.parse_args()

    if args.list_sessions:
        sessions = list_sessions()
        if not sessions:
            print("没有保存的会话")
            return
        print(f"{'会话ID':<18} {'书籍':<16} {'后端':<12} {'更新时间':<18} {'消息'}")
        print("-" * 80)
        for sid, book, prov, model, updated, count in sessions[:20]:
            print(f"{sid:<18} {book:<16} {prov}/{model:<12} {updated:<18} {count}")
        return

    agent = DeepReadAgent(
        session_id=args.resume,
        provider=args.provider,
        model=args.model
    )
    agent.run()


if __name__ == "__main__":
    main()
