# EPUB 解析规范

## 脚本优先

**不要手搓 EPUB 解析**。使用专用脚本：

```bash
# 由 SKILL.md 中的 config.yaml 定位 books_dir
python <deepread>/scripts/extract_epub.py --book "<书名>.epub" --list
python <deepread>/scripts/extract_epub.py --book "<书名>.epub" --chapter 5
python <deepread>/scripts/extract_epub.py --book "<书名>.epub" --chapter 5 --json
python <deepread>/scripts/extract_epub.py --book "<书名>.epub" --meta --json
```

## JSON 输出结构

```json
{
  "book": {"title": "...", "author": "...", "chapters": 38},
  "chapter": {"index": 5, "title": "...", "word_count": 9044},
  "sections": [
    {"title": "_intro", "text": "...", "word_count": 744},
    {"title": "由记忆造成的错觉", "text": "...", "word_count": 1150}
  ]
}
```

## 工作流

1. 用户说"读第5章" → 运行 `extract_epub.py --chapter 5 --json`
2. 超过 8000 字的章节 → 提示用户是否拆开读
3. 按小节逐一进入阶段1
4. 如果用户选择整章一起读 → 逐片做费曼输出，阶段4统合

## 边界情况

- EPUB 不存在 → 提示用户检查文件名，或粘贴原文
- 章节号不存在 → 列出可用章节
- DRM/图片扫描版 → 返回错误，提示用户粘贴原文
- 编码异常 → 脚本自动用 chardet 检测
