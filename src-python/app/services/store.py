"""
Storage layer: LanceDB for vectors, SQLite for metadata.

LanceDB handles all vector operations (insert, search, delete).
SQLite tracks file metadata, indexing state, and user preferences.
Both are embedded — no servers, no config, just files on disk.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import aiosqlite
import lancedb
import pyarrow as pa
import structlog

logger = structlog.get_logger()


# ============================================================================
# Vector Store (LanceDB)
# ============================================================================

@dataclass
class SearchResult:
    """A single search result with metadata."""
    file_path: str
    chunk_text: str
    chunk_index: int
    similarity: float
    file_type: str
    last_modified: float


class VectorStore:
    """
    LanceDB-backed vector storage and similarity search.

    Each chunk is stored as a row with:
      - vector: the embedding
      - file_path: source file
      - chunk_text: the text content
      - chunk_index: position within the file
      - file_type: extension
      - last_modified: file mtime
    """

    TABLE_NAME = "file_chunks"

    def __init__(self, db_path: Path):
        self._db = lancedb.connect(str(db_path))
        self._table = None
        logger.info("vectorstore.connected", path=str(db_path))

    def _get_or_create_table(self, dimensions: int) -> lancedb.table.Table:
        """Get existing table or create with the right schema."""
        if self._table is not None:
            return self._table

        if self.TABLE_NAME in self._db.table_names():
            self._table = self._db.open_table(self.TABLE_NAME)
        else:
            schema = pa.schema([
                pa.field("vector", pa.list_(pa.float32(), dimensions)),
                pa.field("file_path", pa.string()),
                pa.field("chunk_text", pa.string()),
                pa.field("chunk_index", pa.int32()),
                pa.field("file_type", pa.string()),
                pa.field("last_modified", pa.float64()),
            ])
            self._table = self._db.create_table(self.TABLE_NAME, schema=schema)
            logger.info("vectorstore.table_created", dimensions=dimensions)

        return self._table

    def upsert_chunks(
        self,
        file_path: str,
        chunks: list[dict],
        vectors: list[list[float]],
        dimensions: int,
    ) -> int:
        """
        Insert or replace all chunks for a given file.

        Args:
            file_path: The source file path.
            chunks: List of chunk metadata dicts (text, index, etc.).
            vectors: Corresponding embedding vectors.
            dimensions: Vector dimensionality (for table creation).

        Returns:
            Number of chunks upserted.
        """
        table = self._get_or_create_table(dimensions)

        # Delete existing chunks for this file (replacement strategy)
        try:
            table.delete(f'file_path = "{file_path}"')
        except Exception:
            pass  # Table might be empty on first insert

        # Build rows
        rows = []
        for chunk, vector in zip(chunks, vectors):
            rows.append({
                "vector": vector,
                "file_path": file_path,
                "chunk_text": chunk["text"],
                "chunk_index": chunk["index"],
                "file_type": Path(file_path).suffix.lower(),
                "last_modified": chunk.get("last_modified", time.time()),
            })

        if rows:
            table.add(rows)

        return len(rows)

    def search(
        self,
        query_vector: list[float],
        top_k: int = 20,
        min_similarity: float = 0.25,
        file_type_filter: str | None = None,
    ) -> list[SearchResult]:
        """
        Search for similar chunks using cosine similarity.

        Args:
            query_vector: The query embedding.
            top_k: Maximum number of results.
            min_similarity: Minimum cosine similarity threshold.
            file_type_filter: Optional filter by file extension.

        Returns:
            Ranked list of SearchResult objects.
        """
        if self._table is None:
            if self.TABLE_NAME not in self._db.table_names():
                return []
            self._table = self._db.open_table(self.TABLE_NAME)

        query = self._table.search(query_vector).limit(top_k).metric("cosine")

        if file_type_filter:
            query = query.where(f'file_type = "{file_type_filter}"')

        results = query.to_pandas()

        search_results = []
        for _, row in results.iterrows():
            # LanceDB returns _distance (lower = more similar for cosine)
            similarity = 1 - row.get("_distance", 0)
            if similarity >= min_similarity:
                search_results.append(
                    SearchResult(
                        file_path=row["file_path"],
                        chunk_text=row["chunk_text"],
                        chunk_index=row["chunk_index"],
                        similarity=similarity,
                        file_type=row["file_type"],
                        last_modified=row["last_modified"],
                    )
                )

        return search_results

    def delete_file(self, file_path: str) -> None:
        """Remove all chunks for a file."""
        if self._table is not None:
            try:
                self._table.delete(f'file_path = "{file_path}"')
            except Exception:
                pass

    def count(self) -> int:
        """Total number of indexed chunks."""
        if self._table is None:
            if self.TABLE_NAME not in self._db.table_names():
                return 0
            self._table = self._db.open_table(self.TABLE_NAME)
        return self._table.count_rows()
    
    def search_by_filename(self, query_words: list[str]) -> list[SearchResult]:
        """
        Find files whose paths contain any of the query words.
        Returns the first chunk of each matching file.
        """
        if self._table is None:
            if self.TABLE_NAME not in self._db.table_names():
                return []
            self._table = self._db.open_table(self.TABLE_NAME)

        try:
            df = self._table.to_pandas()
        except Exception:
            return []

        results = []
        seen_files: set[str] = set()

        for _, row in df.iterrows():
            file_path = row["file_path"]
            if file_path in seen_files:
                continue

            filename_lower = Path(file_path).stem.lower().replace("_", " ").replace("-", " ")
            matched = any(w in filename_lower for w in query_words)

            if matched:
                seen_files.add(file_path)
                results.append(
                    SearchResult(
                        file_path=file_path,
                        chunk_text=row["chunk_text"][:300],
                        chunk_index=row["chunk_index"],
                        similarity=0.5,
                        file_type=row["file_type"],
                        last_modified=row["last_modified"],
                    )
                )

        return results


# ============================================================================
# Metadata Store (SQLite)
# ============================================================================

class MetadataStore:
    """
    SQLite-backed metadata storage.

    Tracks:
      - File registry (path, hash, last indexed time)
      - Indexing state (pending, processing, completed, failed)
      - User preferences
    """

    def __init__(self, db: aiosqlite.Connection):
        self._db = db

    @classmethod
    async def create(cls, db_path: Path) -> MetadataStore:
        """Create a new MetadataStore, initializing the schema."""
        db = await aiosqlite.connect(str(db_path))
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA synchronous=NORMAL")

        await db.executescript("""
            CREATE TABLE IF NOT EXISTS files (
                path        TEXT PRIMARY KEY,
                size_bytes  INTEGER NOT NULL,
                content_hash TEXT NOT NULL,
                last_modified REAL NOT NULL,
                last_indexed REAL NOT NULL,
                chunk_count INTEGER DEFAULT 0,
                status      TEXT DEFAULT 'completed',
                error       TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_files_status
                ON files(status);

            CREATE INDEX IF NOT EXISTS idx_files_modified
                ON files(last_modified);

            CREATE TABLE IF NOT EXISTS preferences (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        """)
        await db.commit()

        return cls(db)

    async def get_file(self, path: str) -> dict | None:
        """Get file metadata by path."""
        async with self._db.execute(
            "SELECT * FROM files WHERE path = ?", (path,)
        ) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return None
            cols = [d[0] for d in cursor.description]
            return dict(zip(cols, row))

    async def upsert_file(
        self,
        path: str,
        size_bytes: int,
        content_hash: str,
        last_modified: float,
        chunk_count: int = 0,
        status: str = "completed",
        error: str | None = None,
    ) -> None:
        """Insert or update file metadata."""
        await self._db.execute(
            """
            INSERT INTO files (path, size_bytes, content_hash, last_modified,
                               last_indexed, chunk_count, status, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                size_bytes = excluded.size_bytes,
                content_hash = excluded.content_hash,
                last_modified = excluded.last_modified,
                last_indexed = excluded.last_indexed,
                chunk_count = excluded.chunk_count,
                status = excluded.status,
                error = excluded.error
            """,
            (path, size_bytes, content_hash, last_modified, time.time(),
             chunk_count, status, error),
        )
        await self._db.commit()

    async def delete_file(self, path: str) -> None:
        """Remove file metadata."""
        await self._db.execute("DELETE FROM files WHERE path = ?", (path,))
        await self._db.commit()

    async def needs_reindex(self, path: str, content_hash: str) -> bool:
        """Check if a file needs re-indexing based on content hash."""
        existing = await self.get_file(path)
        if existing is None:
            return True
        return existing["content_hash"] != content_hash

    async def get_stats(self) -> dict:
        """Get indexing statistics."""
        stats = {}
        async with self._db.execute("SELECT COUNT(*) FROM files") as c:
            stats["total_files"] = (await c.fetchone())[0]
        async with self._db.execute(
            "SELECT COUNT(*) FROM files WHERE status = 'completed'"
        ) as c:
            stats["indexed_files"] = (await c.fetchone())[0]
        async with self._db.execute(
            "SELECT SUM(chunk_count) FROM files WHERE status = 'completed'"
        ) as c:
            row = await c.fetchone()
            stats["total_chunks"] = row[0] or 0
        async with self._db.execute(
            "SELECT COUNT(*) FROM files WHERE status = 'failed'"
        ) as c:
            stats["failed_files"] = (await c.fetchone())[0]
        return stats

    async def close(self) -> None:
        """Close the database connection."""
        await self._db.close()
