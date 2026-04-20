"""Extraction commands: fetch, ingest, ingest-plain, build-claims, prompt."""

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
def fetch(
    arxiv_id: str = typer.Argument(..., help="arxiv id, e.g. 2301.12345"),
    force: bool = typer.Option(False, "--force", help="Re-download source."),
    pdf: bool = typer.Option(False, "--pdf", help="Force PDF extraction instead of LaTeX."),
) -> None:
    """Download and parse an arxiv paper into .cache/parsed/<id>.json.

    On pandoc errors, falls back to PDF extraction automatically.
    """
    typer.echo(f"Fetching {arxiv_id}…")
    src = fetch_mod.fetch_source(arxiv_id, force=force)
    if pdf:
        src.main_tex = None
        src.source_type = "pdf"
        if src.pdf_path is None:
            src.pdf_path = fetch_mod._download_pdf(arxiv_id, src.source_dir)
    typer.echo(f"  source_type: {src.source_type}")
    typer.echo(f"  title: {src.title}")
    typer.echo("Parsing…")
    paper = parse_with_pdf_fallback(src)
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
    typer.echo(
        f"Updated {arxiv_id}: {n}/{len(paper.claims)} claims have plain-language versions."
    )


@app.command("build-claims")
def build_claims(
    arxiv_id: str = typer.Argument(..., help="arxiv id, e.g. 2301.12345"),
    draft_json: Path = typer.Argument(
        ..., exists=True, readable=True, help="Draft JSON produced by Claude Code."
    ),
    auto_ingest: bool = typer.Option(
        True, "--ingest/--no-ingest", help="Also ingest into the reading cache."
    ),
) -> None:
    """Resolve a draft's passages to char offsets and write claim + plain JSON."""
    claims_path, plain_path, misses = extract_mod.build_from_draft(draft_json)
    typer.echo(f"Wrote {claims_path}")
    typer.echo(f"Wrote {plain_path}")
    for m in misses:
        typer.echo(f"  ! {m}")
    if misses:
        typer.echo(
            f"\n{len(misses)} claim(s) skipped — check passages match section text.",
            err=True,
        )
    if auto_ingest:
        paper = ingest_mod.ingest_claims(arxiv_id, claims_path)
        typer.echo(f"Ingested {arxiv_id}: {len(paper.claims)} claims.")
        if plain_path.exists():
            paper = ingest_mod.ingest_plain(arxiv_id, plain_path)
            n = sum(1 for c in paper.claims if c.plain_language)
            typer.echo(f"Added plain-language: {n}/{len(paper.claims)}")


@app.command()
def prompt(arxiv_id: str = typer.Argument(...)) -> None:
    """Emit a chat-ready extraction prompt for users without Claude Code.

    Assembles clarify/prompts/extract_claims.md + the parsed paper into one
    message you can paste into claude.ai / ChatGPT / Gemini. Pipe to pbcopy
    (macOS), xclip (Linux), or redirect to a file.
    """
    parsed = cache.load_parsed(arxiv_id)
    if parsed is None:
        typer.echo(
            f"No parsed paper for {arxiv_id}. Run `clarify fetch {arxiv_id}` first.",
            err=True,
        )
        raise typer.Exit(code=1)

    spec_path = project_root() / "clarify" / "prompts" / "extract_claims.md"
    spec = spec_path.read_text() if spec_path.exists() else ""

    parts = [
        f"# Task: extract claims from arxiv:{arxiv_id}",
        "",
        "Follow the instructions below and produce a single JSON object with",
        "the shape Clarify expects. Output only the JSON — no prose.",
        "",
        "## Instructions",
        "",
        spec,
        "",
        "## Paper",
        "",
        f"**arxiv_id**: {arxiv_id}",
        f"**title**: {parsed.title}",
        f"**authors**: {', '.join(parsed.authors)}",
        "",
        "### Abstract",
        "",
        parsed.abstract or "(no abstract)",
        "",
    ]
    for s in parsed.sections:
        parts.extend([f"### {s.title}", "", s.text, ""])

    parts.extend(
        [
            "## Output",
            "",
            "Return ONLY a JSON object (no markdown fence, no prose):",
            "",
            "```json",
            (
                f'{{"arxiv_id": "{arxiv_id}", "claims": ['
                '{"id":"intro-01","statement":"…","type":"empirical_result",'
                '"hedging":"asserted","section":"Introduction",'
                '"passage":"<verbatim substring of section text>",'
                '"evidence":null,"dependencies":[],"plain_language":"…"}, …]}'
            ),
            "```",
        ]
    )
    typer.echo("\n".join(parts))
