# Extract claims for a paper without Claude Code

If you have claude.ai / Claude Desktop (or any other LLM chat) but not Claude
Code, you can still contribute an extraction. The skill just becomes a prompt
you paste into a chat.

## Steps

1. **Fetch the paper locally** (requires `uv pip install -e .`):

   ```
   uv run clarify fetch <arxiv_id>
   ```

   This produces `.cache/parsed/<arxiv_id>.json`.

2. **Get the chat-ready prompt**:

   ```
   uv run clarify prompt <arxiv_id> > prompt.md
   ```

   This assembles the extraction instructions and the parsed paper's sections
   into a single message you can paste into any LLM chat.

3. **Paste it into your LLM chat.** Claude.ai, ChatGPT, Gemini — any model with
   a reasonable context window works. Ask it to follow the instructions and
   produce the JSON.

4. **Save the output** as `extractions/<arxiv_id>.json`. (Look at the
   [existing extractions](../extractions) for shape — just a list of claims
   with `statement`, `type`, `hedging`, `section`, `passage`, `dependencies`,
   and `plain_language`.)

5. **Verify** it ingests cleanly:

   ```
   uv run clarify bootstrap
   uv run clarify info <arxiv_id>
   ```

   If it says `claims: N, plain: N/N` with no passage misses, you're done.

6. **Open a PR** adding `extractions/<arxiv_id>.json`.

## No LLM at all

You can also write the JSON by hand. The [extraction prompt doc](../clarify/prompts/extract_claims.md)
is the definition; follow the schema in the existing extraction files. It's
slower but works.

## Can the reader ingest the JSON directly (without fetching)?

No — the reader needs the parsed paper text to render the body, not just the
claims. But `clarify bootstrap` handles both steps automatically: fetch →
build offsets → ingest.
