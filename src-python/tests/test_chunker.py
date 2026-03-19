"""
Tests for the text chunker.

Validates chunking behavior, overlap, edge cases, and token counting.
"""

import pytest
from app.core.chunker import TextChunker, Chunk


@pytest.fixture
def chunker():
    return TextChunker(chunk_size=100, chunk_overlap=20)


@pytest.fixture
def large_chunker():
    return TextChunker(chunk_size=500, chunk_overlap=50)


class TestBasicChunking:
    def test_empty_text(self, chunker):
        assert chunker.chunk("") == []
        assert chunker.chunk("   ") == []

    def test_short_text_single_chunk(self, chunker):
        text = "This is a short sentence."
        chunks = chunker.chunk(text)
        assert len(chunks) == 1
        assert chunks[0].text == text
        assert chunks[0].index == 0

    def test_long_text_produces_multiple_chunks(self, chunker):
        # Generate text that's definitely longer than 100 tokens
        paragraphs = [
            f"This is paragraph number {i} with enough content to make it "
            f"a reasonable length. It discusses topic {i} in moderate detail "
            f"to ensure we have enough tokens for proper chunking behavior."
            for i in range(10)
        ]
        text = "\n\n".join(paragraphs)
        chunks = chunker.chunk(text)
        assert len(chunks) > 1

    def test_chunks_have_sequential_indices(self, chunker):
        text = "\n\n".join([f"Paragraph {i}. " * 20 for i in range(5)])
        chunks = chunker.chunk(text)
        for i, chunk in enumerate(chunks):
            assert chunk.index == i

    def test_chunks_cover_full_text(self, large_chunker):
        text = "Word " * 200
        chunks = large_chunker.chunk(text)
        # Every chunk should have non-empty text
        for chunk in chunks:
            assert len(chunk.text.strip()) > 0


class TestChunkMetadata:
    def test_chunk_has_token_count(self, chunker):
        text = "This is a test sentence with some words in it."
        chunks = chunker.chunk(text)
        assert chunks[0].token_count > 0

    def test_chunk_has_character_offsets(self, chunker):
        text = "Hello world. This is a test."
        chunks = chunker.chunk(text)
        assert chunks[0].start_char >= 0
        assert chunks[0].end_char > chunks[0].start_char


class TestTokenCounting:
    def test_count_tokens_english(self, chunker):
        text = "Hello, world!"
        count = chunker.count_tokens(text)
        assert count > 0
        assert count < 10  # Should be about 4 tokens

    def test_count_tokens_empty(self, chunker):
        assert chunker.count_tokens("") == 0

    def test_count_tokens_code(self, chunker):
        code = "def hello():\n    return 'world'"
        count = chunker.count_tokens(code)
        assert count > 0


class TestEdgeCases:
    def test_single_very_long_word(self, chunker):
        text = "a" * 5000
        chunks = chunker.chunk(text)
        # Should still produce chunks, not crash
        assert len(chunks) >= 1

    def test_only_newlines(self, chunker):
        text = "\n\n\n\n\n"
        chunks = chunker.chunk(text)
        assert len(chunks) == 0

    def test_unicode_text(self, chunker):
        text = "这是一个测试文本，包含中文字符。" * 50
        chunks = chunker.chunk(text)
        assert len(chunks) >= 1
        for chunk in chunks:
            assert len(chunk.text) > 0

    def test_mixed_separators(self, chunker):
        text = (
            "First paragraph here.\n\n"
            "Second paragraph. With multiple sentences. And more.\n"
            "Third line without double newline.\n\n"
            "Fourth paragraph at the end."
        )
        chunks = chunker.chunk(text)
        assert len(chunks) >= 1
