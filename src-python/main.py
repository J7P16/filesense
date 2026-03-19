"""
FileSense — Python sidecar entry point.

This FastAPI server runs as a Tauri sidecar process, handling:
  - Semantic search queries
  - Background file indexing
  - Embedding provider management
  - System status and health checks

Communication with the Tauri frontend happens over a local HTTP socket.
"""

import asyncio
from contextlib import asynccontextmanager

import structlog
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router as api_router
from app.core.config import settings
from app.services.indexer import IndexingService
from app.services.store import VectorStore, MetadataStore

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup/shutdown of background services."""
    logger.info("filesense.starting", data_dir=str(settings.data_dir))

    # Initialize stores
    vector_store = VectorStore(settings.data_dir / "vectors")
    metadata_store = await MetadataStore.create(settings.data_dir / "metadata.db")

    # Initialize indexing service
    indexer = IndexingService(
        vector_store=vector_store,
        metadata_store=metadata_store,
        watch_dirs=settings.watch_directories,
    )

    # Store references for dependency injection
    app.state.vector_store = vector_store
    app.state.metadata_store = metadata_store
    app.state.indexer = indexer

    # Preload the embedding model so first search is instant
    from app.services.search import SearchService
    search_service = SearchService(vector_store)
    search_service._get_provider()  # Force model load
    app.state.search_service = search_service

    # Start background indexing
    indexing_task = asyncio.create_task(indexer.start())
    logger.info("filesense.ready")

    yield

    # Graceful shutdown
    logger.info("filesense.shutting_down")
    await indexer.stop()
    indexing_task.cancel()
    await metadata_store.close()


app = FastAPI(
    title="FileSense",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")


if __name__ == "__main__":
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=settings.port,
        log_level="info",
    )
