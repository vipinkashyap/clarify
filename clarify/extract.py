"""Helpers for turning a "draft" claim list into Clarify's JSON format.

A *draft* is what a Claude Code session produces while following
`clarify/prompts/extract_claims.md`: a list of claims with a near-verbatim
`passage` pulled from the parsed paper's section text, plus a `statement`
(lightly edited — pronouns resolved, etc.) and a `plain_language` rewrite.
This module fills in the `char_start` / `char_end` offsets by locating the
passage in the section text, produces the two JSON files the reader
consumes (claims + plain-language), and is invoked via `clarify
build-claims <arxiv_id> <draft.json>`.

Keeping this stage in Python (instead of asking Claude to compute offsets)
makes the skill simpler and more reliable: Claude only has to surface the
text it saw, and the offsets follow deterministically.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from clarify.cache import cache_dir, load_parsed
from clarify.schema import ClaimType, Hedging


class DraftClaim(BaseModel):
    """Shape the skill writes. No char offsets — we fill those in."""

    id: str
    statement: str
    type: ClaimType
    hedging: Hedging
    section: str
    passage: str
    evidence: Optional[str] = None
    dependencies: list[str] = Field(default_factory=list)
    plain_language: Optional[str] = None


class Draft(BaseModel):
    arxiv_id: str
    claims: list[DraftClaim]


def _find_offsets(section_text: str, passage: str) -> tuple[int, int]:
    """Locate `passage` in `section_text` tolerant of whitespace differences."""
    idx = section_text.find(passage)
    if idx != -1:
        return idx, idx + len(passage)

    def norm(s: str) -> str:
        return re.sub(r"\s+", " ", s).strip()

    n_text = norm(section_text)
    n_pass = norm(passage)
    n_idx = n_text.find(n_pass)
    if n_idx == -1:
        return -1, -1

    pos = 0
    start: Optional[int] = None
    in_ws = True
    for i, c in enumerate(section_text):
        if c.isspace():
            if not in_ws:
                if pos == n_idx and start is None:
                    start = i
                pos += 1
                in_ws = True
            continue
        if in_ws:
            if pos == n_idx and start is None:
                start = i
            in_ws = False
        pos += 1
        if pos == n_idx + len(n_pass):
            return start if start is not None else 0, i + 1
    return -1, -1


def build_from_draft(draft_path: Path) -> tuple[Path, Path, list[str]]:
    """Resolve passages → offsets and write claims + plain JSON.

    Returns (claims_path, plain_path, misses). Misses are claim ids whose
    `passage` couldn't be located in the parsed paper (usually due to a
    typo — the skill should re-check the section text).
    """
    draft = Draft.model_validate_json(Path(draft_path).read_text())
    paper = load_parsed(draft.arxiv_id)
    if paper is None:
        raise FileNotFoundError(
            f"parsed paper not found for {draft.arxiv_id}; run "
            f"`clarify fetch {draft.arxiv_id}` first"
        )

    sec_texts = {s.title: s.text for s in paper.sections}

    claims_out: list[dict] = []
    plain_out: dict[str, str] = {}
    misses: list[str] = []

    for c in draft.claims:
        sec_text = sec_texts.get(c.section)
        if sec_text is None:
            misses.append(f"{c.id}: section {c.section!r} not in paper")
            continue
        start, end = _find_offsets(sec_text, c.passage)
        if start < 0:
            misses.append(f"{c.id}: passage not found in section {c.section!r}")
            continue
        claims_out.append(
            {
                "id": c.id,
                "statement": c.statement,
                "type": c.type.value,
                "evidence": c.evidence,
                "dependencies": c.dependencies,
                "hedging": c.hedging.value,
                "section": c.section,
                "char_start": start,
                "char_end": end,
            }
        )
        if c.plain_language:
            plain_out[c.id] = c.plain_language

    out_dir = cache_dir() / "generated"
    out_dir.mkdir(parents=True, exist_ok=True)
    claims_path = out_dir / f"{draft.arxiv_id}.json"
    plain_path = out_dir / f"{draft.arxiv_id}.plain.json"

    claims_path.write_text(
        json.dumps(
            {"arxiv_id": draft.arxiv_id, "claims": claims_out},
            indent=2,
            ensure_ascii=False,
        )
    )
    plain_path.write_text(
        json.dumps(
            {"arxiv_id": draft.arxiv_id, "plain": plain_out},
            indent=2,
            ensure_ascii=False,
        )
    )
    return claims_path, plain_path, misses
