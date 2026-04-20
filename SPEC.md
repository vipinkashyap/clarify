# Clarify — Prototype Spec

> **Historical spec — kept for the design record.** The prototype has shipped
> several things the original spec called non-goals or deferred: a hosted
> static site at [vipinkashyap.github.io/clarify](https://vipinkashyap.github.io/clarify/),
> mobile-responsive layout, figure extraction, a gallery of papers, live
> arxiv search via a Cloudflare Worker, and a Claude Code skill for
> distributed extraction. See [README.md](README.md) for what's actually
> built; this file documents the original intent.

## What this is

A single-paper claim extractor with an adaptive reading overlay. You give an arxiv ID to Claude Code, which extracts structured claims from the paper into a local cache. You then open a browser-based reading view where the paper is rendered with beautiful typography and each claim is annotated inline. A reading-level toggle lets the reader see claims in plain language or the authors' original wording.

The reading experience must be **beautiful**. Typography, spacing, and math rendering are not polish items to defer — they are the product. A reader who opens Clarify should feel, within five seconds, that this is the nicest thing that has ever happened to an arxiv paper.

This is a **prototype**. Goals: (a) validate that LLM-based claim extraction on research papers works at acceptable quality on a small set of papers, and (b) validate that an inline reading overlay on beautifully rendered papers feels good to use. It is explicitly not a product yet. No users, no cloud, no auth, no API keys.

## Architecture note: how extraction happens

Clarify does NOT call the Anthropic API directly. The developer is a Claude Code subscriber and uses Claude Code itself as the extraction engine. The workflow is:

1. **Extraction phase (via Claude Code):** The developer opens Claude Code in the clarify repo and says something like "extract claims from arxiv 2301.12345." Claude Code runs `python -m clarify.fetch 2301.12345` to fetch and parse the paper into sections, reads the section text, produces claim JSON conforming to the schema, and writes it to the local SQLite cache via `python -m clarify.ingest <json_path>`. Extraction is an offline batch step.

2. **Reading phase (via browser):** The developer (or anyone with the repo running locally) opens `localhost:8000`, enters an arxiv ID that has already been extracted, and gets the beautiful reading view with inline annotations. The FastAPI server only serves already-cached papers; it never calls an LLM.

3. **Plain-language generation:** Also happens via Claude Code, offline. The developer says "generate plain-language versions for all claims in paper 2301.12345" and Claude Code runs the generation and writes results back to the cache.

This means **the only code in the repo that calls an LLM is the developer's Claude Code session itself.** There are no `anthropic.Anthropic()` calls anywhere in the Python code. The extraction prompt lives in `clarify/prompts/extract_claims.txt` as instructions to Claude Code, not as a programmatic prompt.

This is the correct architecture for this prototype because:
- No API keys to manage
- Extraction quality is as high as possible (Claude Opus 4.7 via Claude Code)
- Iterating on extraction prompts happens conversationally, which is faster than code-prompt cycles
- The reading view — the actual concept under test — is fully self-contained and demonstrable to anyone without credentials

## Success criteria for this prototype

1. Five arxiv papers the developer has read carefully get extracted via Claude Code with ≥85% claim precision against hand-annotated ground truth.
2. The reading view renders the paper with typography comparable to a well-typeset book or journal. Math renders cleanly. Figures render in place. Citations are linked.
3. Inline claim annotations don't disrupt reading flow — a reader who ignores them can read the paper end-to-end without friction.
4. The reading-level toggle meaningfully changes comprehension — plain-language versions are genuinely easier for a non-expert.
5. End-to-end time from "developer asks Claude Code to extract a paper" to "paper available in reader" is under 5 minutes for a 10-page paper.

If criterion 1 fails, stop and fix the extraction prompt/pipeline before anything else. If criterion 2 fails, the prototype is technically working but doesn't prove the concept.

## Stack

- **Backend:** Python 3.11+, FastAPI, SQLite via `sqlite3` stdlib
- **CLI:** `typer` for the `clarify` command-line interface Claude Code will invoke
- **Paper fetching:** `arxiv` Python library for metadata; direct HTTPS for PDF and LaTeX source
- **LaTeX processing:** `pandoc` via subprocess for LaTeX→HTML, with custom post-processing
- **PDF fallback:** `pymupdf` for layout-aware text extraction
- **Frontend:** Plain HTML + vanilla JS + custom CSS. No framework, no build step.
- **Math rendering:** KaTeX (self-hosted). Not MathJax.
- **Fonts:** self-hosted, see Typography section below.
- **Dev runner:** `uvicorn clarify.main:app --reload`

No Anthropic SDK. No `ANTHROPIC_API_KEY`. No network calls to any LLM provider.

## Typography — the heart of the reading view

Reading a paper should feel like reading a well-designed book, not a web page and not a PDF in a browser. Implement the details below literally unless you have a specific reason not to.

### Fonts

Self-host via `@font-face`. Files in `clarify/static/fonts/`, checked in.

- **Body:** Source Serif 4 (variable font, regular + italic, weights 400 + 600). Adobe released it open-source; designed for extended reading.
- **Headings:** Source Serif 4 weight 600 at larger sizes. Don't mix a second family — consistency reads more confident than variety.
- **Math and inline code:** JetBrains Mono (regular + italic, 400). KaTeX ships its own math fonts (KaTeX_Main etc.); include them.
- **UI chrome:** Inter (variable, weights 400 + 500 + 600). Sans-serif for UI so it separates from the editorial body.

Fallback for body: `'Source Serif 4', 'Source Serif Pro', Charter, 'Iowan Old Style', 'Palatino Linotype', Georgia, serif`.
Fallback for UI: `'Inter', -apple-system, 'Segoe UI', system-ui, sans-serif`.

### Scale and rhythm

- Body: **19px**, line-height **1.65**, color **#2a2a2a** on background **#fafaf7** (warm off-white — not stark white).
- Measure: **max-width: 68ch** for the body column. Lands around 680–720px — the sweet spot for sustained reading.
- Paragraph spacing: no blank line between paragraphs. Use **text-indent: 1.25em** on paragraphs after the first. First paragraph after a heading gets no indent (`h1 + p, h2 + p, h3 + p { text-indent: 0 }`).
- Headings: H1 at 2.25em weight 600, H2 at 1.5em weight 600, H3 at 1.2em weight 600 italic. Generous top margin (2em+), tight bottom margin (0.5em).
- Title block: title at H1 scale, authors at 1em italic in `#6a6a6a`, abstract at body size with `padding-inline: 2em` and italic. Small-caps "Abstract" label above.

### Character-level polish

- **Ligatures:** `font-feature-settings: 'liga' 1, 'calt' 1, 'dlig' 1;` on body.
- **Old-style figures:** `'onum' 1` in body — numbers like 1873 sit with descenders. Override to tabular lining (`'lnum' 1, 'tnum' 1`) inside tables and math.
- **True small caps:** `'smcp' 1` for "Abstract" label etc. Never fake with `text-transform: uppercase`.
- **Hyphenation:** `hyphens: auto; -webkit-hyphens: auto;` on body column.
- **Alignment:** left-align, not justified. Browsers justify poorly.
- **Punctuation:** real typographic characters. Em dashes, curly quotes, real ellipsis. Pandoc's `--smart` flag handles input.
- **Drop cap on first paragraph of introduction:** 3-line drop cap using `initial-letter: 3`, with `float: left` + size + line-height fallback for unsupported browsers.

### Dark mode

Not in the prototype. Explicitly defer.

### Color system

Muted, warm, editorial. Small palette.

- Background: `#fafaf7`
- Body: `#2a2a2a`
- Muted (authors, captions): `#6a6a6a`
- Rule/border: `#e5e2d8`
- Link: `#5c4a3a` — warm dark brown. Subtle underline via `text-decoration-color` at 40% opacity.
- Claim annotations — one muted hue per type, applied as 2px left border OR subtle background tint, never both, never saturated:
  - Empirical result: accent `#4a7a5c`, tint `#edf4ef`
  - Methodological claim: accent `#5c6a8a`, tint `#eef0f5`
  - Theoretical claim: accent `#7a5c8a`, tint `#f2edf5`
  - Background claim: accent `#8a7a4a`, tint `#f5f2e8`
  - Limitation: accent `#8a5c4a`, tint `#f5ede8`

Default annotation: 2px solid left border in accent, `padding-left: 0.5em`, tint background at 40% alpha. Hover intensifies tint to 80% alpha. A reader should be able to forget annotations are there.

### Math rendering

KaTeX with auto-render extension.

- Inline: `\(...\)` and `$...$`
- Display: `\[...\]` and `$$...$$`
- `throwOnError: false` — fall back to raw TeX in `<code>` rather than crashing
- Display math: block, 1em vertical margin, center-aligned
- Equation numbers via `\tag{…}` or pandoc numbering, right-aligned in muted gray

Never render math as an image. KaTeX output is real text.

### Figures

Centered in body column, up to full width. Caption below in 0.9em italic muted gray, figure number in small caps. 1em margin above/below. Click-to-enlarge in overlay.

Extract figure files from arxiv source bundle and serve as static assets.

### Tables

Booktabs style: border-collapse, no outer border, horizontal rules only (top, below header, bottom). Tabular figures (`font-variant-numeric: tabular-nums`). Caption above in figure-caption style. Wider than column → horizontal scroll within container.

### Citations and references

Inline citations (`[12]`, `(Smith et al., 2023)`) as real links — warm brown, no underline. Click → smooth scroll to reference with 0.8s fade highlight.

References section: hanging indent (`text-indent: -1.5em; padding-left: 1.5em`), 0.5em between entries, 0.95em size.

### Page layout

```
┌────────────────────────────────────────────────────────────────────┐
│  Clarify   [paper title]                         [Original|Plain]  │  ← fixed header, 56px
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│                                                   ┌──────────────┐ │
│         [paper body, 68ch,                        │ side panel   │ │
│          centered until panel                     │ on claim     │ │
│          opens, then shifts left]                 │ click, 360px │ │
│                                                   └──────────────┘ │
└────────────────────────────────────────────────────────────────────┘
```

- Fixed header, 56px, 1px bottom border `#e5e2d8`. Backdrop blur (`backdrop-filter: blur(8px)`) with 85% opacity background.
- Body column centered. When side panel opens, body shifts left, preserving line length.
- Side panel: soft left border, background `#f5f2ea`, 200ms ease-out slide.
- Max page width 1200px, centered.

### Loading / empty states

Since extraction happens offline via Claude Code, the browser's loading states are minimal:

- `localhost:8000` (index): a simple input for an arxiv ID. If the ID isn't in the cache, show a helpful message explaining how to extract it: "This paper hasn't been ingested yet. In Claude Code, run: `clarify ingest 2301.12345`."
- `localhost:8000/paper/{id}` for a cached paper: loads instantly, renders the paper.

### Micro-interactions

- Claim hover: tint intensifies 5% → 15% opacity, 150ms ease
- Claim click: side panel slides in; clicked claim tint persists while open
- "Plain" toggle: annotated spans crossfade to plain-language over 250ms; non-claim text unchanged
- Citation click: smooth scroll with 0.8s fade highlight

All transitions under 300ms.

## Repo structure

```
clarify/
├── README.md
├── SPEC.md
├── pyproject.toml
├── .gitignore
├── clarify/
│   ├── __init__.py
│   ├── main.py                  # FastAPI app (reading server only)
│   ├── cli.py                   # typer CLI: fetch, ingest, list, info
│   ├── fetch.py                 # arxiv fetch, LaTeX/PDF → sections
│   ├── parse.py                 # pandoc wrapping, section splitting
│   ├── render.py                # HTML post-processing for typography
│   ├── ingest.py                # load claim JSON into SQLite
│   ├── schema.py                # Pydantic models
│   ├── cache.py                 # SQLite wrapper
│   ├── prompts/
│   │   └── extract_claims.md    # instructions for Claude Code, human-readable
│   └── static/
│       ├── index.html
│       ├── reader.html
│       ├── reader.js
│       ├── reader.css
│       └── fonts/
├── eval/
│   ├── papers/                  # arxiv IDs
│   ├── annotations/             # hand-annotated ground truth
│   ├── generated/               # extracted claim JSON from Claude Code runs
│   ├── run_eval.py              # compares generated/ to annotations/
│   └── README.md
└── tests/
    └── test_schema.py
```

## CLI surface (what Claude Code will invoke)

```
clarify fetch <arxiv_id>
  Downloads LaTeX or PDF, parses into sections, writes parsed paper to
  .cache/parsed/<arxiv_id>.json. Does NOT extract claims — that's Claude
  Code's job.

clarify ingest <arxiv_id> <claims_json_path>
  Takes a claims JSON file (produced by Claude Code following the schema)
  and merges it with the parsed paper, writing the full Paper object to
  SQLite. After this, the reader can serve the paper.

clarify ingest-plain <arxiv_id> <plain_json_path>
  Adds plain-language versions for claims in a paper. Same pattern.

clarify list
  Lists all papers currently in the cache.

clarify info <arxiv_id>
  Shows details for one cached paper: number of claims, whether plain
  versions exist, source type, etc.
```

## Data model

See [clarify/schema.py](clarify/schema.py).

## The extraction workflow (for Claude Code)

See [clarify/prompts/extract_claims.md](clarify/prompts/extract_claims.md).

## Reading view behavior

On page load: render full paper with typography. Render math with KaTeX auto-render. Wrap claim spans in `<span class="claim claim-{type}" data-claim-id="...">`. Default view "Original."

- Hover claim → tint intensifies, small popover with type + hedging
- Click claim → side panel: statement, type, evidence, dependencies, hedging, "Explain simply" button (shows plain-language if available; otherwise shows "Run `clarify generate-plain 2301.12345` to generate plain versions")
- Click "Plain" in header → annotated spans crossfade to plain-language (only claims with a plain-language field populated; others stay original)
- Click citation → smooth scroll to reference with fade highlight

## Eval harness

See [eval/README.md](eval/README.md) and [eval/run_eval.py](eval/run_eval.py).

## API surface (reading server)

- `GET /api/papers/{arxiv_id}` — returns cached Paper or 404 with helpful message
- `GET /api/papers` — lists all cached arxiv IDs and titles
- `GET /` — serves `index.html`
- `GET /paper/{arxiv_id}` — serves `reader.html` for that paper

No POST endpoints. No auth. Localhost-only.

## Non-goals (do not build)

- Any direct LLM API integration — Claude Code is the LLM
- User accounts, auth, multi-user
- Cross-paper linking, claim graph across papers
- Search across claims
- Idea generation, feed, recommendations
- Social features, shared annotations
- Chat interface to the paper
- Mobile-responsive design — desktop only
- Dark mode
- Deployment, Docker, CI/CD
- Paper sources other than arxiv
- Agents writing papers

If tempted, revisit this spec.

## First two evenings

**Evening 1:** Repo setup, schema, CLI skeleton, fetch + parse working end-to-end on one paper (parsed paper JSON lands in `.cache/parsed/`). Write `extract_claims.md`. Hand-annotate two eval papers. Use Claude Code to extract claims for those two papers into `eval/generated/`. Get `clarify ingest` working. Confirm ingested papers show up in SQLite.

**Evening 2:** Run eval. Iterate the extraction prompt doc (conversationally in Claude Code) until precision clears 85% on both annotated papers. Annotate remaining three eval papers along the way. No reading view yet.

**Evenings 3-4:** Build the reading view with full typography. Every detail in the Typography section matters. If you find yourself thinking "close enough" about font loading, line length, or math rendering — not done.

**Evening 5:** Plain-language toggle, claim annotations, side panel, citation linking. Polish pass.

## Environment

No `.env` file. No secrets. Only config is the cache directory, defaulting to `.cache/` at repo root. Override via `CLARIFY_CACHE_DIR` env var if desired.
