#!/usr/bin/env python3
"""
arXiv Read Helper — Preprocessing Script

Downloads arXiv TeX source, flattens multi-file projects,
converts figures to base64, and outputs cleaned .tex + metadata.

Usage:
    python preprocess_arxiv.py <arxiv_url>
    python preprocess_arxiv.py https://arxiv.org/abs/2412.01506

Output directory: D:/论文阅读笔记合集/{paper_title}/
"""

import json
import os
import re
import sys
import tarfile
import base64
import io
import shutil
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from PIL import Image

# ============================================================
# Constants
# ============================================================

OUTPUT_BASE = Path("D:/论文阅读笔记合集")
ARXIV_ABS_URL = "https://arxiv.org/abs/"
ARXIV_EPRINT_URL = "https://arxiv.org/e-print/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ArxivReadHelper/1.0; mailto:your@email.com)"
}
# Max recursive depth for \input/\include flattening
MAX_FLATTEN_DEPTH = 10

# ============================================================
# Utilities
# ============================================================

def extract_arxiv_id(url: str) -> str:
    """Extract arXiv ID from various URL formats.

    Supported formats:
    - https://arxiv.org/abs/2412.01506
    - https://arxiv.org/abs/2412.01506v2
    - https://arxiv.org/pdf/2412.01506
    - https://arxiv.org/pdf/2412.01506.pdf
    - arxiv.org/abs/2412.01506
    - 2412.01506 (bare ID)
    - 2412.01506v3 (bare versioned ID)
    """
    url = url.strip()

    # If it's already a bare ID (with optional version suffix)
    if re.match(r'^\d{4}\.\d{4,5}(v\d+)?$', url):
        # Strip version suffix to get canonical ID
        return re.sub(r'v\d+$', '', url)

    # Try to extract from URL
    patterns = [
        r'arxiv\.org/abs/(\d{4}\.\d{4,5})(?:v\d+)?',
        r'arxiv\.org/pdf/(\d{4}\.\d{4,5})(?:v\d+)?(?:\.pdf)?',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)

    raise ValueError(f"Cannot extract arXiv ID from: {url}")


def sanitize_filename(name: str, max_len: int = 80) -> str:
    """Sanitize a string for use as a directory name."""
    # Replace LaTeX specials
    name = name.replace("\\", "").replace("{", "").replace("}", "")
    # Replace invalid filesystem characters
    invalid = r'[<>:"/|?*]'
    name = re.sub(invalid, "_", name)
    # Collapse whitespace
    name = re.sub(r'\s+', " ", name).strip()
    # Remove leading/trailing dots and spaces (Windows restriction)
    name = name.strip(". ")
    # Trim to max length
    if len(name) > max_len:
        name = name[:max_len].rstrip()
    return name


# ============================================================
# arXiv Metadata Fetcher
# ============================================================

def fetch_metadata(arxiv_id: str) -> dict:
    """Fetch paper metadata from the arXiv abstract page.

    Returns a dict with keys:
        title, authors (list), abstract, year, arxiv_url,
        project_url, github_url, pdf_url, comments
    """
    url = f"{ARXIV_ABS_URL}{arxiv_id}"
    print(f"  Fetching: {url}")
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # Title
    title_el = soup.find("h1", class_="title")
    title = title_el.get_text(strip=True).removeprefix("Title:").strip() if title_el else arxiv_id

    # Authors
    authors_el = soup.find("div", class_="authors")
    authors = []
    if authors_el:
        for a in authors_el.find_all("a"):
            name = a.get_text(strip=True)
            if name and name.lower() != "authors:":
                authors.append(name)

    # Abstract
    abstract_el = soup.find("blockquote", class_="abstract")
    abstract = ""
    if abstract_el:
        abstract = abstract_el.get_text(strip=True).removeprefix("Abstract:").strip()

    # Year — extract from submission history date
    # The submission history contains dates like "Mon, 2 Dec 2024 ..."
    year = ""
    sub_history = soup.find("div", class_="submission-history")
    if sub_history:
        # Match dates like "Mon, 2 Dec 2024" or "Thu, 17 Apr 2025"
        date_match = re.search(
            r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun),\s*\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{4})',
            sub_history.get_text()
        )
        if date_match:
            year = date_match.group(1)

    # Comments (often contains DOI, published venue, project page, etc.)
    # Use CSS selector to correctly target the comments content cell
    comments = ""
    comments_el = soup.select_one("td.tablecell.comments.mathjax")
    if comments_el:
        comments = comments_el.get_text(strip=True)

    # Extract external links from the abstract page
    project_url = ""
    github_url = ""

    # Look for links in the extra sections
    for link in soup.find_all("a", href=True):
        href = link["href"]
        text = link.get_text(strip=True).lower()
        if "github.com" in href:
            # Check if it's a real GitHub repo link (not just github.com alone)
            if re.search(r'github\.com/[^/]+/[^/\s]+', href):
                github_url = href
        # Look for project page links
        if text in ("project page", "project website", "code", "homepage"):
            if "github" in href.lower():
                github_url = href
            elif project_url == "" and "arxiv" not in href.lower():
                project_url = href

    return {
        "arxiv_id": arxiv_id,
        "title": title,
        "authors": authors,
        "abstract": abstract,
        "year": year,
        "arxiv_url": f"https://arxiv.org/abs/{arxiv_id}",
        "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}.pdf",
        "project_url": project_url,
        "github_url": github_url,
        "comments": comments,
    }


# ============================================================
# TeX Source Download and Extraction
# ============================================================

def download_source(arxiv_id: str, dest_dir: Path) -> None:
    """Download and extract the TeX source tarball.

    Args:
        arxiv_id: arXiv paper ID
        dest_dir: Directory to extract into (source/ will be created inside it)

    Raises:
        FileNotFoundError: No TeX source available
        RuntimeError: Rate limiting or other download issues
    """
    url = f"{ARXIV_EPRINT_URL}{arxiv_id}"
    print(f"  Downloading: {url}")
    resp = requests.get(url, headers=HEADERS, timeout=60)

    # arXiv returns 404 if no TeX source available
    if resp.status_code == 404:
        raise FileNotFoundError(
            f"No TeX source available for {arxiv_id}. "
            f"This paper may have been submitted as PDF only."
        )
    resp.raise_for_status()

    # arXiv sometimes returns a redirect page if fetching too fast
    content_type = resp.headers.get("Content-Type", "")
    if "text/html" in content_type and len(resp.text) < 2000:
        raise RuntimeError(
            f"Unexpected HTML response instead of tarball. "
            f"arXiv may be rate-limiting. Try again in a few seconds.\n"
            f"Response: {resp.text[:500]}"
        )

    # Save the tarball to a temp location
    tarball_path = dest_dir / "_source.tar.gz"
    with open(tarball_path, "wb") as f:
        f.write(resp.content)

    extract_dir = dest_dir / "source"
    extract_dir.mkdir(parents=True, exist_ok=True)

    # Extract safely — preserve directory structure but prevent path traversal
    with tarfile.open(tarball_path, "r:gz") as tar:
        for member in tar.getmembers():
            # Security: normalize the path and reject dangerous ones
            name = os.path.normpath(member.name).lstrip(os.sep)
            if name.startswith("..") or os.path.isabs(name):
                print(f"  [WARNING] Skipping unsafe path: {member.name}")
                continue
            member.name = name
            # Use data_filter if available (Python 3.12+), else trust our own check
            if hasattr(tarfile, "data_filter"):
                tar.extract(member, extract_dir, filter="data")
            else:
                tar.extract(member, extract_dir)

    # Remove the tarball
    tarball_path.unlink()

    # Flatten one level of subdirectory if the tarball has a single top-level folder
    flatten_extracted(extract_dir)


def flatten_extracted(extract_dir: Path) -> None:
    """If the extracted source has a single top-level directory, move its
    contents up one level. This handles the common arXiv tarball pattern
    where all files are inside one wrapper directory."""
    entries = list(extract_dir.iterdir())
    subdirs = [e for e in entries if e.is_dir()]
    files = [e for e in entries if e.is_file()]

    # Only flatten if there's exactly one directory and no files at top level
    if len(subdirs) == 1 and len(files) == 0:
        subdir = subdirs[0]
        for item in subdir.iterdir():
            dest = extract_dir / item.name
            # Handle name conflicts
            if dest.exists():
                if dest.is_dir():
                    shutil.rmtree(str(dest))
                else:
                    dest.unlink()
            shutil.move(str(item), str(dest))
        # Use rmtree instead of rmdir to handle non-empty subdirectories
        shutil.rmtree(str(subdir))
        print(f"  Flattened subdirectory: {subdir.name}")


# ============================================================
# TeX Processing
# ============================================================

def find_main_tex(source_dir: Path) -> Path:
    """Find the main .tex file (the one with \\documentclass or \\documentstyle).

    Priority:
    1. File containing \\documentclass
    2. Largest .tex file
    3. Any .tex file
    """
    tex_files = list(source_dir.glob("*.tex"))
    if not tex_files:
        # Search all subdirectories recursively
        tex_files = list(source_dir.glob("**/*.tex"))

    if not tex_files:
        raise FileNotFoundError(f"No .tex files found in {source_dir}")

    # Look for \\documentclass
    for tex_file in tex_files:
        try:
            content = tex_file.read_text(encoding="utf-8", errors="replace")
            if "\\documentclass" in content or "\\documentstyle" in content:
                return tex_file
        except Exception:
            continue

    # Fallback: largest file
    tex_files.sort(key=lambda f: f.stat().st_size, reverse=True)
    return tex_files[0]


def resolve_input_path(ref: str, main_file: Path, source_dir: Path) -> Path:
    """Resolve an \\input or \\include reference to a file path.

    Handles:
    - Relative paths (relative to main file)
    - Paths relative to source root
    - With and without .tex extension
    """
    # Clean the reference
    ref = ref.strip().strip('"').strip("'")

    # Add .tex if no extension
    if not ref.endswith(".tex"):
        candidates = [f"{ref}.tex", ref]
    else:
        candidates = [ref]

    for candidate in candidates:
        # Try relative to main file's directory
        full = main_file.parent / candidate
        try:
            full = full.resolve(strict=False)
        except Exception:
            full = main_file.parent / candidate
        if full.exists():
            return full

        # Try relative to source root
        full = source_dir / candidate
        try:
            full = full.resolve(strict=False)
        except Exception:
            full = source_dir / candidate
        if full.exists():
            return full

    return None


def flatten_tex(main_file: Path, source_dir: Path, max_depth: int = MAX_FLATTEN_DEPTH) -> str:
    """Flatten \\input and \\include references into a single TeX document.

    Recursively resolves \\input{file} and \\include{file} commands,
    replacing them with the content of the referenced file.
    Tracks already-included files to avoid circular references and
    diamond-dependency double-inclusion.
    """
    seen = set()

    def resolve(content: str, base_file: Path, depth: int = 0) -> str:
        if depth > max_depth:
            return content

        def replace_input(match):
            cmd = match.group(1)  # input or include
            ref = match.group(2)

            resolved = resolve_input_path(ref, base_file, source_dir)
            if resolved is None:
                return match.group(0)  # Keep original if not found

            resolved_key = str(resolved.resolve())
            if resolved_key in seen:
                return f"% [Skipped already-included file: {ref}]"
            seen.add(resolved_key)

            try:
                sub_content = resolved.read_text(encoding="utf-8", errors="replace")
            except Exception:
                return match.group(0)

            # Recursively resolve nested inputs
            resolved_content = resolve(sub_content, resolved, depth + 1)
            return f"\n% === BEGIN: {ref} ===\n{resolved_content}\n% === END: {ref} ===\n"

        # Match \\input{file} and \\include{file}
        # The [^}]+ captures everything up to the closing brace
        pattern = r'\\(input|include)\{([^}]+)\}'
        return re.sub(pattern, replace_input, content)

    content = main_file.read_text(encoding="utf-8", errors="replace")
    seen.add(str(main_file.resolve()))
    return resolve(content, main_file)


def strip_preamble_comments(content: str) -> str:
    """Remove excessive consecutive comment lines in the preamble,
    but keep structured comments and all comments after \\begin{document}."""
    lines = content.split("\n")
    result = []
    in_preamble = True
    consecutive_comments = 0

    for line in lines:
        stripped = line.strip()

        if "\\begin{document}" in stripped:
            in_preamble = False

        if in_preamble and stripped.startswith("%"):
            consecutive_comments += 1
            if consecutive_comments <= 2:
                result.append(line)
            # else: skip this line (third+ consecutive comment)
        else:
            consecutive_comments = 0
            result.append(line)

    return "\n".join(result)


# ============================================================
# Figure Processing
# ============================================================

def find_graphicspath(content: str, source_dir: Path) -> list:
    """Extract paths from \\graphicspath declarations.

    Handles: \\graphicspath{{figures/}{images/}}
    Returns list of Path objects.
    """
    paths = []
    pattern = r'\\graphicspath\{(\{.*?\})\}'
    match = re.search(pattern, content, re.DOTALL)
    if match:
        inner = match.group(1)
        # Extract each {path} inside
        for m in re.finditer(r'\{([^}]+)\}', inner):
            p = m.group(1).strip()
            if p:
                paths.append(source_dir / p)
    return paths


def find_figures_in_tex(content: str, source_dir: Path) -> dict:
    """Find all figure files referenced in the TeX source via \\includegraphics.

    Handles \\graphicspath declarations.

    Returns a dict: {figure_name: Path_to_figure_file}
    """
    figures = {}
    graphics_paths = find_graphicspath(content, source_dir)

    # Match \\includegraphics[options]{path/to/figure}
    pattern = r'\\includegraphics(?:\[.*?\])?\{([^}]+)\}'
    for match in re.finditer(pattern, content):
        ref = match.group(1)
        # Remove file extension for searching
        ref_no_ext = ref.rsplit(".", 1)[0] if "." in ref else ref
        ref_name = Path(ref).name

        # Build candidate search list
        # 1. Exact glob relative to source_dir
        # 2. Search in graphicspath directories
        # 3. Recursive search for filename

        candidates = (list(source_dir.glob(f"{ref_no_ext}.*")) +
                      list(source_dir.glob(f"**/{ref_name}")) +
                      list(source_dir.glob(f"**/{ref_no_ext}.*")))

        for gp in graphics_paths:
            candidates += list(gp.glob(f"{ref_no_ext}.*"))

        for candidate in candidates:
            ext = candidate.suffix.lower()
            if ext in (".pdf", ".png", ".jpg", ".jpeg", ".eps"):
                # Use the \\includegraphics argument as key
                figures[ref] = candidate
                break

    return figures


def convert_to_base64_png(figure_path: Path) -> str:
    """Convert a figure file to a base64-encoded PNG data URI.

    Supports: .png, .jpg, .jpeg, .pdf (via PyMuPDF), .eps (warn and skip)
    Returns: "data:image/png;base64,..." or None if conversion fails
    """
    ext = figure_path.suffix.lower()

    if ext in (".png", ".jpg", ".jpeg"):
        with open(figure_path, "rb") as f:
            img_data = f.read()

        if ext == ".png":
            return f"data:image/png;base64,{base64.b64encode(img_data).decode()}"

        # Convert JPEG to PNG for consistency
        try:
            img = Image.open(io.BytesIO(img_data))
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}"
        except Exception as e:
            print(f"    [WARNING] Failed to convert JPEG: {e}")
            return None

    elif ext == ".pdf":
        try:
            import fitz  # PyMuPDF
        except ImportError:
            print(f"    [WARNING] PyMuPDF not installed, cannot convert PDF figure: {figure_path}")
            return None

        try:
            doc = fitz.open(str(figure_path))
            if len(doc) == 0:
                doc.close()
                return None
            page = doc[0]
            # Render at ~200 DPI for good quality
            mat = fitz.Matrix(2.78, 2.78)
            pix = page.get_pixmap(matrix=mat)
            img_data = pix.tobytes("png")
            doc.close()
            return f"data:image/png;base64,{base64.b64encode(img_data).decode()}"
        except Exception as e:
            print(f"    [WARNING] Failed to convert PDF: {e}")
            return None

    elif ext == ".eps":
        print(f"    [WARNING] EPS conversion requires Ghostscript, skipping: {figure_path}")
        return None

    return None


# ============================================================
# Main Entry Point
# ============================================================

def main():
    if len(sys.argv) < 2:
        print("Usage: python preprocess_arxiv.py <arxiv_url>")
        print("Example: python preprocess_arxiv.py https://arxiv.org/abs/2412.01506")
        sys.exit(1)

    arxiv_url = sys.argv[1]
    try:
        arxiv_id = extract_arxiv_id(arxiv_url)
    except ValueError as e:
        print(f"ERROR: {e}")
        print("Supported formats:")
        print("  https://arxiv.org/abs/2412.01506")
        print("  https://arxiv.org/abs/2412.01506v2")
        print("  https://arxiv.org/pdf/2412.01506")
        print("  2412.01506")
        sys.exit(1)

    print(f"arXiv ID: {arxiv_id}")

    # 1. Fetch metadata
    print("\n[1/5] Fetching metadata...")
    try:
        metadata = fetch_metadata(arxiv_id)
    except requests.HTTPError as e:
        if e.response.status_code == 404:
            print(f"  ERROR: Paper not found. Invalid arXiv ID: {arxiv_id}")
        else:
            print(f"  ERROR: HTTP {e.response.status_code} when fetching metadata.")
        sys.exit(1)
    except requests.RequestException as e:
        print(f"  ERROR: Network error while fetching metadata: {e}")
        sys.exit(1)
    print(f"  Title: {metadata['title']}")
    print(f"  Authors: {', '.join(metadata['authors'][:5])}{'...' if len(metadata['authors']) > 5 else ''}")
    print(f"  Year: {metadata['year'] or 'unknown'}")

    # 2. Setup output directory
    paper_dirname = sanitize_filename(metadata["title"] or arxiv_id)
    output_dir = OUTPUT_BASE / paper_dirname
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"\nOutput directory: {output_dir}")

    # 3. Download TeX source
    print("\n[2/5] Downloading TeX source...")
    source_dir = output_dir / "source"
    try:
        download_source(arxiv_id, output_dir)
        print(f"  Extracted to: {source_dir}")
    except FileNotFoundError as e:
        print(f"  Note: {e}")
        print("  Saving metadata-only output...")
        metadata_path = output_dir / "metadata.json"
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        print(f"  Metadata saved to: {metadata_path}")
        return 0
    except RuntimeError as e:
        print(f"  ERROR: {e}")
        print("  Saving metadata-only output...")
        metadata_path = output_dir / "metadata.json"
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        print(f"  Metadata saved to: {metadata_path}")
        return 1

    # 4. Find and flatten main TeX
    print("\n[3/5] Processing TeX source...")
    main_file = find_main_tex(source_dir)
    print(f"  Main file: {main_file.name}")

    flattened = flatten_tex(main_file, source_dir)
    print(f"  Flattened: {flattened.count(chr(10)):,} lines")

    flattened = strip_preamble_comments(flattened)

    cleaned_path = output_dir / "cleaned.tex"
    cleaned_path.write_text(flattened, encoding="utf-8")
    print(f"  Cleaned TeX saved to: {cleaned_path}")

    # 5. Find and convert figures
    print("\n[4/5] Processing figures...")
    figures = find_figures_in_tex(flattened, source_dir)
    print(f"  Found {len(figures)} figure references")

    figures_b64 = {}
    for ref, path in figures.items():
        print(f"  Converting: {ref} ({path.name}) ... ", end="", flush=True)
        data_uri = convert_to_base64_png(path)
        if data_uri:
            figures_b64[ref] = data_uri
            print(f"OK ({len(data_uri):,} chars)")
        else:
            print("SKIPPED")

    figures_path = output_dir / "figures.json"
    with open(figures_path, "w", encoding="utf-8") as f:
        json.dump(figures_b64, f, ensure_ascii=False)
    print(f"  Figures saved to: {figures_path} ({len(figures_b64)} converted, {len(figures) - len(figures_b64)} skipped)")

    # 6. Save metadata
    print("\n[5/5] Saving metadata...")
    metadata_path = output_dir / "metadata.json"
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    print(f"  Metadata saved to: {metadata_path}")

    # 7. Summary
    print(f"\n{'='*60}")
    print(f"Preprocessing complete!")
    print(f"  Output: {output_dir}")
    print(f"  Files: metadata.json, cleaned.tex, figures.json, source/")
    print(f"  Figures: {len(figures_b64)}/{len(figures)} converted")
    print(f"{'='*60}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
