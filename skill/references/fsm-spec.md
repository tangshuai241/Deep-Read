# FSM 有限状态机规范

## 状态文件

位置由 config.yaml `paths.state_dir` 指定（默认 `deepread/state/default/current.json`）。

## 结构

```json
{
  "current": {
    "book": null,
    "chapter": null,
    "section": null,
    "stage": "idle",
    "turn_count": 0,
    "user_goal": null,
    "last_transition": "2026-05-25"
  },
  "blindspots": [],
  "concepts_covered": [],
  "pending_connections": [],
  "session_summary": "",
  "profile_notes": []
}
```

## 状态管理（使用脚本）

```bash
# 查看当前状态
python state.py show

# 切换阶段
python state.py set --stage feynman --book "思考快与慢" --chapter 5

# 追加盲点/概念
python state.py set --add-blindspot "翻译质量敏感"
python state.py set --add-concept "认知放松"

# 更新摘要
python state.py set --summary "第5章第1节完成：认知放松与曝光效应"

# 重置
python state.py reset
```

## 状态机规则

- **每条消息处理前**：AI 必须先读状态文件
- **每次阶段切换时**：AI 必须更新状态文件
- **阶段切换重置 turn_count 为 1**
- **长对话中优先使用状态文件锚定上下文**

## 阶段枚举

| stage | 含义 |
|-------|------|
| `idle` | 空闲，等待用户命令 |
| `init` | 阶段0：初始化（确认范围/目标） |
| `feynman` | 阶段1：费曼输出 |
| `socratic` | 阶段2：苏格拉底式深化 |
| `associate` | 阶段3：强制联想 |
| `wrapup` | 阶段4：收尾 |

## 多人预留

状态目录结构预留多用户：

```
deepread/state/
  default/              ← 当前单用户
    current.json
    history/
  user_b/               ← 阶段3启用
    current.json
```
