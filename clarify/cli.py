"""Clarify CLI — invoked by Claude Code during extraction."""

from __future__ import annotations

from pathlib import Path

import typer

from clarify import cache, fetch as fetch_mod, ingest as ingest_mod, parse as parse_mod


app = typer.Typer(
    add_completion=False,
    help="Clarify — single-paper claim extractor + reading overlay.",
    no_args_is_help=True,
)


@app.command()
def fetch(
    arxiv_id: str = typer.Argument(..., help="arxiv id, e.g. 2301.12345"),
    force: bool = typer.Option(False, "--force", help="Re-download source."),
) -> None:
    """Download and parse an arxiv paper into .cache/parsed/<id>.json."""
    typer.echo(f"Fetching {arxiv_id}…")
    src = fetch_mod.fetch_source(arxiv_id, force=force)
    typer.echo(f"  source_type: {src.source_type}")
    typer.echo(f"  title: {src.title}")
    typer.echo("Parsing…")
    paper = parse_mod.parse(src)
    out = cache.save_parsed(paper)
    typer.echo(f"Wrote {out} — {len(paper.sections)} sections.")


@app.command()
def ingest(
    arxiv_id: str = typer.Argument(...),
    claims_json: Path = typer.Argument(
        ..., exists=True, readable=True, help="Path to claims JSON produced by Claude Code."
    ),
) -> None:
    """Merge Claude-Code-produced claims into the parsed paper and save to SQLite."""
    paper = ingest_mod.ingest_claims(arxiv_id, claims_json)
    typer.echo(
        f"Ingested {arxiv_id}: {len(paper.claims)} claims across {len(paper.sections)} sections."
    )


@app.command("ingest-plain")
def ingest_plain(
    arxiv_id: str = typer.Argument(...),
    plain_json: Path = typer.Argument(..., exists=True, readable=True),
) -> None:
    """Add plain-language versions to an already-ingested paper."""
    paper = ingest_mod.ingest_plain(arxiv_id, plain_json)
    n = sum(1 for c in paper.claims if c.plain_language)
    typer.echo(f"Updated {arxiv_id}: {n}/{len(paper.claims)} claims have plain-language versions.")


@app.command("list")
def list_cmd() -> None:
    """List cached papers."""
    rows = cache.list_papers()
    if not rows:
        typer.echo("(no papers cached)")
        return
    for r in rows:
        plain = "plain" if r["has_plain"] else "—"
        typer.echo(
            f"{r['arxiv_id']:>14}  claims={r['num_claims']:>3}  {r['source_type']:>5}  {plain:>5}  {r['title'][:60]}"
        )


@app.command()
def info(arxiv_id: str = typer.Argument(...)) -> None:
    """Show details for one cached paper."""
    paper = cache.get_paper(arxiv_id)
    if paper is None:
        typer.echo(f"{arxiv_id} not in cache.")
        raise typer.Exit(code=1)
    typer.echo(f"arxiv_id:    {paper.arxiv_id}")
    typer.echo(f"title:       {paper.title}")
    typer.echo(f"authors:     {', '.join(paper.authors)}")
    typer.echo(f"source_type: {paper.source_type}")
    typer.echo(f"sections:    {len(paper.sections)}")
    typer.echo(f"claims:      {len(paper.claims)}")
    n_plain = sum(1 for c in paper.claims if c.plain_language)
    typer.echo(f"plain_lang:  {n_plain}/{len(paper.claims)}")
    by_type: dict[str, int] = {}
    for c in paper.claims:
        by_type[c.type.value] = by_type.get(c.type.value, 0) + 1
    for t, n in sorted(by_type.items()):
        typer.echo(f"  {t:>22}: {n}")


if __name__ == "__main__":
    app()
