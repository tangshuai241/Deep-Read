"""测试章节学习契约。"""
import json
import tempfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import learning_contract as lc


class Args:
    def __init__(self, **kwargs):
        self.user = kwargs.pop("user", "default")
        self.json = kwargs.pop("json", False)
        self.book = kwargs.pop("book", "")
        self.chapter = kwargs.pop("chapter", "")
        self.section = kwargs.pop("section", "")
        self.goal = kwargs.pop("goal", "理解")
        self.profile = kwargs.pop("profile", "personal")
        self.book_type = kwargs.pop("book_type", "")
        self.reading_mode = kwargs.pop("reading_mode", "concept_deep_read")
        self.mode_reason = kwargs.pop("mode_reason", "")
        self.A_core = kwargs.pop("A_core", "")
        self.B_important = kwargs.pop("B_important", "")
        self.C_evidence = kwargs.pop("C_evidence", "")
        self.D_application = kwargs.pop("D_application", "")
        self.point = kwargs.pop("point", "")
        self.group = kwargs.pop("group", "B_important")
        self.status = kwargs.pop("status", "")
        self.evidence = kwargs.pop("evidence", "")
        self.event = kwargs.pop("event", "")
        self.deposit = kwargs.pop("deposit", "")
        self.note = kwargs.pop("note", "")
        self.stage = kwargs.pop("stage", "")
        for key, value in kwargs.items():
            setattr(self, key, value)


def with_temp_state(monkeypatch):
    tmp = tempfile.TemporaryDirectory()
    monkeypatch.setattr(lc, "get_state_root", lambda: Path(tmp.name))
    return tmp


def test_init_contract_creates_abcd_map(monkeypatch):
    with with_temp_state(monkeypatch):
        result = lc.init_contract(Args(
            book="思考快与慢",
            chapter="8.我们究竟是如何作出判断的？",
            section="强度匹配",
            A_core="基本判断,强度匹配",
            B_important='["思维发散性"]',
            C_evidence="鸟类捐款实验",
            D_application="系统1何时是资产",
        ))

        contract = result["contract"]
        assert result["ok"] is True
        assert contract["scope"]["book"] == "思考快与慢"
        assert len(contract["knowledge_map"]["A_core"]) == 2
        assert contract["knowledge_map"]["B_important"][0]["title"] == "思维发散性"


def test_update_marks_point_and_keeps_evidence(monkeypatch):
    with with_temp_state(monkeypatch):
        lc.init_contract(Args(A_core="WYSIATI,确认偏误"))
        lc.update_contract(Args(
            point="WYSIATI",
            status="covered",
            evidence="用户能解释为只根据眼前证据形成确定感",
        ))

        contract = lc.load_contract()
        point = contract["knowledge_map"]["A_core"][0]
        assert point["status"] == "covered"
        assert "眼前证据" in point["evidence"][0]


def test_feynman_requires_80_percent_a_core(monkeypatch):
    with with_temp_state(monkeypatch):
        lc.init_contract(Args(A_core="A1,A2,A3,A4,A5"))
        for name in ["A1", "A2", "A3"]:
            lc.update_contract(Args(point=name, status="covered", evidence=f"{name} evidence"))

        result = lc.check_contract(Args(stage="feynman"))
        assert result["ok"] is False

        lc.update_contract(Args(point="A4", status="covered", evidence="A4 evidence"))
        result = lc.check_contract(Args(stage="feynman"))
        assert result["ok"] is True


def test_socratic_requires_deep_boundary_and_application(monkeypatch):
    with with_temp_state(monkeypatch):
        lc.init_contract(Args(A_core="A1,A2", B_important="B1"))
        lc.update_contract(Args(point="A1", status="passed", evidence="深挖 A1"))
        lc.update_contract(Args(point="B1", status="passed", evidence="深挖 B1"))

        result = lc.check_contract(Args(stage="socratic"))
        assert result["ok"] is False

        lc.update_contract(Args(event="boundary_or_counterexample", evidence="讨论失效边界"))
        lc.update_contract(Args(event="application_probe", evidence="讨论工程现场应用"))
        result = lc.check_contract(Args(stage="socratic"))
        assert result["ok"] is True


def test_associate_requires_old_note_personal_and_deposit(monkeypatch):
    with with_temp_state(monkeypatch):
        lc.init_contract(Args(A_core="A1"))
        lc.update_contract(Args(event="old_note_connection", evidence="关联 [[光环效应]]"))
        lc.update_contract(Args(event="personal_association", evidence="联想到工地判断"))

        result = lc.check_contract(Args(stage="associate"))
        assert result["ok"] is False

        lc.update_contract(Args(deposit="associations", evidence="已写入让我想到"))
        result = lc.check_contract(Args(stage="associate"))
        assert result["ok"] is True


def test_report_lists_missing_a_core_as_explore(monkeypatch):
    with with_temp_state(monkeypatch):
        lc.init_contract(Args(A_core="系统1,确认偏误"))
        lc.update_contract(Args(point="系统1", status="passed", evidence="用户解释清楚"))

        report = lc.report_contract(Args())
        assert report["ok"] is True
        assert report["missing_a_core"] == ["确认偏误"]
        assert "继续澄清：确认偏误" in report["suggested_explore"]


def test_init_contract_includes_reading_mode_fields(monkeypatch):
    with with_temp_state(monkeypatch):
        result = lc.init_contract(Args(
            book="测试书", chapter="1",
            reading_mode="exam_mastery",
            book_type="教材型",
            mode_reason="用户说这是一级建造师",
            profile="trial",
        ))
        assert result["ok"]
        contract = result["contract"]
        assert contract["profile"] == "trial"
        assert contract["scope"]["reading_mode"] == "exam_mastery"
        assert contract["scope"]["book_type"] == "教材型"
        assert contract["scope"]["mode_reason"] == "用户说这是一级建造师"


def test_show_contract_json_serializable(monkeypatch):
    with with_temp_state(monkeypatch):
        lc.init_contract(Args(book="JSON测试", chapter="3", reading_mode="method_conversion",
                              profile="personal", book_type="方法工具型"))
        contract = lc.load_contract()

        assert contract["scope"]["reading_mode"] == "method_conversion"
        assert contract["profile"] == "personal"
        assert contract["scope"]["book_type"] == "方法工具型"
        # 确保能序列化为 JSON
        json_str = json.dumps(contract, ensure_ascii=False)
        parsed = json.loads(json_str)
        assert parsed["scope"]["reading_mode"] == "method_conversion"


def test_default_contract_missing_reading_mode_defaults_to_concept_deep_read(monkeypatch):
    with with_temp_state(monkeypatch):
        # 模拟旧契约：缺 reading_mode 字段
        contract = lc.default_contract("旧书", "5", "", "理解")
        path = lc.save_contract(contract, user="test_legacy")
        loaded = lc.load_contract(user="test_legacy")
        assert loaded["scope"].get("reading_mode", "concept_deep_read") == "concept_deep_read"
        assert loaded["version"] == "1.1"
