---
name: clarify-extract
description: Extract research-paper claims from an arxiv id for the Clarify reader. Trigger when the user asks to extract claims, ingest a paper, or add a paper to Clarify (e.g. "extract claims from 2301.12345", "add arxiv 2010.11929 to clarify"). Produces a draft-claims JSON, runs the Clarify CLI to fill in offsets and ingest into the local reader cache, then prompts for plain-language generation.
---

# Clarify — claim extraction skill

You are acting as the extraction engine for Clarify. Given an arxiv id, your job
is to turn the paper into structured, inline claims that the Clarify reader can
surface.

## Setup assumptions

- CWD is the Clarify repo root (has `clarify/`, `pyproject.toml`).
- The `clarify` CLI is installed (from `uv pip install -e .`).
- `pandoc` is on PATH. For some papers the LaTeX source won't parse and the CLI
  falls back to PDF automatically — handle either.

If the CLI is missing, stop and tell the user to run `uv pip install -e .`
first.

## Workflow

### 1. Fetch

```bash
clarify fetch <arxiv_id>
```

This downloads the source, parses it, and writes `.cache/parsed/<id>.json`.
If the file already exists from a prior fetch, skip this step.

### 2. Read the paper

Read `.cache/parsed/<arxiv_id>.json`. The fields you care about:

- `title`, `authors`, `abstract` — context
- `sections`: list of `{title, level, text, html}`. **Always extract claims
  against `section.text`** (not html).

Also read `clarify/prompts/extract_claims.md` once — that's the definition
document for what a claim is, what counts for each `ClaimType` and `Hedging`
level, and the quality rules.

### 3. Draft the claims

Produce a draft JSON at `.cache/generated/<arxiv_id>.draft.json`:

```json
{
  "arxiv_id": "<id>",
  "claims": [
    {
      "id": "<section-slug>-<NN>",
      "statement": "<near-verbatim; pronouns may be resolved>",
      "type": "empirical_result | methodological_claim | theoretical_claim | background_claim | limitation",
      "hedging": "asserted | suggested | speculated",
      "section": "<must match a section.title exactly>",
      "passage": "<verbatim substring of section.text for this claim>",
      "evidence": "<Table 2 / Figure 3 / null>",
      "dependencies": ["<other-claim-id or reference-key>"],
      "plain_language": "<one-sentence rewrite for a non-expert reader>"
    }
  ]
}
```

**Quality rules** (the detailed version is in `clarify/prompts/extract_claims.md`):

- `passage` must be a verbatim substring of `section.text`. The tool uses this
  to locate the claim inline; if the passage doesn't match, the claim is
  silently dropped.
- `statement` may be lightly edited (pronouns, acronyms) but should stay close
  to the author's wording.
- `plain_language`: write like a Medium article — friendly, one sentence
  preferred, avoid jargon when possible, keep the technical fact. If the claim
  follows a lead-in clause in the body ("On the WMT 2014 English-to-German
  translation task, *the big Transformer outperforms...*"), write the plain
  version so it flows naturally after the lead-in (lowercase first letter is
  fine).
- Aim for **15–30 claims** on a typical 10-page paper. Fewer, cleaner beats
  more, noisy. Skip references, acknowledgments, pure-math appendices.
- Every `section` must match a section title from the parsed paper **exactly**.

### 4. Build + ingest

```bash
clarify build-claims <arxiv_id> .cache/generated/<arxiv_id>.draft.json
```

This:
- resolves each `passage` to `char_start` / `char_end` offsets
- writes `.cache/generated/<arxiv_id>.json` and `.cache/generated/<arxiv_id>.plain.json`
- ingests both into the reading cache (SQLite + live at `localhost:8000`)

If the command reports misses, open the draft, check the passages against the
parsed section text, and re-run.

### 5. Verify

```bash
clarify info <arxiv_id>
```

Expected: `claims: 15–30`, `plain_lang: N/N`. If counts look wrong, iterate.

## On eval papers vs ad-hoc papers

- Ad-hoc: drafts + generated go to `.cache/generated/` (gitignored).
- Eval papers (listed in `eval/papers/`): after a successful extraction, copy
  `.cache/generated/<id>.json` → `eval/generated/<id>.json` and run
  `python eval/run_eval.py` to check P/R against the hand-annotated ground
  truth in `eval/annotations/`.

## When to iterate this skill

If extraction quality is off in a consistent way (e.g. you keep missing a
certain class of limitations, or your plain-language rewrites keep reading
too academic), update `clarify/prompts/extract_claims.md` conversationally
with the user — the prompt doc is the source of truth.
