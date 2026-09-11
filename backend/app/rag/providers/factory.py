from __future__ import annotations

from functools import lru_cache

from app.core.config import get_settings
from app.rag.providers.base import EmbeddingProvider
from app.rag.providers.local import LocalHashingEmbeddingProvider


@lru_cache
def get_embedding_provider() -> EmbeddingProvider:
    settings = get_settings()
    if settings.embedding_provider == "local":
        return LocalHashingEmbeddingProvider(
            dimensions=settings.embedding_dimensions, model_name=settings.embedding_model
        )
    raise ValueError(
        f"Unsupported EMBEDDING_PROVIDER '{settings.embedding_provider}'. "
        "Implement an EmbeddingProvider subclass and register it here to add a new provider."
    )
