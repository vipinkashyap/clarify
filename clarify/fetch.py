"""Fetch arxiv papers — metadata + source (LaTeX tarball preferred, PDF fallback)."""

from __future__ import annotations

import gzip
import io
import re
import shutil
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

import arxiv
import httpx

from clarify.cache import cache_dir


USER_AGENT = "clarify-prototype/0.1 (https://localhost; research only)"


@dataclass
class FetchedSource:
    arxiv_id: str
    title: str
    authors: list[str]
    abstract: str
    source_dir: Path
    source_type: Literal["latex", "pdf"]
    main_tex: Optional[Path] = None
    pdf_path: Optional[Path] = None
    primary_category: Optional[str] = None
    categories: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.categories is None:
            self.categories = []


def _normalize_id(arxiv_id: str) -> str:
    # Strip version suffix for consistent caching; arxiv library handles either.
    return re.sub(r"v\d+$", "", arxiv_id.strip())


def _fetch_metadata(arxiv_id: str) -> arxiv.Result:
    client = arxiv.Client(page_size=1, delay_seconds=3, num_retries=3)
    search = arxiv.Search(id_list=[arxiv_id])
    results = list(client.results(search))
    if not results:
        raise ValueError(f"arxiv id {arxiv_id} not found")
    return results[0]


def _download_source(arxiv_id: str, dest: Path) -> Path:
    """Download the e-print (LaTeX) bundle. Returns path to the raw download."""
    url = f"https://arxiv.org/e-print/{arxiv_id}"
    raw = dest / "source.raw"
    with httpx.Client(
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
        timeout=60.0,
    ) as client:
        r = client.get(url)
        r.raise_for_status()
    raw.write_bytes(r.content)
    return raw


def _extract_source(raw: Path, dest: Path) -> bool:
    """Try to extract raw download as tar.gz or gzipped tex. Returns True on success."""
    data = raw.read_bytes()

    # Try gzip first
    try:
        decompressed = gzip.decompress(data)
    except OSError:
        decompressed = data

    # Try tarball
    try:
        with tarfile.open(fileobj=io.BytesIO(decompressed)) as tf:
            tf.extractall(dest, filter="data")
        return True
    except tarfile.TarError:
        pass

    # Single-file gzipped tex?
    if decompressed[:1] == b"\\" or b"\\documentclass" in decompressed[:4096]:
        (dest / "main.tex").write_bytes(decompressed)
        return True

    return False


def _find_main_tex(source_dir: Path) -> Optional[Path]:
    candidates: list[Path] = []
    for p in source_dir.rglob("*.tex"):
        try:
            head = p.read_text(errors="ignore")[:4096]
        except Exception:
            continue
        if r"\documentclass" in head:
            candidates.append(p)
    if not candidates:
        return None
    # Prefer names that look like main entry points.
    preferred = ("main.tex", "paper.tex", "ms.tex", "manuscript.tex")
    for name in preferred:
        for c in candidates:
            if c.name == name:
                return c
    # Largest is usually the main file.
    return max(candidates, key=lambda c: c.stat().st_size)


def _download_pdf(arxiv_id: str, dest: Path) -> Path:
    url = f"https://arxiv.org/pdf/{arxiv_id}"
    pdf = dest / f"{arxiv_id}.pdf"
    with httpx.Client(
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
        timeout=60.0,
    ) as client:
        r = client.get(url)
        r.raise_for_status()
    pdf.write_bytes(r.content)
    return pdf


def fetch_source(arxiv_id: str, force: bool = False) -> FetchedSource:
    """Acquire the paper source. Tries LaTeX bundle; falls back to PDF."""
    arxiv_id = _normalize_id(arxiv_id)
    meta = _fetch_metadata(arxiv_id)

    root = cache_dir() / "source" / arxiv_id
    if force and root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)

    main_tex: Optional[Path] = None
    pdf_path: Optional[Path] = None
    source_type: Literal["latex", "pdf"]

    # Try LaTeX bundle first
    try:
        raw = _download_source(arxiv_id, root)
        ok = _extract_source(raw, root)
        if ok:
            main_tex = _find_main_tex(root)
    except httpx.HTTPError:
        main_tex = None

    if main_tex is not None:
        source_type = "latex"
    else:
        pdf_path = _download_pdf(arxiv_id, root)
        source_type = "pdf"

    return FetchedSource(
        arxiv_id=arxiv_id,
        title=meta.title.strip(),
        authors=[a.name for a in meta.authors],
        abstract=meta.summary.strip(),
        source_dir=root,
        source_type=source_type,
        main_tex=main_tex,
        pdf_path=pdf_path,
        primary_category=getattr(meta, "primary_category", None),
        categories=list(getattr(meta, "categories", []) or []),
    )
