"""Pre-render the reader as a static site.

Produces:
  <dist>/index.html
  <dist>/p/<arxiv_id>.html
  <dist>/static/...            (copied from clarify/static)
  <dist>/figures/<id>/...      (copied from .cache/figures)

Reader pages are rewritten to use relative paths so the site is portable
across any static host (GitHub Pages, Netlify, Vercel, `python -m http.server`).
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Iterable

from clarify import cache
from clarify.render import render_index, render_paper


_PKG_STATIC = Path(__file__).parent / "static"


def _copy_tree(src: Path, dest: Path) -> int:
    if not src.exists():
        return 0
    dest.mkdir(parents=True, exist_ok=True)
    n = 0
    for entry in src.iterdir():
        target = dest / entry.name
        if entry.is_dir():
            n += _copy_tree(entry, target)
        else:
            shutil.copy2(entry, target)
            n += 1
    return n


def _rewrite_paper_html(html: str) -> str:
    """Rewrite absolute paths to relative for pages that live under /p/."""
    html = html.replace('href="/static/', 'href="../static/')
    html = html.replace('src="/static/', 'src="../static/')
    html = html.replace('src="/figures/', 'src="../figures/')
    # "Clarify" brand link and "← All" back link both point to "/"
    html = html.replace('href="/"', 'href="../index.html"')
    return html


def build(dist: Path, arxiv_ids: Iterable[str] | None = None) -> dict:
    dist = Path(dist).resolve()
    dist.mkdir(parents=True, exist_ok=True)

    # 1. Static assets (CSS, fonts, panel.js, lightbox.js)
    static_copied = _copy_tree(_PKG_STATIC, dist / "static")

    # 2. Figures (from the runtime cache)
    figures_src = cache.cache_dir() / "figures"
    figures_copied = _copy_tree(figures_src, dist / "figures")

    # 2b. Discover payload (committed; gallery loads it client-side)
    discover_src = Path(__file__).resolve().parents[1] / "docs" / "discover.json"
    if discover_src.exists():
        shutil.copy2(discover_src, dist / "discover.json")

    # 3. Paper pages
    rows = cache.list_papers()
    if arxiv_ids is not None:
        wanted = set(arxiv_ids)
        rows = [r for r in rows if r["arxiv_id"] in wanted]

    papers = [cache.get_paper(r["arxiv_id"]) for r in rows]
    papers = [p for p in papers if p is not None]
    papers.sort(key=lambda p: (-len(p.claims), p.title))

    (dist / "p").mkdir(exist_ok=True)
    pages_written = 0
    for paper in papers:
        html = render_paper(paper, css_href="/static/reader.css")
        html = _rewrite_paper_html(html)
        (dist / "p" / f"{paper.arxiv_id}.html").write_text(html, encoding="utf-8")
        pages_written += 1

    # 4. Gallery index
    index_html = render_index(
        papers,
        css_href="static/reader.css",
        paper_base="p/",
        show_header_form=False,
    )
    # Rewrite the "p/<id>" links to include ".html" for static serving.
    index_html = re.sub(
        r'href="p/([0-9]+\.[0-9]+(?:v\d+)?)"',
        r'href="p/\1.html"',
        index_html,
    )
    (dist / "index.html").write_text(index_html, encoding="utf-8")

    return {
        "dist": str(dist),
        "static": static_copied,
        "figures": figures_copied,
        "pages": pages_written,
        "papers": [p.arxiv_id for p in papers],
    }
