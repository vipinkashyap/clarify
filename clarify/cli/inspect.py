"""Inspection commands: list, info, stats."""

from __future__ import annotations

import json
import sys
from typing import Optional

import typer

from clarify import cache
from clarify.cli import app
from clarify.cli._helpers import project_root
from clarify.render import TYPE_LABELS


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
            f"{r['arxiv_id']:>14}  claims={r['num_claims']:>3}  "
            f"{r['source_type']:>5}  {plain:>5}  {r['title'][:60]}"
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


def _eval_pr(arxiv_id: str) -> Optional[tuple[float, float]]:
    """Return (precision, recall) for `arxiv_id` if both annotations + generated exist."""
    root = project_root()
    ann = root / "eval" / "annotations" / f"{arxiv_id}.json"
    gen = root / "eval" / "generated" / f"{arxiv_id}.json"
    if not (ann.exists() and gen.exists()):
        return None
    sys.path.insert(0, str(root / "eval"))
    try:
        from run_eval import evaluate_paper  # type: ignore
        r = evaluate_paper(arxiv_id)
        if "precision" in r:
            return (r["precision"], r["recall"])
    except Exception:
        return None
    return None


def _collect_stats() -> tuple[list[dict], int, dict[str, int], int]:
    """Walk extractions/ + cache and assemble per-paper rows + totals."""
    ext_dir = project_root() / "extractions"
    papers: list[dict] = []
    total_claims = 0
    type_totals: dict[str, int] = {}
    n_with_plain = 0

    if not ext_dir.exists():
        return papers, total_claims, type_totals, n_with_plain

    for draft_path in sorted(ext_dir.glob("*.json")):
        try:
            draft = json.loads(draft_path.read_text())
        except Exception:
            continue
        arxiv_id = draft.get("arxiv_id", draft_path.stem)
        claims = draft.get("claims", [])
        plain_count = sum(1 for c in claims if c.get("plain_language"))
        if plain_count:
            n_with_plain += 1
        total_claims += len(claims)
        for c in claims:
            t = c.get("type", "unknown")
            type_totals[t] = type_totals.get(t, 0) + 1

        cached = cache.get_paper(arxiv_id)
        papers.append(
            {
                "arxiv_id": arxiv_id,
                "title": cached.title if cached else "(not yet ingested)",
                "n_claims": len(claims),
                "n_plain": plain_count,
                "pr": _eval_pr(arxiv_id),
            }
        )
    return papers, total_claims, type_totals, n_with_plain


def _stats_markdown(papers, total_claims, type_totals, n_with_plain) -> str:
    lines = [
        "# Coverage",
        "",
        f"- **{len(papers)}** papers extracted",
        f"- **{total_claims}** claims total",
        f"- **{n_with_plain}/{len(papers)}** papers with plain-language rewrites",
        "",
    ]
    if type_totals:
        lines += ["## Claims by type", ""]
        for t, n in sorted(type_totals.items(), key=lambda kv: -kv[1]):
            lines.append(f"- {TYPE_LABELS.get(t, t)}: {n}")
        lines.append("")
    lines += [
        "## Papers",
        "",
        "| arxiv id | title | claims | plain | P | R |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for p in papers:
        pr = p["pr"]
        p_s = f"{pr[0]:.0%}" if pr else "—"
        r_s = f"{pr[1]:.0%}" if pr else "—"
        lines.append(
            f"| `{p['arxiv_id']}` | {p['title'][:60]} | {p['n_claims']} | "
            f"{p['n_plain']}/{p['n_claims']} | {p_s} | {r_s} |"
        )
    pairs = [p["pr"] for p in papers if p["pr"]]
    if pairs:
        avg_p = sum(x[0] for x in pairs) / len(pairs)
        avg_r = sum(x[1] for x in pairs) / len(pairs)
        lines += [
            "",
            f"Aggregate eval across {len(pairs)} annotated papers: "
            f"**P {avg_p:.1%} · R {avg_r:.1%}**.",
        ]
    return "\n".join(lines)


@app.command()
def stats(
    markdown: bool = typer.Option(
        False, "--markdown", help="Emit docs/coverage.md-ready markdown."
    ),
) -> None:
    """Summarise paper, claim, and (where available) eval coverage."""
    papers, total_claims, type_totals, n_with_plain = _collect_stats()

    if markdown:
        typer.echo(_stats_markdown(papers, total_claims, type_totals, n_with_plain))
        return

    typer.echo(f"Papers:     {len(papers)}")
    typer.echo(f"Claims:     {total_claims}")
    typer.echo(f"With plain: {n_with_plain}/{len(papers)}")
    if type_totals:
        typer.echo("")
        for t in TYPE_LABELS:  # respects display order
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
