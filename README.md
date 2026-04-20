# Clarify

Single-paper claim extractor with an adaptive reading overlay. You hand an arxiv id to Claude Code; it writes claim JSON into a local cache; you open `localhost:8000` and read the paper with inline annotations.

## Setup

Requires Python 3.11+, `uv`, and `pandoc` (`brew install pandoc`).

```
uv venv
uv pip install -e .
```

## How extraction works

Clarify does **not** call the Anthropic API. Extraction runs inside your Claude Code session — on your subscription — via a bundled skill.

In a Claude Code session opened in this repo, just say:

> extract claims from 2010.11929

The [`clarify-extract` skill](.claude/skills/clarify-extract/SKILL.md) tells Claude Code how to: run `clarify fetch`, read the parsed sections, produce a draft (structured near-verbatim passages + plain-language rewrites), run `clarify build-claims` to resolve offsets and ingest into the local reader, then verify with `clarify info`. The reader at `localhost:8000` reflects the new paper as soon as ingest finishes.

You don't have to memorize the CLI. The skill drives it.

## Run the reader

```
uv run uvicorn clarify.main:app --reload
```

Open `http://localhost:8000`. Cards for every ingested paper; click to read in plain English by default, toggle to the authors' words.

## Eval

```
uv run python eval/run_eval.py
```

Targets: ≥85% precision, ≥70% recall.

See [SPEC.md](SPEC.md) for the full design.
