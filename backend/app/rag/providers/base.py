"""Embedding provider abstraction (docs/rag.md section 26).

The RAG implementation must not be tightly coupled to one embedding
vendor. Swapping providers means swapping the class returned by
`get_embedding_provider()` - nothing else in the ingestion/retrieval
pipeline needs to change.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    model_name: str
    dimensions: int

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        """Return a fixed-length embedding vector for `text`."""
        raise NotImplementedError

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]
