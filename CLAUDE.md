# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

This repository **is itself a Claude Code Skill** — not a normal application. The user installs it by copying the directory into `%USERPROFILE%\.claude\skills\` (Windows) or `~/.claude/skills/`. `SKILL.md` is the entry point Claude reads when the skill is triggered (arXiv URL in the user's message).

Two execution modes coexist:

- **Python preprocessor** (`scripts/preprocess_arxiv.py`) — downloads + parses TeX, runs once per paper.
- **Claude itself** — reads `cleaned.tex` + `figures_index.json` + `metadata.json`, produces the translated HTML using `templates/paper_template.html` as the design reference. There is **no script that generates the HTML** — that step is the LLM's job, driven by `SKILL.md` Step 3–5.

When editing this repo, remember the workflow is split this way: a code change in `preprocess_arxiv.py` only affects the artifacts Claude consumes; a change in `SKILL.md` changes Claude's translation behavior; a change in `templates/paper_template.html` changes the HTML design.

## Running the preprocessor

```bash
python ./scripts/preprocess_arxiv.py "<arxiv_url>"
```

Dependencies (Python 3.8+):

```bash
pip install requests beautifulsoup4 pymupdf Pillow
```

There are **no tests, no linter config, and no build step**. Test changes by running the script against a real arXiv URL and inspecting the resulting `cleaned.tex` / `figures_index.json` in the output directory.

## Output lives outside the repo

The preprocessor writes to `D:/论文阅读笔记合集/{sanitized_title}/` (hardcoded at `scripts/preprocess_arxiv.py:31` as `OUTPUT_BASE`). It does **not** write into the repo. When debugging, look there — not in the working tree.

Per-paper output layout:
- `source/` — extracted TeX tarball (figures stay here; nothing is copied or converted)
- `cleaned.tex` — flattened TeX (all `\input`/`\include` recursively inlined with `% === BEGIN/END ===` markers)
- `metadata.json`, `figures_index.json` — what Claude reads in Step 3
- `{title}.html` — written by Claude in Step 5

## Key design decisions (non-obvious)

- **PDF figures are converted to SVG at preprocess time.** `convert_pdf_to_svg` (via `pymupdf`/`fitz`'s `page.get_svg_image`) writes vector SVG to `figures_svg/`. SVG keeps text/lines crisp at any zoom; raster sub-images inside the PDF (photos, screenshots) get embedded as base64 PNG within the SVG, so figures dominated by photos can still be a few MB — accepted as the cost of sharp vector content. If SVG fails for a given PDF (e.g., uses features pymupdf can't translate), `convert_pdf_to_png` falls back to a PNG capped at 2400 px on the longest edge / 200 DPI in `figures_png/`. PNG/JPG figures are passed through unchanged; original PDFs stay in `source/` for reference. `figures_index.json` points at whatever was successfully produced, so the HTML uses `<img>` uniformly — no `<embed>` / browser PDF plugin. If `pymupdf` import fails the script warns and falls back to the original PDF path.
- **Wide tables need a wrapper div.** `templates/paper_template.html` provides `.table-wrapper { overflow-x: auto; }`. Tables without that wrapper will overflow the 900px container and break the page layout. This is enforced in `SKILL.md` Step 4 rule 5 — keep that rule in sync with the template.
- **Citations and refs are deleted, not preserved.** `\cite{...}`, `\ref{...}`, `\label{...}` are removed from the Chinese output (they're meaningless without LaTeX compilation). See SKILL.md "Key rules".
- **Flattening is depth-limited and dedup'd.** `flatten_tex` tracks resolved paths in a `seen` set to break circular `\input`s and diamond inclusions; `MAX_FLATTEN_DEPTH = 10`.
- **`\graphicspath` is honored per-section.** `find_figures_in_tex` scans both the main file and each flattened sub-file section for its own `\graphicspath`, resolving relative to each declaring file's directory.
- **Tarball extraction is path-traversal-safe.** `download_source` rejects `..`/absolute paths and uses `tarfile.data_filter` on Python 3.12+.
- **Title sanitization is Windows-aware.** `sanitize_filename` strips `<>:"/\|?*`, trailing dots/spaces, and caps length at 80 chars — required for Windows path rules since `OUTPUT_BASE` is on Windows.

## Translation behavior is in SKILL.md, not code

The tiered translation strategy (Abstract = full translation, Related Work = condensed, Implementation Details = word-for-word, Appendix = key formulas only, etc.) lives in `SKILL.md` Step 3. If the user reports translation quality issues, the fix is almost always editing `SKILL.md` rather than Python.
