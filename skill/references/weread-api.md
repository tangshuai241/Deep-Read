# 微信读书 API 参考

## 定位

**可选增强模块，非核心依赖**。默认关闭。

## 启用

config.yaml 中 `integrations.weread.enabled: true` + 设置 `WEREAD_API_KEY` 环境变量。

## API 入口

- URL: `POST https://i.weread.qq.com/api/agent/gateway`
- 鉴权: `Authorization: Bearer $WEREAD_API_KEY`
- 每次请求 body 必须包含 `"skill_version": "1.0.3"`

## 可用接口

| 接口 | 用途 |
|------|------|
| `/shelf/sync` | 获取书架 |
| `/book/info` | 书籍信息 |
| `/book/chapterinfo` | 章节信息 |
| `/book/getprogress` | 阅读进度 |
| `/book/bookmarklist` | 划线/书签 |
| `/review/list/mine` | 我的书评 |
| `/book/bestbookmarks` | 热门标注 |

## 限制

- **无章节原文接口**，原文只能从本地 EPUB 读取
- API 可能变更
- 不同用户的 token 管理有隐私风险

## 容错

- 调用超时或错误 → 跳过云端同步，不中断本地笔记生成
- API Key 未设置 → 仅提示一次，不阻塞
- 获取进度失败 → 用 reading-notes.md 中的本地进度

## 书源优先级

1. 本地 EPUB（主）
2. 用户粘贴文本（备用）
3. 微信读书 API（辅助：进度/划线，不提供原文）
