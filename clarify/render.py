"""Server-side rendering: Paper → full HTML document.

No client-side JavaScript is needed to read the paper. KaTeX loads only to
paint math (the one exception, per SPEC.md). The result is a single HTML
document the browser can render with HTML + CSS alone.
"""

from __future__ import annotations

import html
import re

from clarify.schema import Claim, Paper


KATEX_VERSION = "0.16.11"


def _esc(s: str) -> str:
    return html.escape(s, quote=True)


def _section_id(title: str, idx: int) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return f"sec-{idx}-{slug}" if slug else f"sec-{idx}"


def _render_sections(paper: Paper) -> str:
    parts: list[str] = []
    for i, s in enumerate(paper.sections):
        tag = f"h{min(max(s.level + 1, 2), 4)}"  # paper h1s map to page h2s
        sec_id = _section_id(s.title, i)
        parts.append(
            f'<section id="{sec_id}" aria-labelledby="{sec_id}-h">'
            f'<{tag} id="{sec_id}-h">{_esc(s.title)}</{tag}>'
            f"{s.html}"
            f"</section>"
        )
    return "\n".join(parts)


def _claim_legend(claims: list[Claim]) -> str:
    counts: dict[str, int] = {}
    for c in claims:
        counts[c.type.value] = counts.get(c.type.value, 0) + 1
    if not counts:
        return ""
    rows = []
    label = {
        "empirical_result": "Empirical",
        "methodological_claim": "Methodological",
        "theoretical_claim": "Theoretical",
        "background_claim": "Background",
        "limitation": "Limitation",
    }
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
                f"{label[key]} <span class=\"count\">{counts[key]}</span></li>"
            )
    return f'<ul class="legend" aria-label="claim types">{"".join(rows)}</ul>'


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
</head>
<body>
<header>
  <a class="brand" href="/">Clarify</a>
  <span class="title">{title}</span>
  <span class="spacer"></span>
  {legend}
  <a class="back" href="/">← All papers</a>
</header>
<main>
  <h1>{title}</h1>
  <div class="authors">{authors}</div>
  {abstract_block}
  {_render_sections(paper)}
</main>
</body>
</html>
"""
