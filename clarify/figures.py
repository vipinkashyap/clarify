"""Figure extraction and conversion.

Scans a paper's parsed HTML for figure references (<img>, <embed>), locates
the source files in the arxiv bundle, converts non-web formats (PDF, EPS)
to PNG, copies everything to .cache/figures/<arxiv_id>/, and rewrites the
HTML srcs to point at the served paths.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from clarify.cache import cache_dir
from clarify.schema import Paper, Section


WEB_SAFE = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}
CONVERTIBLE = {".pdf", ".eps", ".ps"}

_PNG_DPI = 180  # render density for converted figures


def figures_dir(arxiv_id: str) -> Path:
    p = cache_dir() / "figures" / arxiv_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def _convert_pdf_to_png(src: Path, dest: Path) -> bool:
    """Render the first page of a PDF to a PNG via pymupdf."""
    try:
        import pymupdf
    except ImportError:
        return False
    try:
        doc = pymupdf.open(src)
        if not len(doc):
            return False
        page = doc[0]
        # Scale so the rendered page is ~DPI.
        zoom = _PNG_DPI / 72.0
        pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
        pix.save(dest)
        doc.close()
        return True
    except Exception:
        return False


def _convert_eps_to_png(src: Path, dest: Path) -> bool:
    """Render an EPS to PNG via ghostscript (`gs`)."""
    if shutil.which("gs") is None:
        return False
    try:
        result = subprocess.run(
            [
                "gs",
                "-q",
                "-dNOPAUSE",
                "-dBATCH",
                "-dSAFER",
                "-sDEVICE=png16m",
                f"-r{_PNG_DPI}",
                "-dEPSCrop",
                f"-sOutputFile={dest}",
                str(src),
            ],
            capture_output=True,
            timeout=30,
        )
        return result.returncode == 0 and dest.exists()
    except Exception:
        return False


def _resolve_source(src_ref: str, source_dir: Path) -> Optional[Path]:
    """Locate the file src_ref refers to inside the arxiv source bundle.

    src_ref may be a relative path without an extension (TeX convention) or
    with one. We search source_dir/<src_ref>, then extensions, then recursive.
    """
    direct = (source_dir / src_ref).resolve()
    if direct.exists() and direct.is_file():
        return direct
    # Try extension candidates when src_ref has none
    if not Path(src_ref).suffix:
        for ext in (".png", ".jpg", ".jpeg", ".pdf", ".eps", ".gif", ".svg"):
            c = (source_dir / (src_ref + ext)).resolve()
            if c.exists() and c.is_file():
                return c
    # Fall back to a recursive search by basename
    base = Path(src_ref).name
    for candidate in source_dir.rglob(base):
        if candidate.is_file():
            return candidate
    # Try basename without extension
    stem = Path(src_ref).stem
    for candidate in source_dir.rglob(f"{stem}.*"):
        if candidate.is_file() and candidate.suffix.lower() in WEB_SAFE | CONVERTIBLE:
            return candidate
    return None


def _prepare_figure(src_ref: str, source_dir: Path, out_dir: Path) -> Optional[str]:
    """Ensure a web-safe copy of the figure exists in out_dir.

    Returns the basename of the file in out_dir, or None on failure.
    """
    found = _resolve_source(src_ref, source_dir)
    if found is None:
        return None

    suffix = found.suffix.lower()
    if suffix in WEB_SAFE:
        dest = out_dir / found.name
        if not dest.exists():
            shutil.copy2(found, dest)
        return dest.name

    if suffix in CONVERTIBLE:
        dest = out_dir / (found.stem + ".png")
        if dest.exists():
            return dest.name
        ok = False
        if suffix == ".pdf":
            ok = _convert_pdf_to_png(found, dest)
        elif suffix in (".eps", ".ps"):
            ok = _convert_eps_to_png(found, dest)
        return dest.name if ok else None

    return None


_IMG_TAG = re.compile(r'<(img|embed)\b([^>]*?)\bsrc="([^"]+)"([^>]*)>', re.IGNORECASE)


def _rewrite_section_html(
    html: str, source_dir: Path, out_dir: Path, arxiv_id: str
) -> str:
    """Replace <img>/<embed> srcs with served paths; convert <embed> → <img>."""

    def replace(m: re.Match[str]) -> str:
        pre_attrs = m.group(2) or ""
        src = m.group(3)
        post_attrs = m.group(4) or ""
        if src.startswith(("http://", "https://", "/static/", "/figures/")):
            return m.group(0)
        name = _prepare_figure(src, source_dir, out_dir)
        if name is None:
            # leave original; browser will show the broken-image placeholder,
            # which is at least honest about the miss.
            return m.group(0)
        new_src = f"/figures/{arxiv_id}/{name}"
        # Always render as <img>, even for former <embed>s (browsers can't
        # display PDFs inline reliably).
        attrs = (pre_attrs + post_attrs).strip()
        attrs = re.sub(r'\bstyle="[^"]*"', "", attrs).strip()
        attrs = re.sub(r"\s+", " ", attrs)
        return f'<img src="{new_src}" loading="lazy" {attrs}>'.replace(" >", ">")

    return _IMG_TAG.sub(replace, html)


def prepare_paper_figures(paper: Paper, source_dir: Path) -> Paper:
    """Copy/convert all figures referenced in paper.sections; return paper
    with rewritten section.html src attributes.

    Idempotent: re-running uses already-extracted files.
    """
    out_dir = figures_dir(paper.arxiv_id)
    new_sections: list[Section] = []
    for s in paper.sections:
        new_html = _rewrite_section_html(s.html, source_dir, out_dir, paper.arxiv_id)
        new_sections.append(
            Section(title=s.title, level=s.level, text=s.text, html=new_html)
        )
    paper.sections = new_sections
    return paper
