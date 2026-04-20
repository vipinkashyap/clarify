# Clarify

> **A reading overlay for arxiv papers.** Open a paper, get the load-bearing claims highlighted inline. Click one to see what it builds on, what evidence supports it, and how strongly the authors meant it. Read in plain English by default; the authors' words are one toggle away.

**→ [vipinkashyap.github.io/clarify](https://vipinkashyap.github.io/clarify/)**

---

## The thing this is trying to fix

Most research papers are written for the people who write research papers. That's reasonable — they're talking to colleagues — but it leaves out almost everyone else. Curious engineers, designers who'd benefit from knowing what's actually been demonstrated, students who want to skim the field before they pick a thesis, people who keep meaning to *finally* read "Attention Is All You Need" but bounce off the first equation.

The information is there. The framing isn't.

Clarify takes a single paper and does three small things:

1. **Highlights the claims** — the load-bearing assertions, color-coded by type (empirical result, methodological choice, theoretical claim, background context, limitation).
2. **Rewrites each one in plain English**, kept right next to the original.
3. **Surfaces the structure** — when you click a claim, you see what it depends on, where to look for the evidence, and how strongly the authors hedged.

The goal is that someone who has never read a paper before can open one and feel oriented within five seconds. Not that they understand every detail — that they can tell *what's being said*.

Five papers are in the gallery today — Attention Is All You Need, BERT, Vision Transformer, and Batch Normalization with full extractions; ResNet parses but its claims haven't been written yet. Below those, a "More from arxiv" section shows recent papers in the three covered categories (NLP, Vision, ML), and the search box runs **live arxiv queries** — anything 3+ characters fires a real search and turns up preview cards with **Request** buttons that open a prefilled GitHub issue. [See them.](https://vipinkashyap.github.io/clarify/)

## How extraction actually happens

Here's the slightly unusual architectural choice. Clarify doesn't call any LLM API from its own code. There's no `anthropic.Anthropic()` anywhere in the Python. Instead, the extraction *is the contributor*, talking to *their own* Claude (or any other LLM) on *their own* subscription.

Concretely: there's a [Claude Code skill](.claude/skills/clarify-extract/SKILL.md) bundled in this repo. When you open the repo in Claude Code and say *"extract claims from 2010.11929"*, the skill drives the local CLI: it fetches the paper, parses it, reads it section by section against the rules in [`extract_claims.md`](clarify/prompts/extract_claims.md), produces a draft, resolves the offsets, ingests into the local cache, and the reader at `localhost:8000` reflects the new paper. Then you commit the resulting `extractions/<arxiv_id>.json` and open a PR.

Why this shape:

- **No shared API keys.** No one is paying for anyone else's extraction. Your Claude Code subscription does your work.
- **No quality ceiling from a hosted backend.** You can use whatever model you want; the project doesn't pin you to one.
- **The reader stays demonstrable.** Anyone can clone the repo and read every contributor's work without having an LLM at all — extractions are committed JSON, the reader just renders.
- **The prompt doc is the source of truth.** Quality drift is a conversation about [`extract_claims.md`](clarify/prompts/extract_claims.md), not a feature flag in code.

The same pattern works without Claude Code. `clarify prompt <arxiv_id>` assembles a single message — instructions plus the parsed paper — that you paste into claude.ai, ChatGPT, Gemini, anything with a context window. You save the JSON it returns and PR it. [Full walkthrough in `docs/extract-prompt.md`.](docs/extract-prompt.md)

If you don't have an LLM at all, you can write the JSON by hand against the schema. It's slower but every other path produces the same file, so contributions are interchangeable.

If you're not a developer at all, you can [open a paper-request issue](../../issues/new?template=request-paper.md) — title, arxiv id, one sentence on why it matters. Someone from the first three groups picks it up.

## What "coverage" means here

When I first wrote a coverage metric, I framed it the way most projects do: *what fraction of the universe have we covered?* Of arxiv's ~2.5 million papers, Clarify has five. That's a humbling number, and it isn't the right one.

Clarify is a curated reading list with deep extraction, not a search index. So coverage means two things, both of which we measure:

- **Per-paper depth.** How many claims, with what type mix, with plain-language for each. ([Live snapshot](docs/coverage.md).)
- **Extraction quality.** When a paper has hand-annotated ground truth in [`eval/annotations/`](eval/annotations), we compare against the extracted version using a max of token-overlap Jaccard and SequenceMatcher ratio. Three papers are double-annotated today; aggregate is **P 97.3% · R 77.6%** against targets of ≥85% / ≥70%.

The coverage doc auto-regenerates on every deploy, so the numbers in the README and the gallery are never stale.

If you want to push extraction quality, the cheapest contribution is to pick an existing paper and add a parallel `eval/annotations/<arxiv_id>.json` written from your own re-read. The eval will tell you (and the project) where the extraction missed.

## How to read the code

```
clarify/
├── render.py        templates: render_paper(), render_index(), card components
├── main.py          FastAPI routes (~70 lines — just routes + mounts)
├── cli/             Typer commands grouped by purpose:
│   ├── extract.py     fetch, ingest, ingest-plain, build-claims, prompt
│   ├── serve.py       bootstrap, build-static, discover
│   └── inspect.py     list, info, stats
├── extract.py       draft → claims+plain JSON, resolves passage offsets
├── parse.py         pandoc (LaTeX) or pymupdf (PDF) → Section objects
├── fetch.py         arxiv source acquisition (LaTeX bundle preferred)
├── figures.py       extracts + converts figures (PDF/EPS → PNG)
├── discover.py      pre-fetches recent arxiv papers per category
├── ingest.py        merges claims + figures into the SQLite cache
├── cache.py         tiny SQLite wrapper
├── schema.py        Pydantic source of truth
├── build_static.py  pre-renders the whole site for any static host
├── prompts/         extract_claims.md — the extraction rulebook
└── static/
    ├── css/             base, paper, panel, chrome, gallery, responsive
    ├── panel.js         side-panel interaction
    ├── lightbox.js      figure click-to-enlarge
    └── arxiv-search.js  live-search client (opt-in via meta tag)

worker/              Cloudflare Worker — arxiv API proxy with CORS
extractions/         committed drafts (one JSON per paper)
eval/                hand-annotated ground truth + run_eval.py
docs/                extract-prompt.md, coverage.md, discover.json
.claude/skills/      clarify-extract/SKILL.md
.github/workflows/   pages.yml — deploy on push to main
```

Four things I'd flag if you read the code:

- **No LLM in Python.** Search for `anthropic` — you won't find it. The boundary is enforced by absence.
- **Schema is the spine.** Every module imports from [`clarify/schema.py`](clarify/schema.py); nothing duplicates the data model.
- **Reader and static-build share one renderer.** [`render.py`](clarify/render.py) emits the HTML for both `/paper/<id>` (FastAPI) and `dist/p/<id>.html` (static). The two outputs can't drift.
- **Search has three tiers, degrading gracefully.** Typing in the search box filters the extracted cards locally. After a debounce, if the gallery sees `<meta name="clarify-worker">`, it also hits the Cloudflare Worker for live arxiv results. Below both, a pre-fetched Discover section shows recent papers in each category. Remove the Worker and live search silently disables; remove the Discover file and its section disappears. The base experience never breaks.

## Running it

You need Python 3.11+, [uv](https://docs.astral.sh/uv/), `pandoc`, and (for EPS figures) `ghostscript`.

```bash
brew install pandoc ghostscript        # or apt equivalents on Linux
uv venv
uv pip install -e .
uv run clarify bootstrap               # fetch + ingest every paper in extractions/
uv run uvicorn clarify.main:app        # http://localhost:8000
```

The first `bootstrap` reads from committed `.cache/parsed/` and `.cache/figures/` so it doesn't hit arxiv. Subsequent runs are no-ops if nothing changed.

A quick CLI tour:

| Command | What it does |
|---|---|
| `clarify bootstrap` | fetch + parse + ingest everything in `extractions/`. Idempotent. |
| `clarify fetch <id>` | fetch + parse one paper (PDF fallback if pandoc rejects the LaTeX). |
| `clarify prompt <id>` | print a chat-ready extraction prompt for non-Claude-Code users. |
| `clarify build-claims <id> <draft>` | resolve a draft's passages to char offsets and ingest. |
| `clarify discover` | refresh the pre-fetched "Recent from arxiv" list (writes `docs/discover.json`). |
| `clarify build-static <dir>` | pre-render the whole site as static HTML. |
| `clarify stats [--markdown]` | per-paper + aggregate coverage. |
| `clarify info <id>` / `clarify list` | inspect the cache. |

## Deploy

[`.github/workflows/pages.yml`](.github/workflows/pages.yml) builds on every push to `main` and deploys to GitHub Pages. To enable on a fork: **Settings → Pages → Source → "GitHub Actions"**.

The build is fast (~1 minute) because `.cache/parsed/` and `.cache/figures/` are committed — CI never hits arxiv. Pushes that only touch README, docs, or issue templates skip the build via `paths-ignore`.

For any other static host, `clarify build-static dist` produces a portable directory of HTML, CSS, fonts, images, and a small amount of JS. All paths are relative.

## Live arxiv search

This deployment runs live search via a Cloudflare Worker at `clarify-arxiv.nowpages.workers.dev`. Type into the gallery's search box; anything 3+ characters fires a real arxiv query, results stream back as preview cards, and every one has a **Request** button that opens a prefilled GitHub issue for extraction. Cached at the Cloudflare edge for 5 minutes per query, which is why repeat searches are instant.

The Worker itself is ~60 lines in [`worker/src/index.js`](worker/src/index.js) — a pure pass-through to `export.arxiv.org/api/query` that adds the CORS header arxiv doesn't send. No backend for Clarify, but a trivial one for arxiv's CORS.

**Forking?** See [`worker/README.md`](worker/README.md) for the two-minute deploy flow on your own Cloudflare account. Then set `CLARIFY_WORKER_URL` as a repository variable (**Settings → Secrets and variables → Actions → Variables**) and push. Without the variable, live search silently disables and the pre-fetched Discover section takes over — nothing breaks, the feature just goes dormant.

## Where this goes next

Not done, in rough priority order:

- **Apply the Attention editorial template to the other four papers.** Attention Is All You Need got a full editorial pass — plain-language rewrites with narrative voice, concrete worked examples for math claims, figure glosses that walk through the diagrams. BERT, ViT, Batch Norm, and ResNet are still in the earlier, more summary-style voice. The [extraction rulebook](clarify/prompts/extract_claims.md) now documents the style for future contributors.
- **More papers.** Five is a proof of concept; thirty would be a small library. Live search + the Request button now make this contributor-driven.
- **Math glosses.** Equations render via KaTeX, but aren't explained with their own plain-language layer. Adding an inline plain-language summary on click would extend the same pattern claims and figures already use.
- **Recall improvement.** Aggregate recall is 77% — precision is excellent, but the extractor is a bit conservative. Iterating [`extract_claims.md`](clarify/prompts/extract_claims.md) to encourage slightly higher claim density should close the gap.
- **A short essay.** A "how to read a research paper with Clarify" piece would double as a landing page. Half-drafted; not yet written.

If any of those interests you, the contribution paths above all work — and there's an [annotation-double-check](.github/ISSUE_TEMPLATE/annotation-pr.md) issue template specifically for the eval-quality work.

## Spec, design notes, and credits

- [`SPEC.md`](SPEC.md) — the original prototype spec, including non-goals.
- [`docs/coverage.md`](docs/coverage.md) — current snapshot, auto-regenerated.
- [`docs/extract-prompt.md`](docs/extract-prompt.md) — contribution path for non-Claude-Code users.
- [`clarify/prompts/extract_claims.md`](clarify/prompts/extract_claims.md) — the extraction rulebook (and the source-of-truth for quality).

Built in a handful of evenings; everything in this repo was iteratively designed and written with Claude Code as collaborator. The whole pipeline — fetch, parse, claim extraction, figure conversion, the reader, the deploy — runs locally on a contributor's machine. There is no backend.
