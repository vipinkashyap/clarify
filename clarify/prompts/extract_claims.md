# Extracting claims from a paper

You (Claude Code, or any other LLM) are the extraction engine for Clarify.
This document describes how to turn a parsed paper into a structured draft
JSON file. You read the paper from `.cache/parsed/<arxiv_id>.json`, produce
a draft at `.cache/generated/<arxiv_id>.draft.json`, then run
`clarify build-claims <arxiv_id> <draft_path>` — that resolves passage
offsets, writes the final claims + plain JSON, and ingests into the reading
cache in one step. The final committed artifact is
`extractions/<arxiv_id>.json` (same shape as the draft).

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

8. **`passage`** — the verbatim substring of `section.text` that this claim
   is pulled from. `clarify build-claims` uses this to compute the character
   offsets for the inline highlight at ingest time; you don't compute offsets
   yourself. If the passage can't be located in `section.text`, the claim is
   silently dropped, so double-check for typos and whitespace normalisation.

9. **Claim IDs** — stable and descriptive: `<section-slug>-<index>`, e.g.
   `results-03`, `method-01`, `limitations-02`. Keep them unique within the
   paper.

## Plain-language rewrites

Every claim has a `plain_language` field. This is the version a
non-expert actually reads — the original statement is only visible via the
"Original" toggle. **Aim to write plain language like a good Medium article**,
not a summary. Voice and examples matter.

- **Write in a voice that connects claim to claim.** Within a paper, claims
  are often part of a narrative — an observation ("RNNs read word-by-word"),
  a problem ("you can't parallelize this"), a fix ("we throw out
  recurrence"). Your plain-language rewrites should read like steps in that
  story, not isolated bullet points. Transitions ("That one change made",
  "Here's a subtle problem", "A third, quieter benefit") are welcome.

- **Concrete examples for math claims.** If a claim involves a formula or a
  constant, include a small worked example. For the attention formula:
  > "Each word asks every other word: how relevant are you? (that's the dot
  > product). Divide by √d_k (if d_k=64, divide by 8) to keep softmax
  > gradients healthy. Then softmax turns the scores into probabilities
  > that sum to 1, and you mix the other words' values by those weights."
  Not just: "Attention is `softmax(QK^T/√d_k) V`."

- **Shorten jargon when possible, keep it when it's load-bearing.** "BLEU"
  stays as "BLEU" — it's the standard translation metric and dodging it
  would be worse. But "monotonic attention" should usually get a one-phrase
  gloss the first time it comes up.

- **Lead-in-aware.** If a claim passage starts mid-sentence (after a lead-in
  like "On the WMT 2014 English-to-German translation task,"), the plain
  rewrite should flow naturally *after* that lead-in, not start a new
  sentence. A lowercase first letter is fine.

- **Hedging shows through.** If a claim is `suggested` or `speculated`, your
  plain-language rewrite must convey that — "maybe," "we think," "could
  work" — not flatten it into a confident assertion.

For the canonical voice, read
[`extractions/1706.03762.json`](../../extractions/1706.03762.json) (Attention
Is All You Need). That paper has had a full editorial pass and is the
template for the others.

## Figure glosses (optional but encouraged)

Papers often have a figure that carries as much meaning as several claims
combined (BERT's overall architecture, ViT's patch-to-token diagram, the
Transformer architecture). When such a figure exists, add it to the draft's
top-level `figures` list:

```json
{
  "figures": [
    {
      "image": "model_scheme.png",
      "plain_language": "Walk-through of the figure..."
    }
  ]
}
```

- `image` is the basename as it appears in the paper's source bundle
  (`model_scheme.png`, not a path).
- `plain_language` should **narrate the figure step by step**, not summarise
  it. "Left tower is the encoder. Six identical blocks. Each one does
  self-attention, then a feed-forward network. Skip connections wrap
  around both." Pretend the reader can't see the figure well.

Two or three glosses for a typical paper is plenty — the architectural
diagrams and the headline results chart. Don't gloss every figure.

## Sections to skip

- References / bibliography
- Acknowledgments
- Pure-math appendices with no natural-language claims (include the theorem
  statements themselves as theoretical claims, but skip the proof chains)
- Tables that are only numbers (but DO extract the claims those numbers support
  from the surrounding prose)
- Algorithm listings (skip the pseudocode; extract claims the surrounding
  prose makes about what the algorithm achieves)

## Output format (draft)

A single JSON file at `.cache/generated/<arxiv_id>.draft.json`:

```json
{
  "arxiv_id": "2301.12345",
  "figures": [
    {
      "image": "model_scheme.png",
      "plain_language": "Step-by-step walk-through of the figure…"
    }
  ],
  "claims": [
    {
      "id": "intro-01",
      "statement": "Transformer architectures dominate language modeling benchmarks.",
      "type": "background_claim",
      "hedging": "asserted",
      "section": "Introduction",
      "passage": "Transformer architectures dominate language modeling benchmarks",
      "evidence": null,
      "dependencies": ["vaswani-2017"],
      "plain_language": "By 2023, pretty much every top language benchmark was headed by a Transformer-based model. It had become the default architecture, the way ResNets were for vision a decade earlier."
    }
  ]
}
```

The `section` field must match a `section.title` from the parsed paper
**exactly** — the build step uses it to locate the host section. `figures` is
optional. The final committed file (`extractions/<arxiv_id>.json`) has the
same shape as the draft.

## Workflow

1. `clarify fetch <arxiv_id>` (skip if `.cache/parsed/<id>.json` already exists).
2. Read `.cache/parsed/<arxiv_id>.json` and this document.
3. Work section by section. Aim for 15–30 claims on a typical 10-page paper;
   fewer is fine, more than ~60 almost always means you're picking up noise.
   Add 2–4 figure glosses for the architectural / headline-result diagrams.
4. Write the draft to `.cache/generated/<arxiv_id>.draft.json`.
5. `clarify build-claims <arxiv_id> <draft_path>` — resolves passage offsets,
   writes the final claim + plain JSON files, and ingests into the reading
   cache. Any passage that can't be located is reported; fix and re-run.
6. Confirm with `clarify info <arxiv_id>` (should show `claims: N` and
   `plain_lang: N/N`).
7. Copy the draft to `extractions/<arxiv_id>.json` and open a PR.

## Iteration

When eval shows misses or the voice slips from essay-like to summary-like,
update *this document* with the refined rule, then re-run extraction on the
affected papers. Prompt iteration is conversational: "you're missing
limitations where the hedge word is 'however' at the start of a clause —
update the prompt doc." Do that, re-extract, re-eval.
