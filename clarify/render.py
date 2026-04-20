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

from clarify.schema import Claim, Paper


KATEX_VERSION = "0.16.11"


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


def _render_sections(paper: Paper) -> str:
    by_section: dict[str, list[Claim]] = {}
    for c in paper.claims:
        by_section.setdefault(c.section, []).append(c)

    parts: list[str] = []
    for i, s in enumerate(paper.sections):
        tag = f"h{min(max(s.level + 1, 2), 4)}"
        sec_id = _section_id(s.title, i)
        body = _wrap_claims_in_section(s.html, s.text, by_section.get(s.title, []))
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
