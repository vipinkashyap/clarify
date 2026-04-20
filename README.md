# Clarify

Single-paper claim extractor with an adaptive reading overlay. You hand an arxiv id to Claude Code; it writes claim JSON into a local cache; you open `localhost:8000` and read the paper with inline annotations.

## Setup

Requires Python 3.11+, `uv`, and `pandoc` (`brew install pandoc`).

```
uv venv
uv pip install -e .
```

## How extraction works

Clarify does **not** call the Anthropic API. Extraction runs inside Claude Code: you say "extract claims from 2301.12345," Claude Code runs `clarify fetch`, reads the parsed paper, follows `clarify/prompts/extract_claims.md`, writes JSON, and runs `clarify ingest`. The server only renders already-cached papers.

## Run the reader

```
uv run uvicorn clarify.main:app --reload
```

Open `http://localhost:8000`.

## Eval

```
uv run python eval/run_eval.py
```

Targets: ≥85% precision, ≥70% recall.

See [SPEC.md](SPEC.md) for the full design.
