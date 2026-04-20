"""FastAPI reading server. Serves already-cached papers — never calls an LLM.

Templating lives in `clarify.render`. This module is just routes + mounts.
"""

from __future__ import annotations

import html as _html
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from clarify import cache
from clarify.cache import cache_dir
from clarify.render import render_index, render_paper


STATIC_DIR = Path(__file__).parent / "static"
FIGURES_DIR = cache_dir() / "figures"

app = FastAPI(title="Clarify")


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    rows = cache.list_papers()
    papers = [cache.get_paper(r["arxiv_id"]) for r in rows]
    papers = [p for p in papers if p is not None]
    papers.sort(key=lambda p: (-len(p.claims), p.title))
    return HTMLResponse(render_index(papers))


@app.get("/go")
def go(id: str) -> RedirectResponse:
    return RedirectResponse(url=f"/paper/{id.strip()}", status_code=303)


@app.get("/paper/{arxiv_id}", response_class=HTMLResponse)
def reader(arxiv_id: str) -> HTMLResponse:
    paper = cache.get_paper(arxiv_id)
    if paper is None:
        return HTMLResponse(_not_ingested_page(arxiv_id), status_code=404)
    return HTMLResponse(render_paper(paper))


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/figures", StaticFiles(directory=FIGURES_DIR), name="figures")


def _not_ingested_page(arxiv_id: str) -> str:
    safe = _html.escape(arxiv_id)
    hint = (
        f"In Claude Code: <code>clarify fetch {safe}</code>, extract claims "
        f"following <code>clarify/prompts/extract_claims.md</code>, then "
        f"<code>clarify ingest {safe} &lt;claims_json&gt;</code>."
    )
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Not ingested — Clarify</title>
<link rel="stylesheet" href="/static/reader.css">
</head><body><header><a class="brand" href="/">Clarify</a></header>
<main><div class="error"><h2>Paper <code>{safe}</code> not ingested</h2>
<p>{hint}</p><p><a href="/">← All papers</a></p></div></main></body></html>"""
