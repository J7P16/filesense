"""
Tests for the embedding providers.

Tests the local provider with the actual model (integration test)
and the provider interface contract.
"""

import pytest
from app.core.embeddings import (
    LocalEmbeddingProvider,
    EmbeddingProvider,
    create_provider,
)


@pytest.fixture(scope="module")
def local_provider():
    """Load the local model once for all tests in this module."""
    return LocalEmbeddingProvider("all-MiniLM-L6-v2")


class TestLocalProvider:
    def test_implements_interface(self, local_provider):
        assert isinstance(local_provider, EmbeddingProvider)

    def test_dimensions(self, local_provider):
        assert local_provider.dimensions == 384

    def test_name(self, local_provider):
        assert "MiniLM" in local_provider.name

    def test_embed_single(self, local_provider):
        vectors = local_provider.embed(["hello world"])
        assert len(vectors) == 1
        assert len(vectors[0]) == 384
        # Vectors should be normalized (unit length)
        magnitude = sum(v**2 for v in vectors[0]) ** 0.5
        assert abs(magnitude - 1.0) < 0.01

    def test_embed_batch(self, local_provider):
        texts = ["first text", "second text", "third text"]
        vectors = local_provider.embed(texts)
        assert len(vectors) == 3
        for v in vectors:
            assert len(v) == 384

    def test_embed_empty_string(self, local_provider):
        vectors = local_provider.embed([""])
        assert len(vectors) == 1
        assert len(vectors[0]) == 384

    def test_similar_texts_have_high_similarity(self, local_provider):
        vectors = local_provider.embed([
            "The cat sat on the mat",
            "A cat was sitting on a mat",
            "Python programming tutorial",
        ])

        # Cosine similarity (vectors are pre-normalized)
        def cosine_sim(a, b):
            return sum(x * y for x, y in zip(a, b))

        sim_similar = cosine_sim(vectors[0], vectors[1])
        sim_different = cosine_sim(vectors[0], vectors[2])

        # Similar sentences should have higher similarity
        assert sim_similar > sim_different
        assert sim_similar > 0.7  # Should be quite similar
        assert sim_different < 0.5  # Should be quite different


class TestProviderFactory:
    def test_create_local(self):
        provider = create_provider("local")
        assert isinstance(provider, LocalEmbeddingProvider)

    def test_create_openai_without_key_raises(self):
        with pytest.raises(ValueError, match="API key"):
            create_provider("openai", api_key="")

    def test_create_default_is_local(self):
        provider = create_provider()
        assert isinstance(provider, LocalEmbeddingProvider)
