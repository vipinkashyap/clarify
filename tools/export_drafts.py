"""One-shot: convert the build-script CLAIMS lists into draft JSON files.

The first three papers were extracted via hand-written Python build scripts
in .cache/generated/_build_<id>.py; this script imports each one, reshapes
the CLAIMS list into the `DraftClaim` schema (renaming `deps` →
`dependencies`, `plain` → `plain_language`), and writes
extractions/<id>.json. Intended to run once.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / ".cache" / "generated"
OUT_DIR = ROOT / "extractions"
OUT_DIR.mkdir(exist_ok=True)

PAPERS = ["1706.03762", "1810.04805", "1502.03167"]


def load_claims(build_path: Path) -> list[dict]:
    spec = importlib.util.spec_from_file_location("build_mod", build_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {build_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.CLAIMS  # type: ignore[attr-defined]


def to_draft(claims: list[dict]) -> list[dict]:
    out = []
    for c in claims:
        out.append(
            {
                "id": c["id"],
                "statement": c["statement"],
                "type": c["type"],
                "hedging": c["hedging"],
                "section": c["section"],
                "passage": c["passage"],
                "evidence": c.get("evidence"),
                "dependencies": c.get("deps", []),
                "plain_language": c.get("plain"),
            }
        )
    return out


def main() -> int:
    for arxiv_id in PAPERS:
        build = SRC_DIR / f"_build_{arxiv_id}.py"
        if not build.exists():
            print(f"!! {arxiv_id}: no build script at {build}")
            continue
        claims = to_draft(load_claims(build))
        out = OUT_DIR / f"{arxiv_id}.json"
        out.write_text(
            json.dumps(
                {"arxiv_id": arxiv_id, "claims": claims}, indent=2, ensure_ascii=False
            )
        )
        print(f"wrote {out}  ({len(claims)} claims)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
