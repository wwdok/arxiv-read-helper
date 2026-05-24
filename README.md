# arXiv Read Helper

输入 arXiv 论文网址，自动生成中文 HTML 阅读笔记 —— 保留公式、图片和原文排版，方便快速浏览和对照原文。

## 安装

1. 将 `arxiv-read-helper/` 放到 Claude Code 的 skills 目录下
2. 安装 Python 依赖：

```bash
pip install requests beautifulsoup4 pymupdf Pillow
```

## 使用方法

在 Claude Code 中输入：

```
帮我读这篇论文：https://arxiv.org/abs/2412.01506
```

Skill 会自动激活，下载论文源码并生成 HTML 笔记。

## 输出

生成的 HTML 文件保存在 `D:/论文阅读笔记合集/{论文标题}/`，包含：
- 中文翻译（按章节重要性分层处理）
- MathJax 渲染的 LaTeX 公式
- 内嵌的论文配图
- 元数据（作者、年份、链接等）

## 分层翻译策略

| 章节 | 处理方式 |
|------|----------|
| Abstract | 完整逐句翻译 |
| Introduction | 浓缩翻译，合并重复句子 |
| Related Work | 适当浓缩概括 |
| Method | 完整逐句翻译 |
| Experiments - Implementation Details | 逐字翻译 |
| Experiments - 结果 | 翻译关键结论，表格数据保留原文 |
| 图表标题 | 逐字翻译 |
| Conclusion | 完整翻译 |
| Appendix | 仅提取关键公式/结论 |
