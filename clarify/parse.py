"""Convert fetched source (LaTeX or PDF) into a Paper with sections."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup, Tag

from clarify.fetch import FetchedSource
from clarify.figures import prepare_paper_figures
from clarify.schema import Paper, Section


PANDOC_ARGS = [
    "--from=latex",
    "--to=html5",
    "--mathjax",  # leaves math as \(...\) / \[...\] — perfect for KaTeX
    "--wrap=none",
    "--section-divs",
    "--no-highlight",
]


class PandocMissing(RuntimeError):
    pass


def _run_pandoc(tex_path: Path, cwd: Path) -> str:
    if shutil.which("pandoc") is None:
        raise PandocMissing("pandoc is not installed; run `brew install pandoc`")
    result = subprocess.run(
        ["pandoc", *PANDOC_ARGS, str(tex_path)],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"pandoc failed (exit {result.returncode}):\n{result.stderr[:2000]}"
        )
    return result.stdout


def _sections_from_html(html: str) -> list[Section]:
    soup = BeautifulSoup(html, "lxml")
    # Pandoc with --section-divs wraps each section in <section> with a heading inside.
    top_sections = soup.find_all("section", recursive=True)

    out: list[Section] = []
    seen_bodies: set[int] = set()

    for sec in top_sections:
        # Only take sections whose immediate parent isn't another section (top-level)
        if sec.parent and sec.parent.name == "section":
            continue
        heading = sec.find(["h1", "h2", "h3", "h4", "h5", "h6"], recursive=True)
        if heading is None:
            continue
        level = int(heading.name[1])
        title = heading.get_text(" ", strip=True)
        # Exclude the heading from body_html — the renderer adds its own.
        body_html = "".join(
            str(c) for c in sec.children if c is not heading
        )
        text_parts = []
        for c in sec.children:
            if c is heading:
                continue
            text_parts.append(
                c.get_text(" ", strip=True) if isinstance(c, Tag) else str(c).strip()
            )
        text = " ".join(t for t in text_parts if t)
        # Avoid duplicate if a nested section was already captured above (it won't be, but guard anyway)
        fingerprint = id(sec)
        if fingerprint in seen_bodies:
            continue
        seen_bodies.add(fingerprint)
        out.append(Section(title=title, level=level, text=text, html=body_html))

    if not out:
        # No section divs — fall back to a single pseudo-section.
        body = soup.body or soup
        out.append(
            Section(
                title="Body",
                level=1,
                text=body.get_text(" ", strip=True),
                html=str(body),
            )
        )
    return out


def _extract_title_authors_abstract_from_html(
    html: str,
) -> tuple[Optional[str], list[str], Optional[str]]:
    """Best-effort extraction of abstract from pandoc-rendered HTML."""
    soup = BeautifulSoup(html, "lxml")
    abstract = None
    for div in soup.find_all(["div", "section"]):
        cls = div.get("class") or []
        if "abstract" in cls:
            abstract = div.get_text(" ", strip=True)
            # remove "Abstract" heading prefix if present
            if abstract.lower().startswith("abstract"):
                abstract = abstract[len("abstract") :].strip(" :.\n")
            break
    return None, [], abstract


def parse_latex(src: FetchedSource) -> Paper:
    assert src.main_tex is not None
    html = _run_pandoc(src.main_tex, cwd=src.main_tex.parent)
    sections = _sections_from_html(html)
    _, _, abstract_from_html = _extract_title_authors_abstract_from_html(html)
    # Drop an "abstract" section if pandoc promoted it — we store it separately.
    sections = [s for s in sections if s.title.strip().lower() != "abstract"]
    return Paper(
        arxiv_id=src.arxiv_id,
        title=src.title,
        authors=src.authors,
        abstract=abstract_from_html or src.abstract,
        sections=sections,
        source_type="latex",
    )


_PAGE_NOISE = re.compile(
    r"^(arxiv:|©|doi:|\s*\d{1,3}\s*$|\s*page\s+\d+|figure\s+\d+|table\s+\d+)",
    re.IGNORECASE,
)


def _dominant_font_size(doc) -> float:
    """Return the body-text font size — the most ink-weighted size in the doc."""
    size_chars: dict[float, int] = {}
    for page in doc:
        d = page.get_text("dict")
        for block in d.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block["lines"]:
                for span in line["spans"]:
                    sz = round(span["size"], 1)
                    size_chars[sz] = size_chars.get(sz, 0) + len(span["text"])
    return max(size_chars, key=size_chars.get) if size_chars else 10.0


def _looks_like_heading(text: str, size: float, body: float) -> bool:
    if len(text) < 2 or len(text) > 110:
        return False
    if _PAGE_NOISE.match(text):
        return False
    if text.endswith((".", ",", ":", ";")):
        return False
    first = text[0]
    if not (first.isalpha() or first.isdigit()):
        return False
    # Must be visibly larger than body.
    return size >= body * 1.15


def _heading_level(size: float, body: float) -> int:
    if size >= body * 1.6:
        return 1
    if size >= body * 1.18:
        return 2
    return 3


def parse_pdf(src: FetchedSource) -> Paper:
    """Font-size-aware PDF parsing.

    We estimate the body font size as the most ink-weighted size in the
    document, then treat anything noticeably larger (≥1.15×) as a heading,
    subject to some tells (no trailing punct, not a page-noise string,
    reasonable length).

    pymupdf's `get_text('dict')` returns blocks in reading order, so we
    get column-aware traversal for free on two-column papers.
    """
    assert src.pdf_path is not None
    import pymupdf

    doc = pymupdf.open(src.pdf_path)
    body_size = _dominant_font_size(doc)

    sections: list[Section] = []
    current_title = "Body"
    current_level = 1
    buf: list[str] = []
    seen_heading = False

    def flush() -> None:
        if not buf:
            return
        text = "\n".join(buf).strip()
        if not text:
            buf.clear()
            return
        paras = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
        html_body = "".join(f"<p>{_escape(p)}</p>" for p in paras)
        sections.append(
            Section(title=current_title, level=current_level, text=text, html=html_body)
        )
        buf.clear()

    for page in doc:
        d = page.get_text("dict")
        for block in d.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block["lines"]:
                # A line may mix sizes; use the max span size as "this line's".
                spans = [s for s in line["spans"] if s["text"].strip()]
                if not spans:
                    continue
                line_text = "".join(s["text"] for s in spans).strip()
                if not line_text:
                    continue
                line_size = max(round(s["size"], 1) for s in spans)

                if _looks_like_heading(line_text, line_size, body_size):
                    flush()
                    current_title = line_text
                    current_level = _heading_level(line_size, body_size)
                    seen_heading = True
                    continue

                if _PAGE_NOISE.match(line_text):
                    continue
                buf.append(line_text)
            # blank line between blocks helps paragraph splitting
            if buf and buf[-1] != "":
                buf.append("")
    flush()

    # Drop a trailing empty body if we never hit a heading (rare).
    sections = [s for s in sections if s.text]

    return Paper(
        arxiv_id=src.arxiv_id,
        title=src.title,
        authors=src.authors,
        abstract=src.abstract,
        sections=sections,
        source_type="pdf",
    )


def _escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def parse(src: FetchedSource) -> Paper:
    if src.source_type == "latex":
        paper = parse_latex(src)
    else:
        paper = parse_pdf(src)
    # Copy/convert figures out of the arxiv bundle and rewrite the srcs.
    # (For PDF-fallback parses this is a no-op — parse_pdf emits no images.)
    paper = prepare_paper_figures(paper, src.source_dir)
    return paper
