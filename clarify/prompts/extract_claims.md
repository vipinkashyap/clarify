# Extracting claims from a paper

You (Claude Code) are the extraction engine for Clarify. This document describes
how to turn a parsed paper into a structured claims JSON file. You read the paper
from `.cache/parsed/<arxiv_id>.json`, produce claims, and write them to
`eval/generated/<arxiv_id>.json` (for papers listed under `eval/papers/`) or
`.cache/generated/<arxiv_id>.json` otherwise. Then you run
`clarify ingest <arxiv_id> <path>` to save them into the reading cache.

## What counts as a claim

A claim is a standalone, testable assertion the paper makes. Not every sentence
is a claim. Good test: a reader should be able to disagree with a claim without
needing to read the surrounding paragraph for context.

Five types (`type` field):

- **empirical_result** — "Our method achieves 84.2% on MMLU, outperforming
  baseline X by 3 points." A statement about measured outcomes.
- **methodological_claim** — "We train for 1M steps with AdamW at lr=3e-4."
  A statement about what was *done* — choices, procedures, design. These are
  often load-bearing for reproducibility.
- **theoretical_claim** — "Under assumptions A1–A3, gradient descent converges
  to a stationary point in O(1/ε²) steps." A statement the paper proves or
  claims to prove, mathematically or formally.
- **background_claim** — "Transformers struggle with long-range dependencies."
  A statement the paper presents as already known in the field. Usually cited.
- **limitation** — "Our approach assumes i.i.d. data; it does not extend to
  streaming settings." A statement about what the paper does *not* establish
  or where it breaks. Authors typically concentrate these in a "Limitations"
  section but they also surface mid-paper ("however...", "one caveat...").

## Hedging

How strongly the authors assert the claim (`hedging` field):

- **asserted** — declarative, no softeners. "Our model outperforms X."
- **suggested** — softened but positive. "This suggests that...", "We believe...",
  "Likely due to..."
- **speculated** — explicitly tentative. "It may be the case that...",
  "One hypothesis is...", "Future work could investigate..."

When in doubt, go one level weaker. Over-hedging is a smaller error than
over-asserting.

## Extraction rules

1. **Verbatim or near-verbatim `statement`.** Prefer the author's exact words.
   You may lightly resolve pronouns ("the model" → "GPT-4") and expand
   abbreviations on first use per section. Do not paraphrase style, tone, or
   content. If you can't preserve the claim without paraphrasing, skip it.

2. **No invention.** If the paper doesn't say something, don't add it. Don't
   combine two sentences into a synthesized super-claim.

3. **Err toward fewer, cleaner claims.** A precise 20 beats a noisy 50. If a
   sentence isn't really a claim (transitions, section previews, motivational
   throat-clearing), leave it out.

4. **One claim per discrete assertion.** A sentence like "X achieves 84% on A
   and 71% on B" is typically *two* empirical claims unless the joint
   comparison is itself the point.

5. **Resolve citations to short reference keys.** `[12]` → `ref-12`. Inline
   author-year `(Smith et al., 2023)` → `smith-2023` or keep the verbatim form
   if disambiguation is hard. Put these in `dependencies`.

6. **`evidence`** — if the claim is directly supported elsewhere in the paper
   (a figure, a table, a theorem, a cited work), put a short locator there
   ("Table 2", "Theorem 3.1", "Figure 4"). Leave null otherwise. Don't
   invent evidence.

7. **`dependencies`** — claim IDs or citation keys that this claim leans on.
   Example: an empirical result that depends on a methodological setup → list
   the methodological claim's `id`. A background claim may depend on a cited
   reference key.

8. **`char_start` / `char_end`** — character offsets into the `text` field of
   the `Section` the claim belongs to (0-indexed, half-open). These are used
   to render the inline annotation overlay. They must bound the original
   verbatim passage, not your rewritten `statement`.

9. **Claim IDs** — stable and descriptive: `<section-slug>-<index>`, e.g.
   `results-03`, `method-01`, `limitations-02`. Keep them unique within the
   paper.

## Sections to skip

- References / bibliography
- Acknowledgments
- Pure-math appendices with no natural-language claims (include the theorem
  statements themselves as theoretical claims, but skip the proof chains)
- Tables that are only numbers (but DO extract the claims those numbers support
  from the surrounding prose)
- Algorithm listings (skip the pseudocode; extract claims the surrounding
  prose makes about what the algorithm achieves)

## Output format

A single JSON file:

```json
{
  "arxiv_id": "2301.12345",
  "claims": [
    {
      "id": "intro-01",
      "statement": "Transformer architectures dominate language modeling benchmarks.",
      "type": "background_claim",
      "evidence": null,
      "dependencies": ["vaswani-2017"],
      "hedging": "asserted",
      "section": "Introduction",
      "char_start": 142,
      "char_end": 201
    },
    ...
  ]
}
```

The `section` field must match a `section.title` from the parsed paper exactly
(or be a case-insensitive match) — the renderer uses it to locate the host
section for the annotation.

## Workflow

1. `clarify fetch <arxiv_id>` (skip if `.cache/parsed/<id>.json` already exists).
2. Read `.cache/parsed/<arxiv_id>.json` and `clarify/prompts/extract_claims.md`.
3. Work through the paper section by section. For each section, decide what is
   a claim and what isn't. Aim for 15–40 claims total on a typical 10-page
   paper; fewer is fine, more than ~60 almost always means you're picking up
   noise.
4. Write the output JSON to `eval/generated/<id>.json` (if the paper is in the
   eval set) or `.cache/generated/<id>.json`.
5. `clarify ingest <arxiv_id> <path>`. Confirm with `clarify info <arxiv_id>`.

## Iteration

When eval shows misses, update *this document* with the refined rule, then
re-run extraction on the affected papers. Prompt iteration is conversational:
"you're missing limitations where the hedge word is 'however' at the start of
a clause — update the prompt doc." Do that, re-extract, re-eval.
