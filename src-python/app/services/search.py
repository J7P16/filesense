"""
Search service.

Takes a natural language query, embeds it, searches the vector store,
and applies re-ranking heuristics to boost the most relevant results.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import structlog

from app.core.config import settings
from app.core.embeddings import create_provider, EmbeddingProvider
from app.services.store import VectorStore, SearchResult

logger = structlog.get_logger()


@dataclass
class RankedResult:
    """A search result after re-ranking, ready for the frontend."""

    file_path: str
    file_name: str
    file_type: str
    snippet: str          # Best matching chunk text
    similarity: float     # Raw cosine similarity
    final_score: float    # After re-ranking adjustments
    last_modified: float
    chunk_count: int      # How many chunks matched from this file


class SearchService:
    """
    Semantic search with re-ranking.

    Re-ranking heuristics:
      1. Filename match bonus: if the query appears in the filename
      2. Recency boost: recently modified files get a small bonus
      3. Multi-chunk bonus: files with multiple matching chunks rank higher
      4. File type preference: configurable per-query (optional)
    """

    # Weight parameters for re-ranking
    FILENAME_BONUS = 0.40      # Boost if query words appear in filename
    RECENCY_WEIGHT = 0.05      # Max boost for very recent files
    RECENCY_HALFLIFE_DAYS = 30 # Days until recency bonus halves
    MULTI_CHUNK_BONUS = 0.02   # Per additional matching chunk

    def __init__(self, vector_store: VectorStore):
        self._vector_store = vector_store
        self._provider: EmbeddingProvider | None = None

    def _get_provider(self) -> EmbeddingProvider:
        """Lazy-load embedding provider (shared with indexer)."""
        if self._provider is None:
            self._provider = create_provider(
                provider_type=settings.embedding_provider,
                model_name=settings.local_model_name,
                api_key=settings.openai_api_key,
            )
        return self._provider

    def search(
        self,
        query: str,
        top_k: int = 20,
        file_type: str | None = None,
    ) -> list[RankedResult]:
        """
        Execute a semantic search.

        Args:
            query: Natural language search string.
            top_k: Maximum results to return.
            file_type: Optional file extension filter (e.g., ".pdf").

        Returns:
            Ranked list of results, grouped by file.
        """
        if not query.strip():
            return []

        start = time.perf_counter()

        # Embed the query
        provider = self._get_provider()
        query_vector = provider.embed([query])[0]

        # 1. Vector search
        raw_results = self._vector_store.search(
            query_vector=query_vector,
            top_k=top_k * 3,
            min_similarity=settings.min_similarity,
            file_type_filter=file_type,
        )

        # 2. Filename search
        query_words = [w.lower() for w in query.split() if len(w) >= 2]
        filename_results = self._vector_store.search_by_filename(query_words)

        # Merge: add filename results that weren't in vector results
        vector_files = {r.file_path for r in raw_results}
        for fr in filename_results:
            if fr.file_path not in vector_files:
                raw_results.append(fr)

        if not raw_results:
            return []

        # Group by file and pick best chunk per file
        grouped = self._group_by_file(raw_results)

        # Re-rank
        ranked = self._rerank(grouped, query)

        # Sort by final score and truncate
        ranked.sort(key=lambda r: r.final_score, reverse=True)
        ranked = ranked[:top_k]

        elapsed = (time.perf_counter() - start) * 1000
        logger.info(
            "search.completed",
            query=query[:50],
            results=len(ranked),
            elapsed_ms=round(elapsed, 1),
        )

        return ranked

    def _group_by_file(
        self, results: list[SearchResult]
    ) -> dict[str, list[SearchResult]]:
        """Group search results by file path."""
        grouped: dict[str, list[SearchResult]] = {}
        for r in results:
            grouped.setdefault(r.file_path, []).append(r)
        return grouped

    def _rerank(
        self,
        grouped: dict[str, list[SearchResult]],
        query: str,
    ) -> list[RankedResult]:
        """Apply re-ranking heuristics to grouped results."""
        query_lower = query.lower()
        query_words = set(query_lower.split())
        now = time.time()
        ranked = []

        for file_path, chunks in grouped.items():
            # Best chunk (highest raw similarity)
            best = max(chunks, key=lambda c: c.similarity)
            score = best.similarity

            # 1. Filename match bonus
            filename = Path(file_path).stem.lower()
            filename_clean = filename.replace("_", " ").replace("-", " ").replace("(", "").replace(")", "")
            filename_words = set(filename_clean.split())
            overlap = query_words & filename_words
            if overlap:
                bonus = self.FILENAME_BONUS * (len(overlap) / len(query_words))
                score += bonus
            # Extra boost if query is a substring of filename
            query_joined = query_lower.replace(" ", "").replace("_", "")
            filename_joined = filename.replace(" ", "").replace("_", "").replace("-", "")
            if query_joined in filename_joined or filename_joined in query_joined:
                score += 0.35

            # 2. Recency boost (exponential decay)
            age_days = (now - best.last_modified) / 86400
            recency_factor = 0.5 ** (age_days / self.RECENCY_HALFLIFE_DAYS)
            score += self.RECENCY_WEIGHT * recency_factor

            # 3. Multi-chunk bonus
            if len(chunks) > 1:
                score += self.MULTI_CHUNK_BONUS * min(len(chunks) - 1, 5)

            ranked.append(
                RankedResult(
                    file_path=file_path,
                    file_name=Path(file_path).name,
                    file_type=best.file_type,
                    snippet=best.chunk_text[:300],
                    similarity=best.similarity,
                    final_score=min(score, 1.0),  # Cap at 1.0
                    last_modified=best.last_modified,
                    chunk_count=len(chunks),
                )
            )

        return ranked
