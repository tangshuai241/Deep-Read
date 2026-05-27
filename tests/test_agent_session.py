"""测试 agent.py 会话管理（不调用 API）"""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from agent import (LLMProvider, save_session, load_session, find_session_for_user,
                    list_sessions, SESSION_DIR, split_thinking_directive,
                    should_enable_auto_thinking, execute_tool)


def setup_module():
    os.environ["PYTHONIOENCODING"] = "utf-8"


def test_save_and_load_session(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        # 临时覆盖 SESSION_DIR
        import agent
        old_dir = agent.SESSION_DIR
        agent.SESSION_DIR = Path(tmp)

        try:
            sid = "test_001"
            messages = [
                {"role": "user", "content": "读第1章"},
                {"role": "assistant", "content": "好的"}
            ]
            meta = {"book": "测试", "chapter": "1", "user_id": "user_a",
                    "provider": "deepseek", "model": "deepseek-chat"}

            save_session(sid, messages, meta)

            loaded = load_session(sid)
            assert loaded is not None
            assert loaded["session_id"] == "test_001"
            assert loaded["book"] == "测试"
            assert loaded["user_id"] == "user_a"
            assert len(loaded["messages"]) == 2
        finally:
            agent.SESSION_DIR = old_dir


def test_find_session_for_user(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        import agent
        old_dir = agent.SESSION_DIR
        agent.SESSION_DIR = Path(tmp)

        try:
            # 创建两个用户各一个会话
            save_session("s1", [], {"user_id": "user_a", "book": "书A"})
            import time
            time.sleep(0.1)
            save_session("s2", [], {"user_id": "user_b", "book": "书B"})

            # user_a 应该找到 s1
            found = find_session_for_user("user_a")
            assert found == "s1"

            found = find_session_for_user("user_b")
            assert found == "s2"

            # 不存在的用户
            found = find_session_for_user("nobody")
            assert found is None
        finally:
            agent.SESSION_DIR = old_dir


def test_list_sessions(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        import agent
        old_dir = agent.SESSION_DIR
        agent.SESSION_DIR = Path(tmp)

        try:
            save_session("a", [], {"user_id": "u1"})
            save_session("b", [], {"user_id": "u2"})

            sessions = list_sessions()
            assert len(sessions) >= 2
        finally:
            agent.SESSION_DIR = old_dir


def test_session_contains_required_fields(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        import agent
        old_dir = agent.SESSION_DIR
        agent.SESSION_DIR = Path(tmp)

        try:
            save_session("fields_test", [], {"user_id": "u"})
            loaded = load_session("fields_test")
            assert "session_id" in loaded
            assert "created_at" in loaded
            assert "updated_at" in loaded
            assert "provider" in loaded
            assert "model" in loaded
            assert "user_id" in loaded
            assert "messages" in loaded
        finally:
            agent.SESSION_DIR = old_dir


def test_deepseek_defaults_to_disable_thinking(monkeypatch):
    class DummyOpenAI:
        def __init__(self, **kwargs):
            pass

    import types
    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=DummyOpenAI))

    provider = LLMProvider(
        "deepseek",
        {"name": "DeepSeek", "base_url": "https://api.deepseek.com", "type": "openai"},
        "test-key",
        "deepseek-v4-pro",
        {"llm": {}}
    )

    assert provider.extra_body == {"thinking": {"type": "disabled"}}


def test_deepseek_supports_auto_thinking(monkeypatch):
    class DummyOpenAI:
        def __init__(self, **kwargs):
            pass

    import types
    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=DummyOpenAI))

    provider = LLMProvider(
        "deepseek",
        {"name": "DeepSeek", "base_url": "https://api.deepseek.com", "type": "openai"},
        "test-key",
        "deepseek-v4-pro",
        {"llm": {"thinking": "auto"}}
    )

    assert provider.thinking_mode == "auto"
    assert provider.extra_body == {}

    provider.set_thinking_for_request("enabled")
    assert provider.extra_body == {"thinking": {"type": "enabled"}}

    provider.set_thinking_for_request("disabled")
    assert provider.extra_body == {"thinking": {"type": "disabled"}}


def test_split_thinking_directive():
    text, override = split_thinking_directive("/深思 总结我的回答")
    assert text == "总结我的回答"
    assert override == "enabled"

    text, override = split_thinking_directive("/深思：总结我的回答")
    assert text == "总结我的回答"
    assert override == "enabled"

    text, override = split_thinking_directive("/普通 你好")
    assert text == "你好"
    assert override == "disabled"


def test_auto_thinking_router():
    assert should_enable_auto_thinking("你好") is False
    assert should_enable_auto_thinking("搜索 系统1") is False
    assert should_enable_auto_thinking("总结我的回答，并指出我的盲点") is True
    assert should_enable_auto_thinking("继续", stage="socratic") is True


def test_learning_contract_tool_passes_user_before_subcommand(monkeypatch):
    captured = {}

    def fake_run_script(name, *args):
        captured["name"] = name
        captured["args"] = args
        return "{}"

    import agent
    monkeypatch.setattr(agent, "run_script", fake_run_script)

    execute_tool("learning_contract", {"action": "show"}, user_id="ou_test")

    assert captured["name"] == "learning_contract.py"
    assert captured["args"][:4] == ("--user", "ou_test", "--json", "show")


def test_openai_replays_reasoning_content(monkeypatch):
    captured = {}

    class DummyMessage:
        content = "ok"
        tool_calls = None

    class DummyChoice:
        message = DummyMessage()

    class DummyResponse:
        choices = [DummyChoice()]

    class DummyCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return DummyResponse()

    class DummyChat:
        completions = DummyCompletions()

    class DummyOpenAI:
        def __init__(self, **kwargs):
            self.chat = DummyChat()

    import types
    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=DummyOpenAI))

    provider = LLMProvider(
        "openai",
        {"name": "OpenAI", "base_url": "", "type": "openai"},
        "test-key",
        "gpt-test",
        {"llm": {}}
    )

    messages = [
        {"role": "user", "content": "你好"},
        {
            "role": "assistant",
            "content": "你好，我想一下",
            "reasoning_content": "hidden chain"
        },
        {"role": "user", "content": "继续"}
    ]

    provider.chat("system", messages, [])
    replayed = captured["messages"][2]

    assert replayed["role"] == "assistant"
    assert replayed["reasoning_content"] == "hidden chain"


def test_call_api_returns_all_tool_results(monkeypatch):
    import agent

    class DummyLLM:
        name = "Dummy"
        model = "dummy-model"
        api_type = "openai"
        calls = 0

        def chat(self, system_prompt, messages, tools):
            self.calls += 1
            if self.calls == 1:
                return "", [{"id": "tc1", "name": "write_note", "input": {"action": "compile"}}], object()
            if self.calls == 2:
                return "", [{"id": "tc2", "name": "read_state", "input": {}}], object()
            return "完成", [], object()

        def extract_reasoning_content(self, raw):
            return ""

    monkeypatch.setattr(agent, "execute_tool", lambda name, inp, user_id: f"{name}-result")
    monkeypatch.setattr(agent, "log_api_call", lambda *args, **kwargs: None)
    monkeypatch.setattr(agent, "log_tool_call", lambda *args, **kwargs: None)
    monkeypatch.setattr(agent, "save_session", lambda *args, **kwargs: None)
    monkeypatch.setattr(agent.DeepReadAgent, "_save_recovery", lambda self: None)
    monkeypatch.setattr(agent.DeepReadAgent, "__init__", lambda self: None)

    bot = agent.DeepReadAgent()
    bot.llm = DummyLLM()
    bot.system_prompt = ""
    bot.messages = []
    bot.use_tools = []
    bot.user_id = "ou_test"
    bot.session_id = "sid"
    bot.meta = {"book": "book", "chapter": "chapter"}
    bot._last_user_input = "收尾"
    bot._thinking_override = None

    text, tools = bot._call_api_internal()

    assert text == "完成"
    assert [item[1] for item in tools] == ["write_note", "read_state"]
