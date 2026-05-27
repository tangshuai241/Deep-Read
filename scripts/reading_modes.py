#!/usr/bin/env python3
"""
DeepRead 阅读模式定义 — Agent、CLI、学习契约、笔记系统共用。

用法:
  from reading_modes import list_modes, suggest_mode, get_mode, allowed_modes
"""

READING_MODES = {
    "concept_deep_read": {
        "name": "概念精读",
        "desc": "四阶段费曼+苏格拉底+联想，适合概念密集型书籍",
        "target": "理解核心概念及其认知机制",
        "sections": ["引用原文", "我的理解", "让我想到", "待探索"],
        "trial": True,
        "suggest_patterns": ["思考快与慢", "认知", "心理学", "行为经济学",
                            "思维", "判断", "决策", "思考"],
        "stage_notes": "A 类核心概念必须覆盖，阶段 1 费曼→阶段 2 苏格拉底→阶段 3 联想→阶段 4 收尾",
        "notable_checks": {"A_core": "A 类核心概念至少覆盖 80%"},
    },
    "proposition_dialogue": {
        "name": "命题辨析",
        "desc": "逐命题挑战和重构，适合观点型、哲学类书籍",
        "target": "辨析命题的前提、边界和隐含假设",
        "sections": ["核心命题", "作者论证", "我的立场/反例", "待探索"],
        "trial": True,
        "suggest_patterns": ["被讨厌的勇气", "哲学", "人生", "意义",
                            "存在", "自由", "幸福", "勇气"],
        "stage_notes": "重点追问：作者主张是什么、前提是什么、你同不同意、边界在哪。不强制概念卡。",
        "notable_checks": {"personal_stance": "必须有个人立场或反例"},
    },
    "method_conversion": {
        "name": "方法转化",
        "desc": "提取方法→验证→改造→归档，适合工具书/方法论",
        "target": "将书中方法转化为个人可执行的步骤",
        "sections": ["方法提取", "前提条件", "我的场景", "改造方案", "行动清单"],
        "trial": True,
        "suggest_patterns": ["方法", "工具", "技巧", "指南", "手册",
                            "How To", "搞定", "GTD", "效率"],
        "stage_notes": "阶段 3 必须产生至少 1 个行动实验。笔记重点为 SOP/适用条件/行动清单。",
        "notable_checks": {"action_experiment": "必须有至少 1 个行动实验"},
    },
    "exam_mastery": {
        "name": "考试掌握",
        "desc": "高频考点→理解→记忆→自测，适合教材/资格证考试",
        "target": "掌握考点并能通过自测验证",
        "sections": ["考点梳理", "核心理解", "易错对比", "自测题", "待复习"],
        "trial": True,
        "suggest_patterns": ["一级建造师", "考试", "教材", "资格证",
                            "备考", "真题", "考点", "习题"],
        "stage_notes": "阶段推进以能否答题为主，不以联想为主。笔记重点为考点/易错/自测/待复习。",
        "notable_checks": {"self_test": "必须有自测题或待复习清单"},
    },
    "textbook_derivation": {
        "name": "教材推导",
        "desc": "逐章还原推导链，适合理论教材/数学/物理",
        "target": "理解每一步推导的前提和逻辑",
        "sections": ["推导链还原", "关键步理解", "边界条件", "课后验证"],
        "trial": False,
        "suggest_patterns": ["数学", "物理", "推导", "公式", "定理",
                            "证明", "原理"],
        "notable_checks": {},
    },
    "standard_lookup": {
        "name": "规范检索",
        "desc": "快速定位→理解条文→关联实际场景，适合工程规范/标准",
        "target": "理解条文并能定位到实际工程场景",
        "sections": ["条文定位", "条文理解", "工程场景", "边界说明"],
        "trial": False,
        "suggest_patterns": ["规范", "标准", "GB", "JT", "条文",
                            "设计", "施工", "验收"],
        "notable_checks": {},
    },
    "case_review": {
        "name": "案例复盘",
        "desc": "案例→决策链→替代方案→教训提炼，适合商业/工程案例",
        "target": "从案例中提炼可复用的决策模式",
        "sections": ["案例事实", "决策链还原", "替代方案", "教训提炼", "可复用原则"],
        "trial": False,
        "suggest_patterns": ["案例", "复盘", "事故", "失败", "教训",
                            "项目", "实践"],
        "notable_checks": {},
    },
    "historical_context": {
        "name": "历史脉络",
        "desc": "时间线→人物关系→事件转折→制度背景→现实镜鉴，适合历史/传记/组织史",
        "target": "理解历史事件的来龙去脉、关键人物选择和结构性原因",
        "sections": ["时间线梳理", "人物与势力", "关键转折", "制度/环境原因", "我的判断", "延伸联想"],
        "trial": True,
        "suggest_patterns": ["明朝那些事", "明朝那些事儿", "历史", "王朝", "帝王",
                            "皇帝", "朝代", "战争", "人物传记", "组织史",
                            "朱元璋", "朱棣", "万历", "张居正", "传记"],
        "stage_notes": "按历史脉络推进：先还原时间线和人物关系，再追问关键转折、制度背景、人物选择和可迁移镜鉴。不强求概念覆盖率，重点防止只复述故事。",
        "notable_checks": {"timeline": "必须有时间线或事件顺序", "judgment": "必须有个人判断或现实镜鉴"},
    },
    "literature_experience": {
        "name": "文学体验",
        "desc": "沉浸→感受→共鸣→表达，适合小说/散文/传记",
        "target": "深度体验文本，形成个人化的感受和表达",
        "sections": ["情境还原", "人物/主题理解", "我的共鸣", "延伸联想"],
        "trial": False,
        "suggest_patterns": ["小说", "散文", "传记", "文学", "故事",
                            "回忆录", "随笔"],
        "notable_checks": {},
    },
}

MODE_QUICK_NAMES = {
    "概念": "concept_deep_read", "精读": "concept_deep_read",
    "费曼": "concept_deep_read",
    "命题": "proposition_dialogue", "辨析": "proposition_dialogue",
    "哲学": "proposition_dialogue", "观点": "proposition_dialogue",
    "工具": "method_conversion", "方法": "method_conversion",
    "转化": "method_conversion", "行动": "method_conversion",
    "考试": "exam_mastery", "备考": "exam_mastery",
    "教材": "exam_mastery", "考证": "exam_mastery",
    "推导": "textbook_derivation", "数学": "textbook_derivation",
    "规范": "standard_lookup", "标准": "standard_lookup",
    "案例": "case_review", "复盘": "case_review",
    "历史": "historical_context", "脉络": "historical_context",
    "明朝": "historical_context", "传记": "historical_context",
    "文学": "literature_experience", "小说": "literature_experience",
    "散文": "literature_experience",
}


def list_modes(profile_name="personal"):
    """返回可用模式列表"""
    is_trial = (profile_name == "trial")
    result = []
    for key, mode in READING_MODES.items():
        if is_trial and not mode["trial"]:
            continue
        result.append({
            "key": key,
            "name": mode["name"],
            "desc": mode["desc"],
            "target": mode["target"],
            "sections": mode.get("sections", []),
        })
    return result


def get_mode(mode_key):
    """获取单个模式定义，不存在返回 None"""
    return READING_MODES.get(mode_key)


def allowed_modes(profile_name="personal"):
    """返回当前 profile 允许的模式键名列表"""
    is_trial = (profile_name == "trial")
    return [k for k, v in READING_MODES.items() if not is_trial or v["trial"]]


def suggest_mode(text, profile_name="personal"):
    """根据书名/描述建议阅读模式。返回 (mode_key, mode_dict, score)"""
    is_trial = (profile_name == "trial")
    best_key = None
    best_score = 0

    for key, mode in READING_MODES.items():
        if is_trial and not mode["trial"]:
            continue
        score = 0
        for pattern in mode.get("suggest_patterns", []):
            if pattern.lower() in text.lower():
                score += 1
        # 快速名称加权：精确匹配得更高分
        clean = text.strip()
        if clean in MODE_QUICK_NAMES:
            quick_key = MODE_QUICK_NAMES[clean]
            if quick_key == key:
                score += 10
        if score > best_score:
            best_score = score
            best_key = key

    if best_key and best_score > 0:
        return best_key, READING_MODES[best_key], best_score

    # 默认兜底：概念精读
    return "concept_deep_read", READING_MODES["concept_deep_read"], 0


def mode_hint_text(mode_key):
    """生成给 Agent 的追问方向提示"""
    mode = READING_MODES.get(mode_key, {})
    if not mode:
        return "使用默认四阶段精读流程。"
    return mode.get("stage_notes", "")


def mode_note_sections(mode_key):
    """返回该模式应有的笔记段落列表"""
    mode = READING_MODES.get(mode_key, {})
    return mode.get("sections", ["引用原文", "我的理解", "让我想到", "待探索"])


def mode_quality_checks(mode_key):
    """返回该模式的专项质量检查"""
    mode = READING_MODES.get(mode_key, {})
    return mode.get("notable_checks", {})
