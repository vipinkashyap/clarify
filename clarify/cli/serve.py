"""Pipeline + deploy commands: bootstrap, build-static."""

from __future__ import annotations

from pathlib import Path

import typer

from clarify import (
    cache,
    extract as extract_mod,
    fetch as fetch_mod,
    ingest as ingest_mod,
)
from clarify.cli import app
from clarify.cli._helpers import parse_with_pdf_fallback, project_root


@app.command()
def bootstrap(
    force_fetch: bool = typer.Option(
        False, "--refetch", help="Re-download and re-parse every paper."
    ),
) -> None:
    """Fetch + ingest every paper in extractions/ so a fresh clone is ready to read."""
    ext_dir = project_root() / "extractions"
    if not ext_dir.exists():
        typer.echo("No extractions/ directory; nothing to do.")
        return

    drafts = sorted(p for p in ext_dir.glob("*.json") if not p.name.startswith("_"))
    if not drafts:
        typer.echo("extractions/ is empty.")
        return

    for draft in drafts:
        arxiv_id = draft.stem
        typer.echo(f"\n── {arxiv_id} ──")
        parsed_path = cache.parsed_json_path(arxiv_id)
        if force_fetch or not parsed_path.exists():
            try:
                src = fetch_mod.fetch_source(arxiv_id, force=force_fetch)
                typer.echo(f"  fetched ({src.source_type})")
                paper = parse_with_pdf_fallback(src)
                cache.save_parsed(paper)
                typer.echo(f"  parsed ({len(paper.sections)} sections)")
            except Exception as e:
                typer.echo(f"  !! fetch/parse failed: {e}", err=True)
                continue
        else:
            typer.echo(f"  parsed already (.cache/parsed/{arxiv_id}.json)")

        try:
            claims_path, plain_path, misses = extract_mod.build_from_draft(draft)
            ingest_mod.ingest_claims(arxiv_id, claims_path)
            paper = ingest_mod.ingest_plain(arxiv_id, plain_path)
            n_plain = sum(1 for c in paper.claims if c.plain_language)
            tail = f"  [{len(misses)} passage miss]" if misses else ""
            typer.echo(
                f"  ingested: {len(paper.claims)} claims, {n_plain} with plain-language{tail}"
            )
        except Exception as e:
            typer.echo(f"  !! build/ingest failed: {e}", err=True)

    typer.echo("\nDone. Reader at http://localhost:8000")


@app.command("build-static")
def build_static(
    dist: Path = typer.Argument(
        Path("dist"), help="Output directory (e.g. dist/ or docs/ for GitHub Pages)."
    ),
) -> None:
    """Pre-render the reader as a static site for any static host.

    Writes index.html + p/<id>.html for every ingested paper, copies static/
    and figures/ alongside.
    """
    from clarify.build_static import build as _build

    result = _build(dist)
    typer.echo(f"Wrote {result['pages']} paper pages + index to {result['dist']}")
    typer.echo(
        f"  static assets: {result['static']} files · figures: {result['figures']} files"
    )
    typer.echo("\nPreview locally:")
    typer.echo(f"  python -m http.server --directory {result['dist']} 8001")
