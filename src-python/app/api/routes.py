"""
API routes for the FileSense sidecar.

These endpoints are called by the Tauri frontend over local HTTP.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Query
from pydantic import BaseModel

from app.services.search import SearchService

router = APIRouter()


# ============================================================================
# Request / Response models
# ============================================================================

class SearchRequest(BaseModel):
    query: str
    top_k: int = 20
    file_type: str | None = None


class SearchResultResponse(BaseModel):
    file_path: str
    file_name: str
    file_type: str
    snippet: str
    similarity: float
    final_score: float
    last_modified: float
    chunk_count: int


class SearchResponse(BaseModel):
    results: list[SearchResultResponse]
    query: str
    elapsed_ms: float


class StatusResponse(BaseModel):
    total_files: int
    indexed_files: int
    total_chunks: int
    failed_files: int
    queue_size: int
    pending_debounce: int
    is_running: bool
    provider: str


# ============================================================================
# Endpoints
# ============================================================================

@router.post("/search", response_model=SearchResponse)
async def search(request: Request, body: SearchRequest):
    """
    Semantic file search.

    Accepts a natural language query and returns ranked file results.
    """
    import time

    start = time.perf_counter()

    # Reuse cached search service instead of creating a new one each time
    if not hasattr(request.app.state, "search_service"):
        vector_store = request.app.state.vector_store
        request.app.state.search_service = SearchService(vector_store)
    search_service = request.app.state.search_service

    results = search_service.search(
        query=body.query,
        top_k=body.top_k,
        file_type=body.file_type,
    )

    elapsed = (time.perf_counter() - start) * 1000

    return SearchResponse(
        results=[
            SearchResultResponse(
                file_path=r.file_path,
                file_name=r.file_name,
                file_type=r.file_type,
                snippet=r.snippet,
                similarity=r.similarity,
                final_score=r.final_score,
                last_modified=r.last_modified,
                chunk_count=r.chunk_count,
            )
            for r in results
        ],
        query=body.query,
        elapsed_ms=round(elapsed, 1),
    )


@router.get("/status", response_model=StatusResponse)
async def status(request: Request):
    """Get current indexing status and statistics."""
    indexer = request.app.state.indexer
    stats = await indexer.get_status()
    return StatusResponse(**stats)


@router.post("/reindex")
async def reindex(request: Request, path: str = Query(...)):
    """Force re-index a specific file or directory."""
    import asyncio
    from pathlib import Path as P

    indexer = request.app.state.indexer
    target = P(path)

    if target.is_file():
        await indexer._index_file(str(target))
        return {"status": "ok", "reindexed": 1}
    elif target.is_dir():
        count = 0
        for f in target.rglob("*"):
            if f.is_file():
                await indexer._index_file(str(f))
                count += 1
        return {"status": "ok", "reindexed": count}

    return {"status": "error", "message": "Path not found"}


@router.get("/health")
async def health():
    """Simple health check for Tauri sidecar management."""
    return {"status": "ok"}
