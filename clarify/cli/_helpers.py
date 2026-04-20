"""Shared helpers for CLI subcommands."""

from __future__ import annotations

from pathlib import Path

from clarify import fetch as fetch_mod, parse as parse_mod
from clarify.fetch import FetchedSource
from clarify.schema import Paper


def parse_with_pdf_fallback(src: FetchedSource) -> Paper:
    """Run parse.parse(src); on a pandoc-only failure, fall back to PDF.

    Several arxiv sources use custom LaTeX macros pandoc rejects (e.g.
    ResNet's \\newcolumntype). Both `clarify fetch` and `clarify bootstrap`
    handle that the same way — re-download the PDF and retry — so the
    handler lives here once.
    """
    try:
        return parse_mod.parse(src)
    except RuntimeError as e:
        if src.source_type == "latex" and "pandoc" in str(e).lower():
            src.pdf_path = fetch_mod._download_pdf(src.arxiv_id, src.source_dir)
            src.main_tex = None
            src.source_type = "pdf"
            return parse_mod.parse(src)
        raise


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]
