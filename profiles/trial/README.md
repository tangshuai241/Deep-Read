# DeepRead 体验版 (Trial)

## 这是什么

DeepRead Trial 是给朋友/同学试用的体验版。走手机 IM 主路径，不需要 Obsidian，不需要 LLM-Wiki。

## 最快开始

```powershell
# 1. 安装
.\install.ps1 -Profile trial

# 2. 编辑生成的 config.yaml，填写 LLM API Key
# 3. 配置飞书 Bot（见 docs/快速启动-新手版.md）
# 4. 手机给 Bot 发 "你好"
```

## 和完整版有什么区别

| | Trial | Personal |
|---|---|---|
| 学习入口 | 手机飞书 | 飞书/终端/Claude Code |
| Obsidian | 可选 | 必启用 |
| LLM-Wiki | 关闭 | 可启用 |
| 概念卡 | 固定基础包 (20-30张) | 完整扫描用户 vault |
| 认知画像 | 关闭 | 可启用 |
| 阅读模式 | 5 个常用 | 全部 9 个 |
| Web 控制台 | 运维/排障 | 运维/排障 |

## 首次阅读

给 Bot 发：
```
我想开始读一本书
```

Bot 会问书名、建议阅读模式，然后进入对话。
