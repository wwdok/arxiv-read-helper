---
name: arxiv-read-helper
description: 输入 arXiv 论文网址，自动下载 TeX 源码，生成含翻译、公式、图片的中文 HTML 阅读笔记。适用于需要快速阅读大量计算机视觉/AI 领域英文论文的算法工程师。触发条件：用户提供 arxiv.org/abs/* 或 arxiv.org/pdf/* 链接并要求解读、翻译、做笔记。
license: MIT
---

# arXiv Read Helper

## Overview

This skill converts an arXiv paper into a self-contained Chinese HTML reading note. It downloads the TeX source, extracts metadata and figures, then Claude translates and compresses the content according to a tiered strategy, outputting a single HTML file with MathJax-rendered formulas and embedded images.

## Prerequisites

Ensure Python dependencies are installed:

```bash
pip install requests beautifulsoup4 pymupdf Pillow
```

## Workflow

### Step 1: Run the Preprocessing Script

When the user provides an arXiv URL (e.g., `https://arxiv.org/abs/2412.01506`):

```bash
python ./scripts/preprocess_arxiv.py "<arxiv_url>"
```

The script will:
1. Extract the arXiv ID from the URL
2. Fetch metadata from the abstract page (title, authors, year, links)
3. Download the TeX source tarball from `arxiv.org/e-print/{id}`
4. Extract to `source/` under the output directory
5. Flatten `\input`/`\include` into a single `cleaned.tex`
6. Convert all figures to base64 PNG, outputting a `figures.json` mapping
7. Save `metadata.json` with all extracted metadata

Output directory: `D:/论文阅读笔记合集/{paper_title}/`
Generated files:
- `source/` — original TeX source (kept for reference)
- `cleaned.tex` — flattened, cleaned TeX
- `metadata.json` — paper metadata
- `figures.json` — figure name → base64 data URI mapping

### Step 2: Read the Preprocessed Output

Read these files:
- `cleaned.tex` — the flattened LaTeX source
- `metadata.json` — paper metadata
- `figures.json` — base64 image data (read only if needed, can be large)

### Step 3: Analyze and Translate

Parse the LaTeX structure and apply the tiered translation strategy:

| Section | Strategy |
|---------|----------|
| Metadata | Display: title (Chinese + English), authors, year, arxiv URL, project URL, GitHub URL |
| Abstract | Full sentence-by-sentence translation |
| Introduction | Condensed translation — merge repetitive sentences |
| Related Work | Condensed summary (not mechanical one-sentence-per-work) |
| Method | Full sentence-by-sentence translation |
| Experiments — Implementation Details | **Word-for-word** translation |
| Experiments — Main results | Translate key conclusions, preserve table data as-is |
| Figure/Table captions | **Word-for-word** translation |
| Conclusion | Full sentence-by-sentence translation |
| Appendix | Extract only key formulas/conclusions, skip rest |

**Key rules:**
- Preserve all `\label{...}`, `\ref{...}`, `\cite{...}` references in the output
- Preserve all equation environments (`\begin{equation}`, `\begin{align}`, etc.) as-is for MathJax
- Do NOT translate mathematical symbols or variable names inside equations
- When translating paragraph text, preserve LaTeX inline math (`$...$`) and display math (`$$...$$`, `\[...\]`)

### Step 4: Generate HTML

Use `templates/paper_template.html` as the design reference. The output must be a self-contained HTML file with:

1. **Metadata header**: paper title (Chinese + English), authors, year, arxiv URL, project URL, GitHub URL
2. **Body**: Translated content following the original paper's section structure
3. **Formulas**: Rendered via MathJax CDN (preserve all LaTeX math environments)
4. **Figures**: Embedded as `<img src="data:image/png;base64,...">` using the mapping from `figures.json`
5. **Layout**: Clean single-column reading layout with proper typography

CSS requirements:
- Max-width ~900px centered, good for reading
- Clear section hierarchy (h1, h2, h3)
- Figure captions styled distinctly
- Responsive, readable on both desktop and tablet
- Print-friendly

### Step 5: Save the Output

Save the completed HTML to:
```
D:/论文阅读笔记合集/{paper_title}/{paper_title}.html
```

Where `{paper_title}` is sanitized: replace `\` `/` `:` `*` `?` `"` `<` `>` `|` with `_`, trim to reasonable length.

The original `source/` directory is kept alongside the HTML for reference.

---

## HTML Template Reference

See `templates/paper_template.html` for the exact HTML/CSS structure to use.

## Translation Quality Notes

- Use natural, fluid Chinese; avoid translationese
- Technical terms: keep standard Chinese translations (e.g., "卷积神经网络" for CNN), but keep model/architecture names in original English
- For ambiguous technical terms, include the original English in parentheses on first occurrence
- Maintain the logical flow of the original paper; do not reorder sections
