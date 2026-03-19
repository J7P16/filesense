"""
Performance optimizations for the indexing and search pipelines.

Key optimizations:
  1. Embedding cache — avoids re-embedding unchanged chunks
  2. Batch scheduler — groups small files into efficient embedding batches
  3. Priority queue — indexes recently modified files first
  4. Memory-mapped model — keeps the embedding model warm across requests
"""

from __future__ import annotations

import asyncio
import hashlib
import heapq
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path

import structlog

logger = structlog.get_logger()


# ============================================================================
# Embedding Cache (LRU)
# ============================================================================

class EmbeddingCache:
    """
    LRU cache for embedding vectors, keyed by content hash.

    Avoids re-embedding text chunks that haven't changed.
    Particularly useful during re-indexing when most files are unchanged.

    Memory usage: ~1.5KB per cached embedding (384 floats × 4 bytes).
    Default 50k entries ≈ 75MB — reasonable for a desktop app.
    """

    def __init__(self, max_size: int = 50_000):
        self._cache: OrderedDict[str, list[float]] = OrderedDict()
        self._max_size = max_size
        self._hits = 0
        self._misses = 0

    def _hash_text(self, text: str) -> str:
        """Fast content hash for cache key."""
        return hashlib.md5(text.encode("utf-8")).hexdigest()

    def get(self, text: str) -> list[float] | None:
        """Look up a cached embedding. Returns None on cache miss."""
        key = self._hash_text(text)
        if key in self._cache:
            self._hits += 1
            self._cache.move_to_end(key)  # LRU touch
            return self._cache[key]
        self._misses += 1
        return None

    def put(self, text: str, vector: list[float]) -> None:
        """Store an embedding in the cache."""
        key = self._hash_text(text)
        self._cache[key] = vector
        self._cache.move_to_end(key)

        # Evict oldest entries if over capacity
        while len(self._cache) > self._max_size:
            self._cache.popitem(last=False)

    def get_batch(self, texts: list[str]) -> tuple[list[list[float] | None], list[int]]:
        """
        Look up a batch of texts. Returns:
          - results: list of vectors (None for cache misses)
          - miss_indices: indices of texts that need embedding
        """
        results: list[list[float] | None] = []
        miss_indices: list[int] = []

        for i, text in enumerate(texts):
            cached = self.get(text)
            results.append(cached)
            if cached is None:
                miss_indices.append(i)

        return results, miss_indices

    def put_batch(self, texts: list[str], vectors: list[list[float]]) -> None:
        """Store a batch of embeddings."""
        for text, vector in zip(texts, vectors):
            self.put(text, vector)

    @property
    def hit_rate(self) -> float:
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 0.0

    @property
    def size(self) -> int:
        return len(self._cache)

    def clear(self) -> None:
        self._cache.clear()
        self._hits = 0
        self._misses = 0

    def stats(self) -> dict:
        return {
            "size": self.size,
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self.hit_rate, 3),
        }


# ============================================================================
# Priority Queue for Indexing
# ============================================================================

@dataclass(order=True)
class IndexJob:
    """
    A file indexing job with priority ordering.

    Lower priority number = processed first.
    Priority is based on:
      - File modification recency (recently modified files first)
      - File type (documents before code before config)
    """
    priority: float
    file_path: str = field(compare=False)
    event_type: str = field(compare=False, default="modified")
    enqueued_at: float = field(compare=False, default_factory=time.time)


class PriorityIndexQueue:
    """
    Priority queue for file indexing jobs.

    Processes recently modified files first, and prioritizes
    document types over code files over config files.
    """

    # Lower number = higher priority
    TYPE_PRIORITY = {
        ".pdf": 1, ".docx": 1, ".doc": 1, ".pptx": 1, ".xlsx": 1,
        ".md": 2, ".txt": 2, ".rst": 2,
        ".py": 3, ".js": 3, ".ts": 3, ".java": 3, ".go": 3, ".rs": 3,
        ".json": 4, ".yaml": 4, ".toml": 4, ".xml": 4,
        ".csv": 2, ".tsv": 2,
    }

    def __init__(self):
        self._heap: list[IndexJob] = []
        self._seen: set[str] = set()  # Dedup: only one job per file path
        self._lock = asyncio.Lock()

    async def put(self, file_path: str, event_type: str = "modified") -> None:
        """Add a file to the index queue with computed priority."""
        async with self._lock:
            if file_path in self._seen:
                return  # Already queued

            path = Path(file_path)
            type_weight = self.TYPE_PRIORITY.get(path.suffix.lower(), 5)

            # Recency weight: modified in last hour = 0, older = higher number
            try:
                age_hours = (time.time() - path.stat().st_mtime) / 3600
            except OSError:
                age_hours = 1000  # File gone, low priority

            priority = type_weight + min(age_hours / 24, 10)

            job = IndexJob(priority=priority, file_path=file_path, event_type=event_type)
            heapq.heappush(self._heap, job)
            self._seen.add(file_path)

    async def get(self) -> IndexJob | None:
        """Get the highest-priority job, or None if empty."""
        async with self._lock:
            if not self._heap:
                return None
            job = heapq.heappop(self._heap)
            self._seen.discard(job.file_path)
            return job

    @property
    def size(self) -> int:
        return len(self._heap)

    @property
    def is_empty(self) -> bool:
        return len(self._heap) == 0


# ============================================================================
# Batch Scheduler
# ============================================================================

class BatchScheduler:
    """
    Groups texts into efficient batches for embedding.

    Instead of embedding one file's chunks at a time, this collects
    chunks from multiple files and submits them in optimal-sized batches.
    This improves GPU/MPS utilization and reduces per-call overhead.
    """

    def __init__(self, batch_size: int = 64, flush_interval: float = 1.0):
        self._batch_size = batch_size
        self._flush_interval = flush_interval
        self._pending: list[tuple[str, list[str]]] = []  # (file_path, chunks)
        self._total_chunks = 0
        self._lock = asyncio.Lock()

    async def add(self, file_path: str, chunks: list[str]) -> None:
        """Add chunks from a file to the pending batch."""
        async with self._lock:
            self._pending.append((file_path, chunks))
            self._total_chunks += len(chunks)

    async def should_flush(self) -> bool:
        """Check if we have enough chunks to justify an embedding call."""
        return self._total_chunks >= self._batch_size

    async def flush(self) -> list[tuple[str, list[str]]]:
        """Return and clear all pending items."""
        async with self._lock:
            items = self._pending
            self._pending = []
            self._total_chunks = 0
            return items

    @property
    def pending_count(self) -> int:
        return self._total_chunks


# ============================================================================
# Search Result Cache
# ============================================================================

class SearchCache:
    """
    Short-lived cache for search results.

    Caches the last N queries for instant repeat lookups.
    Entries expire after ttl_seconds to reflect index changes.
    """

    def __init__(self, max_size: int = 100, ttl_seconds: float = 30.0):
        self._cache: OrderedDict[str, tuple[float, list]] = OrderedDict()
        self._max_size = max_size
        self._ttl = ttl_seconds

    def get(self, query: str) -> list | None:
        """Look up cached results for a query."""
        key = query.strip().lower()
        if key in self._cache:
            ts, results = self._cache[key]
            if time.time() - ts < self._ttl:
                self._cache.move_to_end(key)
                return results
            else:
                del self._cache[key]
        return None

    def put(self, query: str, results: list) -> None:
        """Cache search results."""
        key = query.strip().lower()
        self._cache[key] = (time.time(), results)
        self._cache.move_to_end(key)

        while len(self._cache) > self._max_size:
            self._cache.popitem(last=False)

    def invalidate(self) -> None:
        """Clear all cached results (call after index changes)."""
        self._cache.clear()
