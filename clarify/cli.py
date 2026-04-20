"""Clarify CLI — invoked by Claude Code during extraction."""

from __future__ import annotations

from pathlib import Path

import typer

from clarify import (
    cache,
    extract as extract_mod,
    fetch as fetch_mod,
    ingest as ingest_mod,
    parse as parse_mod,
)


app = typer.Typer(
    add_completion=False,
    help="Clarify — single-paper claim extractor + reading overlay.",
    no_args_is_help=True,
)


@app.command()
def fetch(
    arxiv_id: str = typer.Argument(..., help="arxiv id, e.g. 2301.12345"),
    force: bool = typer.Option(False, "--force", help="Re-download source."),
    pdf: bool = typer.Option(False, "--pdf", help="Force PDF extraction instead of LaTeX."),
) -> None:
    """Download and parse an arxiv paper into .cache/parsed/<id>.json.

    If pandoc chokes on the LaTeX source (custom macros, unsupported
    packages), automatically falls back to PDF extraction and retries.
    """
    typer.echo(f"Fetching {arxiv_id}…")
    src = fetch_mod.fetch_source(arxiv_id, force=force)
    if pdf:
        src.main_tex = None  # force PDF path
        src.source_type = "pdf"
        if src.pdf_path is None:
            src.pdf_path = fetch_mod._download_pdf(arxiv_id, src.source_dir)
    typer.echo(f"  source_type: {src.source_type}")
    typer.echo(f"  title: {src.title}")
    typer.echo("Parsing…")
    try:
        paper = parse_mod.parse(src)
    except RuntimeError as e:
        if src.source_type == "latex" and "pandoc" in str(e).lower():
            typer.echo("  pandoc rejected the LaTeX source; falling back to PDF…")
            src.pdf_path = fetch_mod._download_pdf(arxiv_id, src.source_dir)
            src.main_tex = None
            src.source_type = "pdf"
            paper = parse_mod.parse(src)
        else:
            raise
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


@app.command()
def bootstrap(
    force_fetch: bool = typer.Option(
        False, "--refetch", help="Re-download and re-parse every paper."
    ),
) -> None:
    """Fetch + ingest every paper in extractions/ so a fresh clone is ready to read.

    Walks `extractions/*.json`, and for each one runs `fetch` if the paper
    isn't already parsed, then runs `build-claims` to resolve offsets and
    ingest into the local reading cache.
    """
    ROOT = Path(__file__).resolve().parents[1]
    ext_dir = ROOT / "extractions"
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
                try:
                    paper = parse_mod.parse(src)
                except RuntimeError as e:
                    if src.source_type == "latex" and "pandoc" in str(e).lower():
                        src.pdf_path = fetch_mod._download_pdf(arxiv_id, src.source_dir)
                        src.main_tex = None
                        src.source_type = "pdf"
                        paper = parse_mod.parse(src)
                    else:
                        raise
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
            typer.echo(
                f"  ingested: {len(paper.claims)} claims, "
                f"{n_plain} with plain-language"
                + (f"  [{len(misses)} passage miss]" if misses else "")
            )
        except Exception as e:
            typer.echo(f"  !! build/ingest failed: {e}", err=True)

    typer.echo("\nDone. Reader at http://localhost:8000")


@app.command("build-claims")
def build_claims(
    arxiv_id: str = typer.Argument(..., help="arxiv id, e.g. 2301.12345"),
    draft_json: Path = typer.Argument(
        ..., exists=True, readable=True, help="Draft JSON produced by Claude Code."
    ),
    auto_ingest: bool = typer.Option(
        True,
        "--ingest/--no-ingest",
        help="Also ingest the produced JSON into the reading cache.",
    ),
) -> None:
    """Resolve a draft's passages to char offsets and write claim + plain JSON.

    The draft format matches what the `clarify-extract` Claude Code skill
    produces: a list of claims with `passage` strings (rather than
    char_start / char_end). This command locates each passage in the parsed
    paper and fills in the offsets, producing the two cache files the reader
    needs, and (by default) ingests them.
    """
    claims_path, plain_path, misses = extract_mod.build_from_draft(draft_json)
    typer.echo(f"Wrote {claims_path}")
    typer.echo(f"Wrote {plain_path}")
    for m in misses:
        typer.echo(f"  ! {m}")
    if misses:
        typer.echo(
            f"\n{len(misses)} claim(s) skipped — check the passage strings "
            f"match the parsed section text.",
            err=True,
        )

    if auto_ingest:
        paper = ingest_mod.ingest_claims(arxiv_id, claims_path)
        typer.echo(f"Ingested {arxiv_id}: {len(paper.claims)} claims.")
        if plain_path.exists():
            paper = ingest_mod.ingest_plain(arxiv_id, plain_path)
            n = sum(1 for c in paper.claims if c.plain_language)
            typer.echo(f"Added plain-language: {n}/{len(paper.claims)}")


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
def prompt(arxiv_id: str = typer.Argument(...)) -> None:
    """Emit a chat-ready extraction prompt for users without Claude Code.

    Assembles clarify/prompts/extract_claims.md + the parsed paper sections
    into one message you can paste into claude.ai / ChatGPT / Gemini. Pipe
    into pbcopy (macOS) or xclip (Linux) or redirect to a file.
    """
    ROOT = Path(__file__).resolve().parents[1]
    parsed = cache.load_parsed(arxiv_id)
    if parsed is None:
        typer.echo(
            f"No parsed paper for {arxiv_id}. Run `clarify fetch {arxiv_id}` first.",
            err=True,
        )
        raise typer.Exit(code=1)

    spec_path = ROOT / "clarify" / "prompts" / "extract_claims.md"
    spec = spec_path.read_text() if spec_path.exists() else ""

    lines = [
        f"# Task: extract claims from arxiv:{arxiv_id}",
        "",
        "Please follow the instructions below and produce a single JSON object",
        "with the shape expected by Clarify. Output only the JSON — no prose.",
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
        lines.append(f"### {s.title}")
        lines.append("")
        lines.append(s.text)
        lines.append("")

    lines.extend(
        [
            "## Output",
            "",
            "Return ONLY a JSON object with this shape (no markdown fence, no prose):",
            "",
            "```json",
            '{"arxiv_id": "'
            + arxiv_id
            + '", "claims": [{"id":"intro-01","statement":"…","type":"empirical_result","hedging":"asserted","section":"Introduction","passage":"<verbatim substring of the section text>","evidence":null,"dependencies":[],"plain_language":"…"}, …]}',
            "```",
        ]
    )
    typer.echo("\n".join(lines))


@app.command()
def stats(
    markdown: bool = typer.Option(False, "--markdown", help="Emit docs/coverage.md-ready markdown."),
) -> None:
    """Summarise paper, claim, and (where available) eval coverage.

    Counts come from extractions/ + the local reading cache. Eval numbers
    come from eval/annotations/ matched against eval/generated/.
    """
    ROOT = Path(__file__).resolve().parents[1]
    ext_dir = ROOT / "extractions"
    eval_ann = ROOT / "eval" / "annotations"
    eval_gen = ROOT / "eval" / "generated"

    papers = []
    total_claims = 0
    type_totals: dict[str, int] = {}
    n_with_plain = 0

    for draft_path in sorted(ext_dir.glob("*.json")) if ext_dir.exists() else []:
        try:
            import json as _json
            draft = _json.loads(draft_path.read_text())
        except Exception:
            continue
        arxiv_id = draft.get("arxiv_id", draft_path.stem)
        claims = draft.get("claims", [])
        plain_claims = sum(1 for c in claims if c.get("plain_language"))
        if plain_claims:
            n_with_plain += 1
        total_claims += len(claims)
        for c in claims:
            t = c.get("type", "unknown")
            type_totals[t] = type_totals.get(t, 0) + 1

        cached = cache.get_paper(arxiv_id)
        title = cached.title if cached else "(not yet ingested)"
        source = cached.source_type if cached else "-"

        # Eval pair?
        eval_pr: Optional[tuple[float, float]] = None
        ann_path = eval_ann / f"{arxiv_id}.json"
        gen_path = eval_gen / f"{arxiv_id}.json"
        if ann_path.exists() and gen_path.exists():
            try:
                import sys
                sys.path.insert(0, str(ROOT / "eval"))
                from run_eval import evaluate_paper  # type: ignore
                r = evaluate_paper(arxiv_id)
                if "precision" in r:
                    eval_pr = (r["precision"], r["recall"])
            except Exception:
                pass

        papers.append(
            {
                "arxiv_id": arxiv_id,
                "title": title,
                "source": source,
                "n_claims": len(claims),
                "n_plain": plain_claims,
                "pr": eval_pr,
            }
        )

    if markdown:
        lines = [
            "# Coverage",
            "",
            f"- **{len(papers)}** papers extracted",
            f"- **{total_claims}** claims total",
            f"- **{n_with_plain}/{len(papers)}** papers with plain-language rewrites",
            "",
        ]
        if type_totals:
            lines.append("## Claims by type")
            lines.append("")
            TYPE_LABELS = {
                "empirical_result": "Empirical",
                "methodological_claim": "Methodological",
                "theoretical_claim": "Theoretical",
                "background_claim": "Background",
                "limitation": "Limitation",
            }
            for t, n in sorted(type_totals.items(), key=lambda kv: -kv[1]):
                lines.append(f"- {TYPE_LABELS.get(t, t)}: {n}")
            lines.append("")
        lines.append("## Papers")
        lines.append("")
        lines.append("| arxiv id | title | claims | plain | P | R |")
        lines.append("|---|---|---:|---:|---:|---:|")
        for p in papers:
            pr = p["pr"]
            p_s = f"{pr[0]:.0%}" if pr else "—"
            r_s = f"{pr[1]:.0%}" if pr else "—"
            title = p["title"][:60]
            lines.append(
                f"| `{p['arxiv_id']}` | {title} | {p['n_claims']} | "
                f"{p['n_plain']}/{p['n_claims']} | {p_s} | {r_s} |"
            )
        # Aggregate eval
        pairs = [p["pr"] for p in papers if p["pr"]]
        if pairs:
            avg_p = sum(x[0] for x in pairs) / len(pairs)
            avg_r = sum(x[1] for x in pairs) / len(pairs)
            lines.append("")
            lines.append(
                f"Aggregate eval across {len(pairs)} annotated papers: "
                f"**P {avg_p:.1%} · R {avg_r:.1%}**."
            )
        typer.echo("\n".join(lines))
        return

    # Plain text output
    typer.echo(f"Papers:     {len(papers)}")
    typer.echo(f"Claims:     {total_claims}")
    typer.echo(f"With plain: {n_with_plain}/{len(papers)}")
    if type_totals:
        typer.echo("")
        for t in (
            "empirical_result",
            "methodological_claim",
            "theoretical_claim",
            "background_claim",
            "limitation",
        ):
            if t in type_totals:
                typer.echo(f"  {t:>22}: {type_totals[t]:>4}")
    typer.echo("")
    typer.echo(
        f"{'arxiv_id':>12}  {'claims':>6}  {'plain':>7}  {'P':>5}  {'R':>5}  title"
    )
    typer.echo("-" * 78)
    for p in papers:
        pr = p["pr"]
        p_s = f"{pr[0]:>5.1%}" if pr else f"{'—':>5}"
        r_s = f"{pr[1]:>5.1%}" if pr else f"{'—':>5}"
        typer.echo(
            f"{p['arxiv_id']:>12}  {p['n_claims']:>6}  "
            f"{p['n_plain']:>3}/{p['n_claims']:<3}  {p_s}  {r_s}  {p['title'][:40]}"
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
