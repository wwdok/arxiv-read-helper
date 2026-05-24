# arXiv Read Helper

输入 arXiv 论文网址，自动生成中文 HTML 阅读笔记 —— 保留公式、图片和原文排版，方便快速浏览和对照原文。

适用于每天需要快速阅读大量 CV/AI 论文的算法工程师。

## 工作原理

```
arxiv.org/abs/XXXX.XXXXX
       │
       ▼
1. 下载 TeX 源码包 (.tar.gz)
       │
       ▼
2. 解析 LaTeX → 展平多文件、提取元数据、转换图片
       │
       ▼
3. Claude 按分层策略翻译 (方法/实验逐字译, 相关工作浓缩)
       │
       ▼
4. 生成自包含 HTML (MathJax + base64 图片)
```

## 安装

### 1. 安装 Skill

将 `arxiv-read-helper/` 文件夹放到 Claude Code 的 skills 目录：

- **Windows**: `%USERPROFILE%\.claude\skills\`
- **macOS / Linux**: `~/.claude/skills/`

### 2. 安装 Python 依赖

需要 Python 3.8+:

```bash
pip install requests beautifulsoup4 pymupdf Pillow
```

## 使用方法

在 Claude Code 中直接输入 arXiv 链接即可，Skill 会自动激活：

```
帮我读这篇论文：https://arxiv.org/abs/2412.01506
```

或者更简洁：

```
解读 https://arxiv.org/abs/1706.03762
```

### 支持的 URL 格式

- `https://arxiv.org/abs/2412.01506`
- `https://arxiv.org/abs/2412.01506v2`
- `https://arxiv.org/pdf/2412.01506`
- 直接给 arXiv ID: `2412.01506`
- 后续版本将支持直接 PDF 链接

## 输出

生成的 HTML 文件保存在 `D:/论文阅读笔记合集/{论文标题}/`，包含：

```
{论文标题}/
├── {论文标题}.html      ← 中文阅读笔记 (自包含, 可在浏览器打开)
├── metadata.json         ← 论文元数据
├── cleaned.tex           ← 展平后的 LaTeX 源码
├── figures.json           ← 图片 base64 映射
└── source/               ← 原始 TeX 源码 (方便对照原文)
```

HTML 文件可以：
- 在任何浏览器中打开（无需服务器）
- 完美渲染 LaTeX 公式（MathJax）
- 直接打印或导出 PDF
- 在移动设备上阅读（响应式设计）

## 分层翻译策略

| 章节 | 处理方式 |
|------|----------|
| 元数据 | 展示标题（中英双语）、作者、年份、链接 |
| Abstract | 完整逐句翻译 |
| Introduction | 浓缩翻译，合并重复句子 |
| Related Work | 适当浓缩概括 |
| Method | 完整逐句翻译 |
| Experiments - Implementation Details | 逐字翻译 |
| Experiments - 结果 | 翻译关键结论，表格数据保留原文 |
| 图表标题 (captions) | 逐字翻译 |
| Conclusion | 完整翻译 |
| Appendix | 仅提取关键公式/结论 |

**翻译规则：**
- 保留所有 `\ref{}`、`\cite{}` 引用，方便对照原文
- 保留全部 LaTeX 公式环境，不翻译数学符号
- 技术术语首次出现时附英文原文
- 模型/架构名保持英文（如 SLat, TRELLIS, ResNet）

## 配置

如需修改输出目录，编辑 `scripts/preprocess_arxiv.py` 第 38 行：

```python
OUTPUT_BASE = Path("D:/论文阅读笔记合集")  # 改为你的路径
```

## Roadmap

- [x] arXiv TeX 源码解析
- [x] 分层翻译 + HTML 生成
- [x] 图片内嵌（PDF/PNG/JPEG → base64）
- [x] 元数据提取（作者、年份、GitHub 链接等）
- [ ] PDF 输入支持（通过 MinerU 解析）
- [ ] 自定义输出目录配置
- [ ] 批量处理多篇论文
- [ ] 中英双语切换

## 项目结构

```
arxiv-read-helper/
├── SKILL.md                        # Skill 定义和工作流
├── README.md                       # 本文件
├── LICENSE.txt                     # MIT License
├── scripts/
│   └── preprocess_arxiv.py         # 预处理脚本
└── templates/
    └── paper_template.html         # HTML/CSS 模板
```

## 致谢

- [arXiv](https://arxiv.org/) — 开放获取的学术论文预印本
- [MathJax](https://www.mathjax.org/) — 浏览器端 LaTeX 渲染

## License

MIT
