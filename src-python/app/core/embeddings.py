"""
Embedding provider abstraction.

This module defines the interface for embedding providers and ships two
implementations:
  - LocalEmbeddingProvider: runs sentence-transformers on the local CPU/MPS
  - OpenAIEmbeddingProvider: calls the OpenAI embeddings API

Users can switch between providers in settings. Switching requires a full
re-index because vector dimensions differ between models.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import structlog

logger = structlog.get_logger()


class EmbeddingProvider(ABC):
    """Interface for text embedding models."""

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts into vectors."""
        ...

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """Vector dimensionality of this provider's embeddings."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider name."""
        ...


class LocalEmbeddingProvider(EmbeddingProvider):
    """
    Local embedding using sentence-transformers.

    Default model: all-MiniLM-L6-v2
      - 384 dimensions
      - ~80MB on disk
      - ~500 embeddings/sec on M1 CPU
      - No internet required
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        from sentence_transformers import SentenceTransformer
        import torch

        # Use MPS (Apple Silicon GPU) if available, else CPU
        device = "mps" if torch.backends.mps.is_available() else "cpu"
        logger.info("embedding.local.loading", model=model_name, device=device)

        self._model = SentenceTransformer(model_name, device=device)
        self._dimensions = self._model.get_sentence_embedding_dimension()
        self._name = f"local/{model_name}"

        logger.info("embedding.local.ready", dimensions=self._dimensions)

    def embed(self, texts: list[str]) -> list[list[float]]:
        embeddings = self._model.encode(
            texts,
            show_progress_bar=False,
            normalize_embeddings=True,  # Pre-normalize for cosine similarity
            batch_size=64,
        )
        return embeddings.tolist()

    @property
    def dimensions(self) -> int:
        return self._dimensions

    @property
    def name(self) -> str:
        return self._name


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """
    Cloud embedding using OpenAI's API.

    Default model: text-embedding-3-small
      - 1536 dimensions
      - $0.02 per 1M tokens
      - Requires internet + API key
      - Higher quality for nuanced queries
    """

    def __init__(self, api_key: str, model: str = "text-embedding-3-small"):
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key)
        self._model = model
        self._name = f"openai/{model}"

        # Dimension lookup for known models
        dim_map = {
            "text-embedding-3-small": 1536,
            "text-embedding-3-large": 3072,
            "text-embedding-ada-002": 1536,
        }
        self._dimensions = dim_map.get(model, 1536)

        logger.info("embedding.openai.ready", model=model, dimensions=self._dimensions)

    def embed(self, texts: list[str]) -> list[list[float]]:
        from tenacity import retry, stop_after_attempt, wait_exponential

        @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
        def _call(batch: list[str]) -> list[list[float]]:
            response = self._client.embeddings.create(input=batch, model=self._model)
            return [item.embedding for item in response.data]

        # OpenAI recommends batches of up to 2048
        results = []
        for i in range(0, len(texts), 2048):
            batch = texts[i : i + 2048]
            results.extend(_call(batch))
        return results

    @property
    def dimensions(self) -> int:
        return self._dimensions

    @property
    def name(self) -> str:
        return self._name


def create_provider(
    provider_type: str = "local",
    model_name: str = "all-MiniLM-L6-v2",
    api_key: str = "",
) -> EmbeddingProvider:
    """Factory function to create the configured embedding provider."""
    if provider_type == "openai":
        if not api_key:
            raise ValueError("OpenAI API key is required for cloud embeddings")
        return OpenAIEmbeddingProvider(api_key=api_key)
    return LocalEmbeddingProvider(model_name=model_name)
