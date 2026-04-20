# Clarify

**A reading overlay for arxiv papers.** Clarify pulls the load-bearing *claims* out of a paper, surfaces them inline, and rewrites each one in plain English. Click a claim to see its evidence, how strongly it's hedged, and what it builds on. The authors' exact words are one toggle away.

---

## I just want to read papers

→ **[vipinkashyap.github.io/clarify](https://vipinkashyap.github.io/clarify/)**

Nothing to install. The site lists every paper Clarify has extracted. Click one, read it in plain English, toggle to the authors' words when you want.

## I want to add a paper

Pick the path that matches your setup. All three produce the same output — a JSON file in `extractions/<arxiv_id>.json` that you open a PR for.

### ↳ With Claude Code

Easiest path. Clone the repo, open it in Claude Code, and say:

> extract claims from 2010.11929

The bundled [`clarify-extract` skill](.claude/skills/clarify-extract/SKILL.md) handles everything: fetches the paper, reads it, drafts the claims with plain-language rewrites, checks them, ingests. Runs on *your* Claude Code subscription — nothing shared. After it finishes, commit the new `extractions/<arxiv_id>.json` and open a PR.

### ↳ With claude.ai / ChatGPT / Gemini

If you have an LLM chat but not Claude Code:

```
uv run clarify fetch <arxiv_id>
uv run clarify prompt <arxiv_id> > prompt.md
```

Paste `prompt.md` into any LLM chat, save the model's JSON output as `extractions/<arxiv_id>.json`, verify with `uv run clarify bootstrap`, and PR. See [docs/extract-prompt.md](docs/extract-prompt.md) for the full flow.

### ↳ Without any LLM

You can write the JSON by hand against [clarify/prompts/extract_claims.md](clarify/prompts/extract_claims.md). Slower but fully supported.

## I want a paper extracted but can't do it myself

Open a [paper-request issue](../../issues/new?template=request-paper.md) with the arxiv id and a sentence on why. Someone from the three paths above picks it up.

## Current coverage

See [docs/coverage.md](docs/coverage.md) — auto-regenerated on each deploy.

At a glance: **4 papers extracted** across NLP (Attention, BERT), Vision (ViT), and ML (Batch Norm), **92 claims total**, all with plain-language rewrites. Extraction quality: aggregate **P 97.3% · R 77.6%** vs hand-annotated ground truth on three papers (target was ≥85% / ≥70%).

> "Coverage" here means: *of the papers in the cache, how well is each extracted* — not *what fraction of arxiv* (arxiv is ~2.5M papers; no prototype covers a meaningful slice of that). The project's scope is a curated reading list, not a search index.

---

## Developing locally

Requires Python 3.11+, [uv](https://docs.astral.sh/uv/), `pandoc` (`brew install pandoc` on macOS, `apt install pandoc` on Linux), and — for EPS figure conversion — `ghostscript` (`brew install ghostscript`).

```
uv venv
uv pip install -e .
uv run clarify bootstrap          # fetches + ingests every paper in extractions/
uv run uvicorn clarify.main:app   # reader at http://localhost:8000
```

### Useful CLI commands

| Command | What it does |
|---|---|
| `clarify bootstrap` | Fetch + parse + ingest everything in `extractions/`. Idempotent. |
| `clarify fetch <id>` | Download + parse one paper (falls back to PDF on pandoc errors). |
| `clarify prompt <id>` | Emit a chat-ready extraction prompt for non-Claude-Code users. |
| `clarify build-claims <id> <draft>` | Resolve passage offsets and ingest a draft. |
| `clarify build-static <dir>` | Pre-render the whole site as static HTML. |
| `clarify stats [--markdown]` | Paper + claim + eval coverage snapshot. |
| `clarify info <id>` / `clarify list` | Inspect the local cache. |

### Architecture

No LLM is ever called from Python — extraction runs inside *your* Claude Code (or any LLM chat). The reader server only renders already-cached papers. The only runtime JS is KaTeX (math) and two small files (side panel + figure lightbox). Everything else is HTML + CSS.

```
clarify/         # Python: fetch, parse, render, CLI, FastAPI reader
extractions/     # community-contributed <arxiv_id>.json drafts (committed)
eval/            # hand-annotated ground truth + run_eval.py
docs/            # extract-prompt.md, coverage.md
.claude/skills/  # Claude Code skill
.github/         # workflows + issue templates
```

### Deploy

[`.github/workflows/pages.yml`](.github/workflows/pages.yml) builds on every push to `main` and deploys to GitHub Pages. To flip it on: **Settings → Pages → Source → "GitHub Actions"**.

Portable to any static host — the build output is plain HTML with relative paths.

### Eval

```
uv run python eval/run_eval.py
```

Compares `eval/generated/<id>.json` against hand-annotated `eval/annotations/<id>.json` via max of SequenceMatcher + content-token Jaccard (threshold 0.45). Current aggregate: 97% precision, 77% recall across three annotated papers. Target: ≥85% / ≥70%.

See [SPEC.md](SPEC.md) for the full design and non-goals.
