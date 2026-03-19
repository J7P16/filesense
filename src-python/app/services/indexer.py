"""
Background indexing service.

Watches configured directories for file changes and processes them
through the extraction → chunking → embedding → storage pipeline.

Uses an async queue with debouncing to batch rapid file changes
(e.g., saving a file repeatedly while editing).
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import xxhash
import structlog
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent

from app.core.config import settings
from app.core.embeddings import create_provider, EmbeddingProvider
from app.core.extractor import extract_text, ExtractionError
from app.core.chunker import TextChunker
from app.services.store import VectorStore, MetadataStore

logger = structlog.get_logger()


class _FileEventHandler(FileSystemEventHandler):
    """Watchdog handler that feeds file events into an async queue."""

    def __init__(self, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
        self._queue = queue
        self._loop = loop

    def on_created(self, event: FileSystemEvent):
        if not event.is_directory:
            self._loop.call_soon_threadsafe(self._queue.put_nowait, ("created", event.src_path))

    def on_modified(self, event: FileSystemEvent):
        if not event.is_directory:
            self._loop.call_soon_threadsafe(self._queue.put_nowait, ("modified", event.src_path))

    def on_deleted(self, event: FileSystemEvent):
        if not event.is_directory:
            self._loop.call_soon_threadsafe(self._queue.put_nowait, ("deleted", event.src_path))

    def on_moved(self, event: FileSystemEvent):
        if not event.is_directory:
            self._loop.call_soon_threadsafe(self._queue.put_nowait, ("deleted", event.src_path))
            self._loop.call_soon_threadsafe(
                self._queue.put_nowait, ("created", event.dest_path)
            )


class IndexingService:
    """
    Manages the full indexing lifecycle:
      1. Initial scan of watched directories
      2. Continuous monitoring via watchdog
      3. Processing pipeline: extract → chunk → embed → store
    """

    def __init__(
        self,
        vector_store: VectorStore,
        metadata_store: MetadataStore,
        watch_dirs: list[Path],
    ):
        self._vector_store = vector_store
        self._metadata_store = metadata_store
        self._watch_dirs = watch_dirs
        self._queue: asyncio.Queue = asyncio.Queue()
        self._observer: Observer | None = None
        self._running = False
        self._chunker = TextChunker(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
        )
        self._provider: EmbeddingProvider | None = None
        self._pending: dict[str, float] = {}  # path -> timestamp for debouncing

    def _get_provider(self) -> EmbeddingProvider:
        """Lazy-load the embedding provider."""
        if self._provider is None:
            self._provider = create_provider(
                provider_type=settings.embedding_provider,
                model_name=settings.local_model_name,
                api_key=settings.openai_api_key,
            )
        return self._provider

    async def start(self) -> None:
        """Start the indexing service."""
        self._running = True
        loop = asyncio.get_event_loop()

        # Start file watcher
        handler = _FileEventHandler(self._queue, loop)
        self._observer = Observer()
        for watch_dir in self._watch_dirs:
            if watch_dir.exists():
                self._observer.schedule(handler, str(watch_dir), recursive=True)
                logger.info("indexer.watching", directory=str(watch_dir))
        self._observer.start()

        # Run initial scan in background
        asyncio.create_task(self._initial_scan())

        # Process queue
        await self._process_queue()

    async def stop(self) -> None:
        """Stop the indexing service gracefully."""
        self._running = False
        if self._observer:
            self._observer.stop()
            self._observer.join()

    async def _initial_scan(self) -> None:
        """Scan all watched directories and index new/changed files."""
        logger.info("indexer.initial_scan.start")
        file_count = 0

        for watch_dir in self._watch_dirs:
            if not watch_dir.exists():
                continue
            for file_path in watch_dir.rglob("*"):
                if not file_path.is_file():
                    continue
                if file_path.suffix.lower() not in settings.supported_extensions:
                    continue
                if self._is_hidden(file_path):
                    continue
                if file_path.stat().st_size > settings.max_file_size_mb * 1024 * 1024:
                    continue

                await self._queue.put(("scan", str(file_path)))
                file_count += 1

        logger.info("indexer.initial_scan.queued", files=file_count)

    async def _process_queue(self) -> None:
        """Main processing loop with debouncing."""
        while self._running:
            try:
                event_type, file_path = await asyncio.wait_for(
                    self._queue.get(), timeout=1.0
                )
            except asyncio.TimeoutError:
                # Flush any debounced items
                await self._flush_pending()
                continue

            if event_type == "deleted":
                await self._handle_delete(file_path)
            else:
                # Debounce: record the latest timestamp
                self._pending[file_path] = time.time()

            # Periodically flush pending items
            if len(self._pending) >= settings.batch_size:
                await self._flush_pending()

    async def _flush_pending(self) -> None:
        """Process all pending files that have been stable for debounce_seconds."""
        now = time.time()
        ready = [
            path
            for path, ts in self._pending.items()
            if now - ts >= settings.debounce_seconds
        ]

        if not ready:
            return

        for path in ready:
            del self._pending[path]
            await self._index_file(path)

    async def _index_file(self, file_path: str) -> None:
        """Run the full indexing pipeline for a single file."""
        path = Path(file_path)

        # Skip checks
        if not path.exists():
            return
        if path.suffix.lower() not in settings.supported_extensions:
            return
        if self._is_hidden(path):
            return

        try:
            # Compute content hash for change detection
            content_hash = self._hash_file(path)

            # Skip if already indexed with same hash
            if not await self._metadata_store.needs_reindex(file_path, content_hash):
                return

            # Extract text
            text = await asyncio.to_thread(extract_text, path)
            if not text:
                logger.debug("indexer.skip.empty", path=file_path)
                return

            # Chunk
            chunks = self._chunker.chunk(text)
            if not chunks:
                return

            # Embed
            provider = self._get_provider()
            texts = [c.text for c in chunks]

            # Process in batches
            all_vectors = []
            for i in range(0, len(texts), settings.batch_size):
                batch = texts[i : i + settings.batch_size]
                vectors = await asyncio.to_thread(provider.embed, batch)
                all_vectors.extend(vectors)

            # Store vectors
            chunk_dicts = [
                {
                    "text": c.text,
                    "index": c.index,
                    "last_modified": path.stat().st_mtime,
                }
                for c in chunks
            ]
            stored = self._vector_store.upsert_chunks(
                file_path=file_path,
                chunks=chunk_dicts,
                vectors=all_vectors,
                dimensions=provider.dimensions,
            )

            # Update metadata
            await self._metadata_store.upsert_file(
                path=file_path,
                size_bytes=path.stat().st_size,
                content_hash=content_hash,
                last_modified=path.stat().st_mtime,
                chunk_count=stored,
                status="completed",
            )

            logger.debug("indexer.indexed", path=file_path, chunks=stored)

        except ExtractionError as e:
            logger.warning("indexer.extraction_failed", path=file_path, error=str(e))
            await self._metadata_store.upsert_file(
                path=file_path,
                size_bytes=path.stat().st_size if path.exists() else 0,
                content_hash="",
                last_modified=path.stat().st_mtime if path.exists() else 0,
                status="failed",
                error=str(e),
            )
        except Exception as e:
            logger.error("indexer.error", path=file_path, error=str(e))

    async def _handle_delete(self, file_path: str) -> None:
        """Remove a deleted file from the index."""
        self._vector_store.delete_file(file_path)
        await self._metadata_store.delete_file(file_path)
        logger.debug("indexer.deleted", path=file_path)

    @staticmethod
    def _hash_file(path: Path) -> str:
        """Compute a fast content hash using xxHash."""
        h = xxhash.xxh64()
        with open(path, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def _is_hidden(path: Path) -> bool:
        """Check if a file should be skipped."""
        skip_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv",
                    ".tox", "dist", "build", ".cache", ".npm", ".cargo",
                    "target", ".Trash", "Library"}
        return any(part.startswith(".") or part in skip_dirs for part in path.parts)

    async def get_status(self) -> dict:
        """Get current indexing status."""
        stats = await self._metadata_store.get_stats()
        stats["queue_size"] = self._queue.qsize()
        stats["pending_debounce"] = len(self._pending)
        stats["is_running"] = self._running
        stats["provider"] = self._get_provider().name if self._provider else "not loaded"
        return stats
