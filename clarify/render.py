"""Server-side rendering: Paper → full HTML document.

Client-side JavaScript is limited to two narrow responsibilities:
  • KaTeX paints math (doing this in pure HTML would mean MathML, whose
    quality varies across browsers — the spec explicitly calls for KaTeX).
  • panel.js drives the claim-detail side panel (click a tinted claim →
    panel slides in with type, evidence, hedging, dependencies, plain
    version). A pure-CSS `:target` version would require a hidden panel
    per claim and bloat the HTML; ~60 lines of JS is cleaner.

The reading view itself (body, typography, claim annotations, Plain/
Original toggle) is pure HTML + CSS.

Claim annotations: for each claim we locate its verbatim passage
(section.text[char_start:char_end]) inside the section's rendered HTML,
extend the match to respect tag balance and absorb a trailing "." / ",",
and wrap it in a <span class="claim claim-{type}"> that carries both the
original passage and (if available) a plain-language rewrite.

The Original / Plain toggle is a pair of hidden radio inputs rendered
above the <header>; CSS sibling selectors swap the two variants.
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString

from clarify.schema import Claim, FigureGloss, Paper


KATEX_VERSION = "0.16.11"

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


def _esc(s: str) -> str:
    return html.escape(s, quote=True)


def _section_id(title: str, idx: int) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return f"sec-{idx}-{slug}" if slug else f"sec-{idx}"


# ── Claim annotation ──────────────────────────────────────────────────────
#
# We wrap the verbatim passage in section.html with an annotation span.
# Matching is tolerant: the passage has already been verified against
# section.text (plain), but section.html may contain intervening inline
# tags (e.g. pandoc's <a> wrappers around citation numbers) or minor
# whitespace differences. We build a regex that allows any sequence of
# whitespace and inline tags between the passage's tokens.

_INTERVENING = r"(?:\s|<[^>]+>|&[a-z#0-9]+;)*"


def _build_passage_regex(passage: str) -> re.Pattern[str]:
    tokens = re.findall(r"\S+", passage)
    if not tokens:
        return re.compile(r"(?!)")
    body = _INTERVENING.join(re.escape(t) for t in tokens)
    return re.compile(body, re.IGNORECASE)


def _render_claim_span(claim: Claim, matched: str) -> str:
    cls = f"claim claim-{claim.type.value}"
    orig = f'<span class="c-original">{matched}</span>'
    plain = (
        f'<span class="c-plain">{_esc(claim.plain_language)}</span>'
        if claim.plain_language
        else f'<span class="c-plain">{_esc(claim.statement)}</span>'
    )
    # id="claim-{id}" lets dependency links target a specific claim span.
    return (
        f'<span class="{cls}" '
        f'id="claim-{_esc(claim.id)}" '
        f'data-claim-id="{_esc(claim.id)}" '
        f'tabindex="0" '
        f'role="button" '
        f'title="{_esc(claim.type.value.replace("_", " "))} · {_esc(claim.hedging.value)}">'
        f"{orig}{plain}</span>"
    )


_TAG_RE = re.compile(r"<(/?)(\w+)[^>]*?(/?)>")
_TRAILING_PUNCT = re.compile(r"\s*[.,;](?=\s|$|<)")


def _absorb_trailing_punct(html_str: str, end: int) -> int:
    m = _TRAILING_PUNCT.match(html_str, end)
    return m.end() if m else end


def _balance_slice(html_str: str, start: int, end: int) -> tuple[int, int]:
    """Extend `end` so the slice html_str[start:end] has balanced tags.

    If the match cut through an open tag (e.g. <span class="math inline">...
    ends before </span>), extend end to include the matching close.
    """
    for _ in range(8):  # bounded iteration
        stack: list[str] = []
        for m in _TAG_RE.finditer(html_str, start, end):
            is_close, tag, self_close = m.group(1), m.group(2), m.group(3)
            if self_close:
                continue
            if is_close:
                if stack and stack[-1] == tag:
                    stack.pop()
            else:
                stack.append(tag)
        if not stack:
            return start, end
        # extend end to close the last unclosed tag
        closer = re.compile(rf"</{re.escape(stack[-1])}\s*>")
        m = closer.search(html_str, end)
        if not m:
            return start, end
        end = m.end()
    return start, end


def _wrap_claims_in_section(
    section_html: str, section_text: str, claims: list[Claim]
) -> str:
    """Wrap each claim's passage in section_html with an annotation span.

    Claims are located by (char_start, char_end) indices into section_text,
    which gives us the verbatim passage string. We search for that string
    (via a whitespace-and-tag-tolerant regex) in section_html and wrap the
    first match, extending the range to respect tag balance. Overlapping
    matches are dropped.
    """
    if not claims:
        return section_html

    ranked: list[tuple[int, int, Claim]] = []
    for c in claims:
        if not (0 <= c.char_start < c.char_end <= len(section_text)):
            continue
        passage = section_text[c.char_start : c.char_end]
        m = _build_passage_regex(passage).search(section_html)
        if m is None:
            continue
        start, end = _balance_slice(section_html, m.start(), m.end())
        # Eat a trailing "." / "," / ";" that sits right after the match,
        # so plain-language swaps don't strand the original sentence's
        # terminator floating after the span.
        end = _absorb_trailing_punct(section_html, end)
        ranked.append((start, end, c))
    ranked.sort(key=lambda t: t[0])

    # Apply wraps right-to-left so earlier indices stay valid. Drop a later
    # (in-document) claim if it overlaps one we've already wrapped.
    out = section_html
    next_start = len(out) + 1
    for start, end, claim in reversed(ranked):
        if end > next_start:
            continue
        matched = out[start:end]
        out = out[:start] + _render_claim_span(claim, matched) + out[end:]
        next_start = start
    return out


# ── Legend ────────────────────────────────────────────────────────────────


def _claim_legend(claims: list[Claim]) -> str:
    counts: dict[str, int] = {}
    for c in claims:
        counts[c.type.value] = counts.get(c.type.value, 0) + 1
    if not counts:
        return ""
    label = {
        "empirical_result": "Empirical",
        "methodological_claim": "Methodological",
        "theoretical_claim": "Theoretical",
        "background_claim": "Background",
        "limitation": "Limitation",
    }
    rows = []
    for key in (
        "empirical_result",
        "methodological_claim",
        "theoretical_claim",
        "background_claim",
        "limitation",
    ):
        if key in counts:
            rows.append(
                f'<li><span class="swatch claim-{key}"></span>'
                f'{label[key]} <span class="count">{counts[key]}</span></li>'
            )
    return f'<ul class="legend" aria-label="claim types">{"".join(rows)}</ul>'


# ── Sections ──────────────────────────────────────────────────────────────


def _inject_figure_glosses(
    section_html: str, glosses_by_basename: dict[str, FigureGloss]
) -> str:
    """Add a plain-language gloss inside each <figure> whose image matches."""
    if not glosses_by_basename or "<figure" not in section_html:
        return section_html

    soup = BeautifulSoup(section_html, "html.parser")
    touched = False

    for fig in soup.find_all("figure"):
        img = fig.find("img")
        if not img or not img.get("src"):
            continue
        basename = Path(img["src"]).name
        gloss = glosses_by_basename.get(basename)
        if gloss is None:
            continue

        existing_class = fig.get("class") or []
        fig["class"] = existing_class + ["has-gloss"]

        plain_div = soup.new_tag("div", attrs={"class": "fig-plain"})
        plain_div.string = gloss.plain_language
        img.insert_after(plain_div)

        figcap = fig.find("figcaption")
        if figcap is not None:
            cap_class = figcap.get("class") or []
            if "fig-original" not in cap_class:
                figcap["class"] = cap_class + ["fig-original"]
        if gloss.caption_override:
            override = soup.new_tag(
                "figcaption", attrs={"class": "fig-override"}
            )
            override.string = gloss.caption_override
            if figcap is not None:
                figcap.insert_before(override)
            else:
                fig.append(override)

        touched = True

    return str(soup) if touched else section_html


def _render_sections(paper: Paper) -> str:
    by_section: dict[str, list[Claim]] = {}
    for c in paper.claims:
        by_section.setdefault(c.section, []).append(c)

    glosses_by_basename = {g.image: g for g in paper.figure_glosses}

    parts: list[str] = []
    for i, s in enumerate(paper.sections):
        tag = f"h{min(max(s.level + 1, 2), 4)}"
        sec_id = _section_id(s.title, i)
        body = _wrap_claims_in_section(s.html, s.text, by_section.get(s.title, []))
        body = _inject_figure_glosses(body, glosses_by_basename)
        parts.append(
            f'<section id="{sec_id}" aria-labelledby="{sec_id}-h">'
            f'<{tag} id="{sec_id}-h">{_esc(s.title)}</{tag}>'
            f"{body}</section>"
        )
    return "\n".join(parts)


def _render_toc(paper: Paper) -> str:
    """Emit a simple table of contents; CSS only shows it on wide viewports."""
    items = []
    for i, s in enumerate(paper.sections):
        sec_id = _section_id(s.title, i)
        # Skip tiny anomaly sections (rare, from PDF-fallback mis-detections).
        if len(s.text) < 120:
            continue
        items.append(
            f'<li class="toc-l{min(s.level, 3)}">'
            f'<a href="#{sec_id}">{_esc(s.title)}</a></li>'
        )
    if not items:
        return ""
    return (
        '<nav class="toc" aria-label="sections">'
        '<div class="toc-label">Sections</div>'
        f'<ol>{"".join(items)}</ol>'
        "</nav>"
    )


# ── Document ──────────────────────────────────────────────────────────────


def render_paper(paper: Paper, css_href: str = "/static/reader.css") -> str:
    title = _esc(paper.title)
    authors = ", ".join(_esc(a) for a in paper.authors)
    abstract = _esc(paper.abstract) if paper.abstract else ""

    katex_css = f"https://cdn.jsdelivr.net/npm/katex@{KATEX_VERSION}/dist/katex.min.css"
    katex_js = f"https://cdn.jsdelivr.net/npm/katex@{KATEX_VERSION}/dist/katex.min.js"
    katex_auto = f"https://cdn.jsdelivr.net/npm/katex@{KATEX_VERSION}/dist/contrib/auto-render.min.js"

    katex_bootstrap = (
        "renderMathInElement(document.body, { throwOnError: false, delimiters: ["
        "{left:'$$',right:'$$',display:true},"
        "{left:'\\\\[',right:'\\\\]',display:true},"
        "{left:'$',right:'$',display:false},"
        "{left:'\\\\(',right:'\\\\)',display:false}"
        "] })"
    )

    legend = _claim_legend(paper.claims)
    abstract_block = (
        f'<div class="abstract"><span class="label">Abstract</span>{abstract}</div>'
        if abstract
        else ""
    )

    # Claims dict for panel.js — safe escape of "</" for inline <script>.
    claims_payload = {c.id: c.model_dump(mode="json") for c in paper.claims}
    claims_json = json.dumps(claims_payload, ensure_ascii=False).replace(
        "</", "<\\/"
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>{title} — Clarify</title>
<meta name="viewport" content="width=device-width, initial-scale=1" />
<link rel="stylesheet" href="{css_href}" />
<link rel="stylesheet" href="{katex_css}" crossorigin="anonymous" />
<script defer src="{katex_js}" crossorigin="anonymous"></script>
<script defer src="{katex_auto}" crossorigin="anonymous" onload="{katex_bootstrap}"></script>
<script type="application/json" id="claims-data">{claims_json}</script>
<script defer src="/static/panel.js"></script>
<script defer src="/static/lightbox.js"></script>
</head>
<body>
<input type="radio" name="mode" id="mode-plain" class="mode-toggle" checked>
<input type="radio" name="mode" id="mode-original" class="mode-toggle">
<header>
  <a class="brand" href="/">Clarify</a>
  <span class="title">{title}</span>
  <span class="spacer"></span>
  {legend}
  <div class="mode-switch" role="tablist" aria-label="reading level">
    <label for="mode-plain" role="tab">Plain</label>
    <label for="mode-original" role="tab">Original</label>
  </div>
  <a class="back" href="/">← All</a>
</header>
{_render_toc(paper)}
<main>
  <h1>{title}</h1>
  <div class="authors">{authors}</div>
  {abstract_block}
  {_render_sections(paper)}
</main>
<aside id="panel" hidden aria-label="claim detail">
  <button class="close" type="button" aria-label="close panel">×</button>
  <div class="panel-body"></div>
</aside>
</body>
</html>
"""


# ── Index / gallery renderer ──────────────────────────────────────────────


def _paper_card(paper: Paper, base_path: str = "/paper/") -> str:
    arxiv_id = _esc(paper.arxiv_id)
    title = _esc(paper.title)
    authors = paper.authors or []
    author_text = ", ".join(_esc(a) for a in authors[:3])
    if len(authors) > 3:
        author_text += f', <span class="et-al">+{len(authors) - 3}</span>'

    by_type: dict[str, int] = {}
    for c in paper.claims:
        by_type[c.type.value] = by_type.get(c.type.value, 0) + 1
    chips = []
    for key in TYPE_ORDER:
        if key in by_type:
            chips.append(
                f'<span class="chip claim-{key}" title="{_esc(TYPE_LABELS[key])}">'
                f"{by_type[key]}</span>"
            )
    chips_html = (
        "".join(chips)
        if chips
        else '<span class="chip chip-empty">no claims yet</span>'
    )

    hero = ""
    for c in paper.claims:
        if c.plain_language and c.type.value in (
            "empirical_result",
            "methodological_claim",
        ):
            hero = c.plain_language
            break
    if not hero:
        for c in paper.claims:
            if c.plain_language:
                hero = c.plain_language
                break
    hero_html = (
        f'<blockquote class="card-hero">{_esc(hero)}</blockquote>' if hero else ""
    )

    cat = paper.primary_category
    cat_label = CATEGORY_LABELS.get(cat, cat) if cat else None
    cat_html = (
        f'<span class="card-cat" data-cat="{_esc(cat or "")}">'
        f'{_esc(cat_label or "")}</span>'
        if cat_label
        else ""
    )

    haystack = " ".join(
        [paper.arxiv_id, paper.title, " ".join(authors), cat or "", cat_label or ""]
    ).lower()
    haystack = _esc(haystack)

    return (
        f'<a class="paper-card" href="{base_path}{arxiv_id}" data-search="{haystack}">'
        f'  <div class="card-meta">'
        f'    <span class="card-id">{arxiv_id}</span>'
        f"    {cat_html}"
        f"  </div>"
        f'  <h2 class="card-title">{title}</h2>'
        f'  <div class="card-authors">{author_text}</div>'
        f"  {hero_html}"
        f'  <div class="card-foot">'
        f'    <div class="card-chips">{chips_html}</div>'
        f'    <span class="card-cta">Read →</span>'
        f"  </div>"
        f"</a>"
    )


_INDEX_SEARCH_JS = """
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


def render_index(
    papers: list[Paper],
    *,
    css_href: str = "/static/reader.css",
    paper_base: str = "/paper/",
    show_header_form: bool = True,
) -> str:
    """Gallery / landing page. Used by both the runtime server and build-static.

    `paper_base` lets the same renderer emit `/paper/<id>` for the FastAPI
    route or `p/<id>.html` for the static-site layout.
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
    or follow <a href="https://github.com/vipinkashyap/clarify/blob/main/docs/extract-prompt.md">docs/extract-prompt.md</a>.
  </p>
</main>
{_INDEX_SEARCH_JS}
</body></html>"""
