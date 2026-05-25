# DeepRead 入口适配层

## 架构

```
[外部入口]
  飞书 Bot    微信桥接    CLI      Claude Code (主)
      │          │         │            │
      └──────────┴────┬────┘            │
                      ▼                 │
               cli.py (命令路由)         │
                 /    |    \            │
           进度/复习 搜索  提取章节      │
                                │       │
                                ▼       ▼
                           extract_epub  SKILL.md
                           → Claude Code 精读
```

## 已实现的入口

| 入口 | 文件 | 状态 |
|------|------|:--:|
| Claude Code | `SKILL.md` | 生产（主流） |
| CLI | `cli.py` | 就绪 |
| 飞书 Bot | `adapters/feishu_bot.py` | 骨架（单次处理可用） |

## CLI 命令

```bash
python cli.py progress          # 读书进度
python cli.py review            # 随机复习
python cli.py think             # 慢思考问题
python cli.py search 关键词     # 搜索 vault
python cli.py status            # 阅读状态
python cli.py read 书名 章节号  # 提取章节 + 提示粘贴到 Claude Code
```

## 飞书 Bot 接入步骤（待激活）

1. 飞书开放平台创建应用 → 订阅 `im.message.receive_v1` 事件
2. 配置事件回调 URL 或使用 lark-cli 长连接
3. `python feishu_bot.py` 监听消息
4. 收到消息 → `handle_message()` → `cli.py` → 回复

## 设计决策

- **对话式精读保留在 Claude Code**：四阶段多轮对话需要 LLM 驱动，CLI/飞书只是入口
- **非对话命令直接 CLI 处理**：进度、复习、搜索等不依赖 LLM
- **飞书 Bot 不替代 Claude Code**：它负责轻量查询 + 触发精读流程
