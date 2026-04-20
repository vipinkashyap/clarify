"""Pre-fetch recent arxiv papers per category for the gallery's Discover view.

Arxiv's API doesn't support browser CORS, so live client-side search is out.
Instead we query at build time (here and via the Pages workflow) and commit
a small JSON the browser loads statically.

The list is tight on purpose — top N per category, nothing exhaustive. The
Discover view is a starting point, not a mirror of arxiv.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import arxiv


CATEGORIES: dict[str, str] = {
    "cs.CL": "NLP",
    "cs.CV": "Vision",
    "cs.LG": "ML",
}
PER_CATEGORY = 12


def _normalize_id(entry_id: str) -> str:
    """http://arxiv.org/abs/2301.12345v3 → 2301.12345."""
    raw = entry_id.rsplit("/", 1)[-1]
    if "v" in raw:
        raw = raw.split("v")[0]
    return raw


def _fetch_category(category: str, limit: int) -> list[dict]:
    client = arxiv.Client(page_size=limit, delay_seconds=3, num_retries=3)
    search = arxiv.Search(
        query=f"cat:{category}",
        max_results=limit,
        sort_by=arxiv.SortCriterion.SubmittedDate,
        sort_order=arxiv.SortOrder.Descending,
    )
    out = []
    for r in client.results(search):
        out.append(
            {
                "arxiv_id": _normalize_id(r.entry_id),
                "title": r.title.strip(),
                "authors": [a.name for a in r.authors][:6],
                "summary": (r.summary or "").strip(),
                "primary_category": r.primary_category,
                "published": r.published.isoformat() if r.published else None,
            }
        )
    return out


def build_discover(
    categories: dict[str, str] = CATEGORIES,
    per_category: int = PER_CATEGORY,
    ingested: Iterable[str] = (),
) -> dict:
    """Fetch recent papers for each category and return the Discover payload."""
    ingested_set = set(ingested)
    groups = []
    for cat_code, cat_label in categories.items():
        papers = _fetch_category(cat_code, per_category)
        groups.append(
            {
                "code": cat_code,
                "label": cat_label,
                "papers": [
                    {**p, "ingested": p["arxiv_id"] in ingested_set} for p in papers
                ],
            }
        )
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "groups": groups,
    }


def write_discover_json(path: Path, ingested: Iterable[str] = ()) -> dict:
    payload = build_discover(ingested=ingested)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    return payload
