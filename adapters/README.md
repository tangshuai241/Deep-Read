# DeepRead 入口适配层

## 架构

```
[外部入口]
  飞书 Bot     微信桥接      CLI              Claude Code (调试)
      │            │           │                    │
      └────────────┴─────┬─────┘                    │
                         ▼                          │
               agent.process_message()              │
              (会话保持 + 工具调用)                   │
                         │                          │
                    ┌────┴────┐                     │
                    ▼         ▼                     │
              Obsidian 笔记   终端输出              SKILL.md
```

## 飞书 Bot

### 单次测试

```bash
python adapters/feishu_bot.py once "精读《思考快与慢》第5章" --user tangshuai
```

### 事件监听（观察模式，不回复）

```bash
python adapters/feishu_bot.py listen --max-events 5
```

首条事件会打印完整原始结构用于调试。确认字段解析正确后，再开回复：

### 事件监听（自动回复）

```bash
python adapters/feishu_bot.py listen --reply
```

### 前置条件

- lark-cli 已登录 (`lark-cli auth login`)
- 飞书应用已配置 `im.message.receive_v1` 事件订阅
- 机器人有 `im:message.p2p_msg:readonly` 权限
- API Key 已设置 (DEEPSEEK_API_KEY 等)

### 接入步骤

1. 飞书开放平台创建应用 → 订阅 `im.message.receive_v1` 事件
2. `python adapters/feishu_bot.py listen --max-events 1` → 发一条消息 → 观察输出结构
3. 确认 sender_id/content 解析正确 → `listen --reply` 正式启用
