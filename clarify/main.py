"""FastAPI reading server. Serves already-cached papers — never calls an LLM."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from clarify import cache


STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Clarify")


@app.get("/api/papers")
def api_list_papers() -> list[dict]:
    return cache.list_papers()


@app.get("/api/papers/{arxiv_id}")
def api_get_paper(arxiv_id: str) -> JSONResponse:
    paper = cache.get_paper(arxiv_id)
    if paper is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "not_ingested",
                "arxiv_id": arxiv_id,
                "hint": (
                    f"Paper {arxiv_id} hasn't been ingested yet. In Claude Code, run: "
                    f"clarify fetch {arxiv_id}, then extract claims following "
                    f"clarify/prompts/extract_claims.md, then clarify ingest "
                    f"{arxiv_id} <claims_json>."
                ),
            },
        )
    return JSONResponse(paper.model_dump())


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/paper/{arxiv_id}")
def reader(arxiv_id: str) -> FileResponse:
    # Client-side JS reads the id from the URL and fetches /api/papers/{id}.
    return FileResponse(STATIC_DIR / "reader.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
