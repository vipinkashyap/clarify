"""Compare generated claims against hand-annotated ground truth."""

from __future__ import annotations

import json
import sys
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).parent
PAPERS = ROOT / "papers"
ANNOTATIONS = ROOT / "annotations"
GENERATED = ROOT / "generated"

MATCH_THRESHOLD = 0.6


def _norm(s: str) -> str:
    return " ".join(s.lower().split())


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, _norm(a), _norm(b)).ratio()


def _best_match(target: str, candidates: Iterable[dict]) -> tuple[dict | None, float]:
    best: dict | None = None
    best_score = 0.0
    for c in candidates:
        s = _similarity(target, c["statement"])
        if s > best_score:
            best, best_score = c, s
    return best, best_score


def _load_claims(path: Path) -> list[dict]:
    data = json.loads(path.read_text())
    if isinstance(data, list):
        return data
    return data["claims"]


def _arxiv_ids() -> list[str]:
    if not PAPERS.exists():
        return []
    ids: list[str] = []
    for p in sorted(PAPERS.iterdir()):
        if p.is_file() and p.suffix in ("", ".txt"):
            ids.extend(
                line.strip() for line in p.read_text().splitlines() if line.strip()
            )
    # Also accept a simple "one file per id" convention.
    for p in sorted(PAPERS.iterdir()):
        if p.is_file() and p.stem and p.stem not in ids and p.suffix in ("", ".txt"):
            ids.append(p.stem)
    # Dedupe preserving order
    seen: set[str] = set()
    out: list[str] = []
    for i in ids:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


def evaluate_paper(arxiv_id: str) -> dict:
    ann_path = ANNOTATIONS / f"{arxiv_id}.json"
    gen_path = GENERATED / f"{arxiv_id}.json"
    if not ann_path.exists() or not gen_path.exists():
        return {
            "arxiv_id": arxiv_id,
            "missing": {
                "annotations": not ann_path.exists(),
                "generated": not gen_path.exists(),
            },
        }
    truth = _load_claims(ann_path)
    generated = _load_claims(gen_path)

    matched_truth: set[int] = set()
    precision_hits = 0
    by_type_hit: dict[str, int] = {}
    by_type_total: dict[str, int] = {}

    # Precision: for each generated claim, does it match any truth claim?
    for g in generated:
        t = g.get("type", "unknown")
        by_type_total[t] = by_type_total.get(t, 0) + 1
        best, score = _best_match(g["statement"], truth)
        if best is not None and score >= MATCH_THRESHOLD:
            precision_hits += 1
            by_type_hit[t] = by_type_hit.get(t, 0) + 1
            # Track which truth claim got matched (by position since they have ids).
            matched_truth.add(truth.index(best))

    # Recall: unique truth claims matched at least once.
    recall_hits = len(matched_truth)

    return {
        "arxiv_id": arxiv_id,
        "n_truth": len(truth),
        "n_generated": len(generated),
        "precision": precision_hits / len(generated) if generated else 0.0,
        "recall": recall_hits / len(truth) if truth else 0.0,
        "by_type": {
            t: {
                "generated": by_type_total[t],
                "matched": by_type_hit.get(t, 0),
                "precision": by_type_hit.get(t, 0) / by_type_total[t],
            }
            for t in by_type_total
        },
    }


def main() -> int:
    ids = _arxiv_ids()
    if not ids:
        print("No papers in eval/papers/. Add arxiv ids (one per file, or one per line).")
        return 1

    results = [evaluate_paper(i) for i in ids]
    print(f"{'arxiv_id':>14}  {'truth':>5}  {'gen':>5}  {'P':>6}  {'R':>6}")
    print("-" * 48)
    tot_truth = tot_gen = tot_p_hits = tot_r_hits = 0
    for r in results:
        if r.get("missing"):
            miss = [k for k, v in r["missing"].items() if v]
            print(f"{r['arxiv_id']:>14}  (missing: {','.join(miss)})")
            continue
        print(
            f"{r['arxiv_id']:>14}  {r['n_truth']:>5}  {r['n_generated']:>5}  "
            f"{r['precision']:>5.1%}  {r['recall']:>5.1%}"
        )
        tot_truth += r["n_truth"]
        tot_gen += r["n_generated"]
        tot_p_hits += round(r["precision"] * r["n_generated"])
        tot_r_hits += round(r["recall"] * r["n_truth"])

    if tot_gen and tot_truth:
        print("-" * 48)
        print(
            f"{'aggregate':>14}  {tot_truth:>5}  {tot_gen:>5}  "
            f"{tot_p_hits / tot_gen:>5.1%}  {tot_r_hits / tot_truth:>5.1%}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
