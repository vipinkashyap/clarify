"""FastAPI reading server. Serves already-cached papers — never calls an LLM."""

from __future__ import annotations

from pathlib import Path

import html as _html

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from clarify import cache
from clarify.cache import cache_dir
from clarify.render import render_paper


STATIC_DIR = Path(__file__).parent / "static"
FIGURES_DIR = cache_dir() / "figures"

app = FastAPI(title="Clarify")


TYPE_LABELS = {
    "empirical_result": "Empirical",
    "methodological_claim": "Methodological",
    "theoretical_claim": "Theoretical",
    "background_claim": "Background",
    "limitation": "Limitation",
}
TYPE_ORDER = list(TYPE_LABELS.keys())


def _paper_card(paper: "cache.Paper") -> str:  # noqa: F821
    arxiv_id = _html.escape(paper.arxiv_id)
    title = _html.escape(paper.title)
    authors = paper.authors or []
    author_text = ", ".join(_html.escape(a) for a in authors[:3])
    if len(authors) > 3:
        author_text += f", <span class=\"et-al\">+{len(authors) - 3}</span>"

    # Type-mix chip row
    by_type: dict[str, int] = {}
    for c in paper.claims:
        by_type[c.type.value] = by_type.get(c.type.value, 0) + 1
    chips = []
    for key in TYPE_ORDER:
        if key in by_type:
            chips.append(
                f'<span class="chip claim-{key}" title="{_html.escape(TYPE_LABELS[key])}">'
                f'{by_type[key]}</span>'
            )
    chips_html = "".join(chips) if chips else (
        '<span class="chip chip-empty">no claims ingested yet</span>'
    )

    # Hero excerpt — first empirical or methodological claim's plain version
    hero = ""
    for c in paper.claims:
        if c.plain_language and c.type.value in ("empirical_result", "methodological_claim"):
            hero = c.plain_language
            break
    if not hero:
        for c in paper.claims:
            if c.plain_language:
                hero = c.plain_language
                break

    hero_html = (
        f'<blockquote class="card-hero">{_html.escape(hero)}</blockquote>'
        if hero
        else ""
    )

    return f"""
<a class="paper-card" href="/paper/{arxiv_id}">
  <div class="card-id">{arxiv_id}</div>
  <h2 class="card-title">{title}</h2>
  <div class="card-authors">{author_text}</div>
  {hero_html}
  <div class="card-foot">
    <div class="card-chips">{chips_html}</div>
    <span class="card-cta">Read →</span>
  </div>
</a>
""".strip()


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    rows = cache.list_papers()
    papers = [cache.get_paper(r["arxiv_id"]) for r in rows]
    papers = [p for p in papers if p is not None]
    papers.sort(key=lambda p: (-len(p.claims), p.title))

    if papers:
        cards = "\n".join(_paper_card(p) for p in papers)
        listing = f'<div class="paper-grid">{cards}</div>'
    else:
        listing = '<p class="empty">No papers ingested yet.</p>'

    return HTMLResponse(f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><title>Clarify</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="/static/reader.css">
</head><body class="index">
<header>
  <span class="brand">Clarify</span>
  <span class="title">A reading overlay for arxiv papers</span>
  <span class="spacer"></span>
  <form action="/go" method="get" class="header-go">
    <input type="text" name="id" placeholder="Open by arxiv id" aria-label="arxiv id">
  </form>
</header>
<main>
  <section class="hero">
    <h1>Read papers<br><em>in plain English.</em></h1>
    <p class="lede">Clarify is a reading overlay for arxiv papers — it surfaces the load-bearing
      claims inline, with a plain-language rewrite for each one. Click a claim to see the evidence,
      the hedging, and what it builds on.</p>
  </section>
  {listing}
  <p class="hint">
    To add a paper: in Claude Code, run <code>clarify fetch &lt;id&gt;</code>,
    extract claims following <code>clarify/prompts/extract_claims.md</code>,
    then <code>clarify ingest &lt;id&gt; &lt;path&gt;</code>.
  </p>
</main>
</body></html>""")


@app.get("/go")
def go(id: str) -> RedirectResponse:
    return RedirectResponse(url=f"/paper/{id.strip()}", status_code=303)


@app.get("/paper/{arxiv_id}", response_class=HTMLResponse)
def reader(arxiv_id: str) -> HTMLResponse:
    paper = cache.get_paper(arxiv_id)
    if paper is None:
        body = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Not ingested — Clarify</title><link rel="stylesheet" href="/static/reader.css">
</head><body><header><a class="brand" href="/">Clarify</a></header>
<main><div class="error"><h2>Paper <code>{_html.escape(arxiv_id)}</code> not ingested</h2>
<p>{_ingest_hint(arxiv_id)}</p><p><a href="/">← All papers</a></p></div></main></body></html>"""
        return HTMLResponse(body, status_code=404)
    return HTMLResponse(render_paper(paper))


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/figures", StaticFiles(directory=FIGURES_DIR), name="figures")


def _ingest_hint(arxiv_id: str) -> str:
    safe = _html.escape(arxiv_id)
    return (
        f"In Claude Code: run <code>clarify fetch {safe}</code>, extract "
        f"claims following <code>clarify/prompts/extract_claims.md</code>, "
        f"then <code>clarify ingest {safe} &lt;claims_json&gt;</code>."
    )
