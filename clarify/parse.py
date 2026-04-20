"""Convert fetched source (LaTeX or PDF) into a Paper with sections."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup, Tag

from clarify.fetch import FetchedSource
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
        body_html = "".join(str(c) for c in sec.children)
        text = sec.get_text(" ", strip=True)
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


def parse_pdf(src: FetchedSource) -> Paper:
    assert src.pdf_path is not None
    import pymupdf  # local import — heavy

    doc = pymupdf.open(src.pdf_path)
    sections: list[Section] = []
    current_title = "Body"
    current_level = 1
    buf: list[str] = []

    def flush() -> None:
        if not buf:
            return
        text = "\n".join(buf).strip()
        if not text:
            return
        html_body = "".join(f"<p>{_escape(p)}</p>" for p in text.split("\n\n") if p.strip())
        sections.append(
            Section(title=current_title, level=current_level, text=text, html=html_body)
        )
        buf.clear()

    for page in doc:
        blocks = page.get_text("blocks")
        blocks.sort(key=lambda b: (b[1], b[0]))  # top-to-bottom, left-to-right
        for _x0, _y0, _x1, _y1, text, *_rest in blocks:
            line = text.strip()
            if not line:
                continue
            # Heuristic heading: short, no terminal period, mostly capitalized-ish.
            if (
                len(line) < 80
                and "\n" not in line
                and not line.endswith(".")
                and sum(1 for c in line if c.isupper()) >= 2
                and line[0].isalpha()
            ):
                flush()
                current_title = line
                current_level = 2
                continue
            buf.append(line)
    flush()

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
        return parse_latex(src)
    return parse_pdf(src)
