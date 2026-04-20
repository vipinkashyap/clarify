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


CATEGORY_LABELS = {
    "cs.CL": "NLP",
    "cs.CV": "Vision",
    "cs.LG": "ML",
    "cs.AI": "AI",
    "cs.NE": "Neural",
    "stat.ML": "ML",
    "cs.RO": "Robotics",
    "cs.IR": "IR",
}


def _paper_card(paper: "cache.Paper", base_path: str = "/paper/") -> str:  # noqa: F821
    arxiv_id = _html.escape(paper.arxiv_id)
    title = _html.escape(paper.title)
    authors = paper.authors or []
    author_text = ", ".join(_html.escape(a) for a in authors[:3])
    if len(authors) > 3:
        author_text += f", <span class=\"et-al\">+{len(authors) - 3}</span>"

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
        '<span class="chip chip-empty">no claims yet</span>'
    )

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

    # Arxiv category badge
    cat = getattr(paper, "primary_category", None)
    cat_label = CATEGORY_LABELS.get(cat, cat) if cat else None
    cat_html = (
        f'<span class="card-cat" data-cat="{_html.escape(cat or "")}">'
        f'{_html.escape(cat_label or "")}</span>'
        if cat_label
        else ""
    )

    # Search haystack — lowercase string of everything we want to filter on.
    haystack_parts = [
        paper.arxiv_id,
        paper.title,
        " ".join(authors),
        cat or "",
        cat_label or "",
    ]
    haystack = " ".join(haystack_parts).lower()
    haystack = _html.escape(haystack, quote=True)

    return f"""
<a class="paper-card" href="{base_path}{arxiv_id}" data-search="{haystack}">
  <div class="card-meta">
    <span class="card-id">{arxiv_id}</span>
    {cat_html}
  </div>
  <h2 class="card-title">{title}</h2>
  <div class="card-authors">{author_text}</div>
  {hero_html}
  <div class="card-foot">
    <div class="card-chips">{chips_html}</div>
    <span class="card-cta">Read →</span>
  </div>
</a>
""".strip()


def render_index(
    papers: list,
    *,
    css_href: str = "/static/reader.css",
    paper_base: str = "/paper/",
    show_header_form: bool = True,
) -> str:
    """Render the gallery as a standalone HTML document.

    Used by both the runtime server and `clarify build-static`. `paper_base`
    is prefixed to each paper link so the same renderer works for the
    FastAPI route (`/paper/<id>`) and the static-site layout (`p/<id>.html`).
    """
    if papers:
        cards = "\n".join(_paper_card(p, base_path=paper_base) for p in papers)
        listing = f'<div class="paper-grid" id="paper-grid">{cards}</div>'
    else:
        listing = '<p class="empty">No papers ingested yet.</p>'

    header_form = (
        '<form action="/go" method="get" class="header-go">'
        '<input type="text" name="id" placeholder="Open by arxiv id" aria-label="arxiv id">'
        "</form>"
        if show_header_form
        else ""
    )

    search_block = (
        '<div class="search-row">'
        '<input type="search" id="search" class="search-input" '
        'placeholder="Search titles, authors, categories…" autocomplete="off" '
        'aria-label="filter papers">'
        '<div class="search-count" id="search-count" aria-live="polite"></div>'
        "</div>"
        if papers
        else ""
    )

    search_js = """
<script>
(() => {
  const input = document.getElementById('search');
  const grid = document.getElementById('paper-grid');
  const count = document.getElementById('search-count');
  if (!input || !grid) return;
  const cards = [...grid.querySelectorAll('.paper-card')];
  const total = cards.length;
  const updateCount = (n) => {
    if (!count) return;
    count.textContent = n === total ? '' : `${n} of ${total}`;
  };
  input.addEventListener('input', () => {
    const q = input.value.trim().toLowerCase();
    let visible = 0;
    for (const c of cards) {
      const hay = c.dataset.search || '';
      const match = !q || hay.includes(q);
      c.style.display = match ? '' : 'none';
      if (match) visible++;
    }
    updateCount(visible);
  });
})();
</script>
""".strip()

    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><title>Clarify</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="{css_href}">
</head><body class="index">
<header>
  <span class="brand">Clarify</span>
  <span class="title">A reading overlay for arxiv papers</span>
  <span class="spacer"></span>
  {header_form}
</header>
<main>
  <section class="hero">
    <h1>Read papers<br><em>in plain English.</em></h1>
    <p class="lede">Clarify is a reading overlay for arxiv papers — it surfaces the load-bearing
      claims inline, with a plain-language rewrite for each one. Click a claim to see the evidence,
      the hedging, and what it builds on.</p>
  </section>
  {search_block}
  {listing}
  <p class="hint">
    Add a paper: in Claude Code, say <em>"extract claims from &lt;arxiv id&gt;"</em>,
    or without Claude Code follow
    <a href="https://github.com">docs/extract-prompt.md</a>.
  </p>
</main>
{search_js}
</body></html>"""


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
