"""测试 state.py 状态保存/恢复/归档"""
import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from state import read_state, write_state, default_state, get_current_path, get_history_dir, archive_state


def setup_module():
    os.environ["PYTHONIOENCODING"] = "utf-8"


def test_default_state():
    state = default_state()
    assert state["current"]["stage"] == "idle"
    assert state["current"]["book"] is None
    assert state["blindspots"] == []
    assert state["concepts_covered"] == []


def test_write_and_read():
    with tempfile.TemporaryDirectory() as tmp:
        state = default_state()
        state["current"]["book"] = "测试书"
        state["current"]["chapter"] = "3"
        state["current"]["stage"] = "feynman"
        state["concepts_covered"] = ["概念A", "概念B"]

        write_state(tmp, state)
        loaded = read_state(tmp)

        assert loaded["current"]["book"] == "测试书"
        assert loaded["current"]["chapter"] == "3"
        assert loaded["current"]["stage"] == "feynman"
        assert "概念A" in loaded["concepts_covered"]


def test_read_nonexistent_returns_default():
    state = read_state("/nonexistent/path/xyz")
    assert state["current"]["stage"] == "idle"


def test_archive_uses_timestamp():
    with tempfile.TemporaryDirectory() as tmp:
        state = default_state()
        state["current"]["stage"] = "socratic"
        archive_state(tmp, state)

        history_dir = get_history_dir(tmp)
        files = os.listdir(history_dir)
        assert len(files) == 1
        # 文件名应该是时间戳格式: YYYY-MM-DDTHHMMSS.json
        assert "T" in files[0]
        assert files[0].endswith(".json")
        # 不是纯日期格式（旧bug）
        assert files[0] != f"{datetime.now().strftime('%Y-%m-%d')}.json" or len(files[0]) > 15
