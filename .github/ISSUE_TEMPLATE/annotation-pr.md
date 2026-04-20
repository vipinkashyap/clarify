---
name: Annotation double-check
about: Propose ground-truth annotations for an already-extracted paper so we can measure extraction quality
title: "[Annotate] <paper title>"
labels: annotation
---

**arxiv id:** <!-- the paper whose extraction you want to double-check -->

**Process:** read the paper, write an independent list of claims in
`eval/annotations/<arxiv_id>.json` (same schema as the extraction, just
statement + type + section + hedging), then open a PR. `python eval/run_eval.py`
will report precision/recall against the existing extraction.

**Why bother:** this is how we know extraction quality isn't drifting as we
add papers. Aggregate eval numbers land in `docs/coverage.md`.
