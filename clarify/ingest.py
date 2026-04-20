"""Merge Claude-Code-generated claim JSON with parsed paper and save to cache."""

from __future__ import annotations

import json
from pathlib import Path

from clarify.cache import get_paper, load_parsed, save_paper
from clarify.schema import Claim, ClaimsFile, Paper


def ingest_claims(arxiv_id: str, claims_path: Path) -> Paper:
    parsed = load_parsed(arxiv_id)
    if parsed is None:
        raise FileNotFoundError(
            f"parsed paper not found for {arxiv_id}; run `clarify fetch {arxiv_id}` first"
        )

    data = json.loads(Path(claims_path).read_text())
    # Accept either {arxiv_id, claims: [...]} or a bare list of claims.
    if isinstance(data, list):
        claims_file = ClaimsFile(arxiv_id=arxiv_id, claims=data)
    else:
        claims_file = ClaimsFile.model_validate(data)

    if claims_file.arxiv_id != arxiv_id:
        raise ValueError(
            f"claims file arxiv_id {claims_file.arxiv_id!r} does not match {arxiv_id!r}"
        )

    parsed.claims = claims_file.claims
    save_paper(parsed)
    return parsed


def ingest_plain(arxiv_id: str, plain_path: Path) -> Paper:
    """Merge plain-language versions into an already-ingested paper.

    Input shape: {"arxiv_id": ..., "plain": {"<claim_id>": "<plain text>", ...}}
    """
    existing = get_paper(arxiv_id)
    if existing is None:
        raise FileNotFoundError(
            f"paper {arxiv_id} not in cache; run `clarify ingest` first"
        )

    data = json.loads(Path(plain_path).read_text())
    plain_map = data.get("plain") if isinstance(data, dict) else None
    if not isinstance(plain_map, dict):
        raise ValueError("expected {'plain': {claim_id: text, ...}} in plain JSON")

    updated: list[Claim] = []
    for claim in existing.claims:
        if claim.id in plain_map:
            claim = claim.model_copy(update={"plain_language": plain_map[claim.id]})
        updated.append(claim)
    existing.claims = updated
    save_paper(existing)
    return existing
