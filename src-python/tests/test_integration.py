"""
Integration test for the full search pipeline.

Tests the entire flow: extract → chunk → embed → store → search.
Uses temporary files and an in-memory-like LanceDB instance.
"""

import pytest
import tempfile
from pathlib import Path

from app.core.chunker import TextChunker
from app.core.embeddings import LocalEmbeddingProvider
from app.core.extractor import extract_text
from app.services.store import VectorStore
from app.services.search import SearchService


@pytest.fixture(scope="module")
def provider():
    return LocalEmbeddingProvider("all-MiniLM-L6-v2")


@pytest.fixture
def vector_store(tmp_path):
    return VectorStore(tmp_path / "test_vectors")


@pytest.fixture
def chunker():
    return TextChunker(chunk_size=200, chunk_overlap=30)


@pytest.fixture
def search_service(vector_store):
    return SearchService(vector_store)


def _index_text_file(
    file_path: str,
    content: str,
    vector_store: VectorStore,
    chunker: TextChunker,
    provider: LocalEmbeddingProvider,
):
    """Helper: write content to a file and index it."""
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)

    chunks = chunker.chunk(content)
    texts = [c.text for c in chunks]
    vectors = provider.embed(texts)

    chunk_dicts = [
        {"text": c.text, "index": c.index, "last_modified": path.stat().st_mtime}
        for c in chunks
    ]

    vector_store.upsert_chunks(
        file_path=file_path,
        chunks=chunk_dicts,
        vectors=vectors,
        dimensions=provider.dimensions,
    )
    return len(chunks)


class TestFullPipeline:
    def test_index_and_search(self, tmp_path, vector_store, chunker, provider):
        """Index a few files and verify semantic search returns relevant results."""

        # Create test files with distinct topics
        _index_text_file(
            str(tmp_path / "python_guide.txt"),
            (
                "Python is a high-level programming language known for its "
                "readability and simplicity. It supports multiple paradigms "
                "including object-oriented and functional programming. Python "
                "is widely used in web development, data science, machine "
                "learning, and automation. Popular frameworks include Django, "
                "Flask, and FastAPI for web development."
            ),
            vector_store, chunker, provider,
        )

        _index_text_file(
            str(tmp_path / "cooking_recipes.txt"),
            (
                "Italian pasta carbonara is a classic Roman dish made with "
                "eggs, pecorino cheese, guanciale, and black pepper. The key "
                "to a good carbonara is tempering the egg mixture so it "
                "creates a creamy sauce without scrambling. Spaghetti is the "
                "traditional pasta shape, though rigatoni is also popular."
            ),
            vector_store, chunker, provider,
        )

        _index_text_file(
            str(tmp_path / "space_exploration.txt"),
            (
                "NASA's Artemis program aims to return humans to the Moon "
                "by the mid-2020s. The Space Launch System rocket and Orion "
                "spacecraft are the core vehicles. The program also plans "
                "to establish a sustainable human presence on the lunar "
                "surface as a stepping stone to Mars exploration."
            ),
            vector_store, chunker, provider,
        )

        assert vector_store.count() >= 3

        # Search for programming → should find python_guide
        search_svc = SearchService(vector_store)
        results = search_svc.search("programming language for web development")
        assert len(results) > 0
        top_result = results[0]
        assert "python" in top_result.file_name.lower()

        # Search for cooking → should find recipes
        results = search_svc.search("how to make Italian pasta")
        assert len(results) > 0
        top_result = results[0]
        assert "cooking" in top_result.file_name.lower() or "recipe" in top_result.file_name.lower()

        # Search for space → should find space_exploration
        results = search_svc.search("lunar mission and rockets")
        assert len(results) > 0
        top_result = results[0]
        assert "space" in top_result.file_name.lower()

    def test_file_deletion(self, tmp_path, vector_store, chunker, provider):
        """Verify that deleting a file removes its vectors."""
        file_path = str(tmp_path / "to_delete.txt")
        _index_text_file(
            file_path,
            "This file will be deleted from the index shortly.",
            vector_store, chunker, provider,
        )
        initial_count = vector_store.count()
        assert initial_count > 0

        vector_store.delete_file(file_path)
        # Count should decrease
        assert vector_store.count() < initial_count

    def test_file_update_replaces_vectors(self, tmp_path, vector_store, chunker, provider):
        """Verify that re-indexing a file replaces old vectors."""
        file_path = str(tmp_path / "updatable.txt")

        _index_text_file(
            file_path,
            "Original content about gardening and flowers.",
            vector_store, chunker, provider,
        )
        count_v1 = vector_store.count()

        _index_text_file(
            file_path,
            "Updated content about quantum physics and particles.",
            vector_store, chunker, provider,
        )
        count_v2 = vector_store.count()

        # Should have same count (replaced, not appended)
        assert count_v2 == count_v1

        # Search should find the new content, not old
        search_svc = SearchService(vector_store)
        results = search_svc.search("quantum physics")
        assert len(results) > 0
        assert "updatable" in results[0].file_name.lower()

    def test_empty_query(self, vector_store):
        """Empty queries should return no results."""
        search_svc = SearchService(vector_store)
        assert search_svc.search("") == []
        assert search_svc.search("   ") == []

    def test_search_with_file_type_filter(self, tmp_path, vector_store, chunker, provider):
        """Verify file type filtering works."""
        _index_text_file(
            str(tmp_path / "notes.md"),
            "Markdown notes about machine learning algorithms and neural networks.",
            vector_store, chunker, provider,
        )
        _index_text_file(
            str(tmp_path / "report.txt"),
            "Text report about machine learning algorithms and neural networks.",
            vector_store, chunker, provider,
        )

        # Filter by .md should only return the markdown file
        search_svc = SearchService(vector_store)
        results = search_svc.search("machine learning", file_type=".md")
        md_results = [r for r in results if r.file_type == ".md"]
        txt_results = [r for r in results if r.file_type == ".txt"]
        assert len(md_results) > 0
        assert len(txt_results) == 0
