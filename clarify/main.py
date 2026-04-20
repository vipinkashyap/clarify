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


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    rows = cache.list_papers()
    if rows:
        items = "\n".join(
            f'<li><a href="/paper/{_html.escape(r["arxiv_id"])}">{_html.escape(r["title"])}</a>'
            f'<span class="meta">{r["num_claims"]} claims · {r["source_type"]}</span></li>'
            for r in rows
        )
        listing = f'<ul class="papers">{items}</ul>'
    else:
        listing = '<p class="empty">No papers cached yet.</p>'

    return HTMLResponse(f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><title>Clarify</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="/static/reader.css">
</head><body class="index">
<header><span class="brand">Clarify</span><span class="spacer"></span></header>
<main>
  <h1>Clarify</h1>
  <p class="lede">A reading overlay for arxiv papers.</p>
  <form action="/go" method="get" class="go-form">
    <input type="text" name="id" placeholder="2301.12345" aria-label="arxiv id" autofocus>
    <button type="submit">Open</button>
  </form>
  <h2>Cached papers</h2>
  {listing}
  <p class="hint">Not listed? In Claude Code: <code>clarify fetch &lt;id&gt;</code>,
  extract claims following <code>clarify/prompts/extract_claims.md</code>,
  then <code>clarify ingest &lt;id&gt; &lt;path&gt;</code>.</p>
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
