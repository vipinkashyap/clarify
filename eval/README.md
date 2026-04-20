# Eval

Five hand-annotated arxiv papers, compared against Claude-Code-generated claims.

## Layout

- `papers/` — one file per paper, `<arxiv_id>.txt`, containing just the arxiv id (one per line is also fine). This is the list `run_eval.py` iterates over.
- `annotations/<arxiv_id>.json` — hand-annotated ground truth, same schema as `ClaimsFile`.
- `generated/<arxiv_id>.json` — Claude-Code-produced extraction. Gitignored.

## Running

```
python eval/run_eval.py
```

Reports precision / recall per paper and aggregate, broken down by claim type.
Match criterion: verbatim statement overlap OR `difflib.SequenceMatcher` ratio
≥ 0.6 against any ground-truth claim.

Targets: **≥85% precision, ≥70% recall** aggregated.

## Iterating the prompt

When eval shows misses, update `clarify/prompts/extract_claims.md`
conversationally in Claude Code and re-run extraction on the affected papers.
The prompt doc is the source of truth — the repo never calls the Anthropic API.
