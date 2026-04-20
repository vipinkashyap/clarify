# Clarify

A reading overlay for arxiv papers. Clarify extracts the load-bearing *claims* from a paper and surfaces them inline, with a plain-language rewrite for every one. Click a claim to see its evidence, its hedging, and what it builds on. Open the reader and any ingested paper is readable in plain English by default — the authors' words are one toggle away.

## Setup

Requires Python 3.11+, `uv`, `pandoc` (`brew install pandoc`), and for EPS figures `ghostscript` (`brew install ghostscript`).

```
uv venv
uv pip install -e .
uv run clarify bootstrap          # fetches + ingests every paper in extractions/
uv run uvicorn clarify.main:app   # reader at http://localhost:8000
```

## See what's already extracted

```
uv run clarify stats
```

See [docs/coverage.md](docs/coverage.md) for the current snapshot of papers, claims, and eval numbers.

## Add a paper

### If you have Claude Code

Open a Claude Code session in this repo and say:

> extract claims from 2010.11929

The bundled [`clarify-extract` skill](.claude/skills/clarify-extract/SKILL.md) drives the whole pipeline — fetch, read, draft claims with plain-language rewrites, resolve offsets, ingest, verify. Extraction runs on *your* Claude Code subscription; nothing is shared. After it finishes, PR the new `extractions/<arxiv_id>.json` file.

### If you have claude.ai / ChatGPT / Gemini but not Claude Code

```
uv run clarify fetch <arxiv_id>
uv run clarify prompt <arxiv_id> > prompt.md
```

Paste `prompt.md` into a chat, save the model's JSON output as `extractions/<arxiv_id>.json`, and run `uv run clarify bootstrap` to verify. See [docs/extract-prompt.md](docs/extract-prompt.md) for the full flow.

### If you don't have an LLM at all

You can write the JSON by hand following [clarify/prompts/extract_claims.md](clarify/prompts/extract_claims.md). It's slower but fully supported.

### If you're not a developer

Open a [paper-request issue](../../issues/new?template=request-paper.md) — someone from the first group picks it up.

## Measure coverage

- **Paper coverage** — `clarify stats`, or [docs/coverage.md](docs/coverage.md)
- **Extraction quality** — hand-annotate a paper in `eval/annotations/<arxiv_id>.json` and run `python eval/run_eval.py`. Aggregate P / R numbers land in the coverage report. Currently **P 97.3% · R 77.6%** across three annotated papers.
- **Community activity** — git log; a GitHub Action can auto-regenerate `docs/coverage.md` on every merge (future).

## Deploy a read-only site

For non-developers who just want to read, pre-render the whole gallery and deploy anywhere:

```
uv run clarify build-static dist
```

This writes `dist/index.html`, one `dist/p/<arxiv_id>.html` per paper, plus `static/` and `figures/`. Open `dist/index.html` directly, or serve it:

```
python -m http.server --directory dist 8001
```

All paths are relative, so the same directory deploys to GitHub Pages, Netlify, Vercel, S3 — anywhere static files live.

**GitHub Pages** is wired up: [`.github/workflows/pages.yml`](.github/workflows/pages.yml) builds on every push to `main` (installs pandoc + ghostscript, runs `clarify bootstrap` to fetch/ingest every paper in `extractions/`, regenerates `docs/coverage.md`, builds the static site, deploys). To enable: go to repo **Settings → Pages → Source → "GitHub Actions"**. The site appears at `https://<user>.github.io/<repo>/`.

## Architecture

No LLM is called from Python. Extraction runs in your Claude Code (or any LLM chat). The reader server only renders already-cached papers. The only runtime JS is KaTeX (math) and a small panel + lightbox. Everything else is HTML + CSS.

```
clarify/         # Python: fetch, parse, render, CLI, FastAPI reader
extractions/     # community-contributed <arxiv_id>.json drafts (committed)
eval/            # hand-annotated ground truth + run_eval.py
docs/            # extract-prompt.md, coverage.md
.claude/skills/  # Claude Code skill
```

See [SPEC.md](SPEC.md) for the full design.
