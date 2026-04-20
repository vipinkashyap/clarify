import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from clarify.schema import Paper


def cache_dir() -> Path:
    root = Path(os.environ.get("CLARIFY_CACHE_DIR", ".cache")).resolve()
    root.mkdir(parents=True, exist_ok=True)
    (root / "parsed").mkdir(exist_ok=True)
    (root / "generated").mkdir(exist_ok=True)
    (root / "source").mkdir(exist_ok=True)
    (root / "figures").mkdir(exist_ok=True)
    return root


def db_path() -> Path:
    return cache_dir() / "clarify.db"


SCHEMA = """
CREATE TABLE IF NOT EXISTS papers (
    arxiv_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    source_type TEXT NOT NULL,
    num_claims INTEGER NOT NULL DEFAULT 0,
    has_plain INTEGER NOT NULL DEFAULT 0,
    paper_json TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def save_paper(paper: Paper) -> None:
    has_plain = any(c.plain_language for c in paper.claims)
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO papers (arxiv_id, title, source_type, num_claims, has_plain, paper_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(arxiv_id) DO UPDATE SET
                title = excluded.title,
                source_type = excluded.source_type,
                num_claims = excluded.num_claims,
                has_plain = excluded.has_plain,
                paper_json = excluded.paper_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                paper.arxiv_id,
                paper.title,
                paper.source_type,
                len(paper.claims),
                1 if has_plain else 0,
                paper.model_dump_json(),
            ),
        )


def get_paper(arxiv_id: str) -> Optional[Paper]:
    with connect() as conn:
        row = conn.execute(
            "SELECT paper_json FROM papers WHERE arxiv_id = ?", (arxiv_id,)
        ).fetchone()
    if not row:
        return None
    return Paper.model_validate_json(row["paper_json"])


def list_papers() -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT arxiv_id, title, source_type, num_claims, has_plain, updated_at
            FROM papers
            ORDER BY updated_at DESC
            """
        ).fetchall()
    return [dict(r) for r in rows]


def parsed_json_path(arxiv_id: str) -> Path:
    return cache_dir() / "parsed" / f"{arxiv_id}.json"


def save_parsed(paper: Paper) -> Path:
    p = parsed_json_path(paper.arxiv_id)
    p.write_text(paper.model_dump_json(indent=2))
    return p


def load_parsed(arxiv_id: str) -> Optional[Paper]:
    p = parsed_json_path(arxiv_id)
    if not p.exists():
        return None
    return Paper.model_validate_json(p.read_text())
