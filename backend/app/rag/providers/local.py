"""Deterministic, offline embedding provider.

Used as the default so the platform is fully testable and demo-able
without any paid LLM/embedding API key (docs/rag.md section 66,
CLAUDE.md "Model Provider Abstraction"). It uses feature hashing
(the "hashing trick"): each normalized token votes on a bucket of a
fixed-size vector, which is then L2-normalized. This is not as
semantically rich as a trained embedding model, but it is deterministic,
fast, dependency-free, and gives meaningfully higher cosine similarity
to text that shares vocabulary - enough to exercise and test the full
RAG pipeline (tenant isolation, thresholds, ranking) honestly.

A production deployment can swap this for a real provider (OpenAI,
Cohere, etc.) by implementing EmbeddingProvider and updating
get_embedding_provider() - no other RAG code changes.
"""
from __future__ import annotations

import hashlib
import math
import re

from app.rag.providers.base import EmbeddingProvider

_TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)

# A small function-word/filler list. Removing these keeps hashed vectors
# dominated by content words, which matters a lot for a hashing-trick
# embedding: without it, common words shared between an unrelated query
# and any chunk ("is", "the", "what") can produce a nonzero similarity
# score purely by chance.
_STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "of", "in", "on", "at", "to", "for", "and", "or", "but", "with",
    "what", "which", "who", "whom", "this", "that", "these", "those",
    "i", "you", "he", "she", "it", "we", "they", "me", "my", "your",
    "his", "her", "its", "our", "their", "do", "does", "did", "have",
    "has", "had", "can", "could", "will", "would", "shall", "should",
    "may", "might", "must", "about", "tell", "please", "hi", "hello",
    "there", "here", "as", "by", "from", "if", "so", "not",
}


class LocalHashingEmbeddingProvider(EmbeddingProvider):
    def __init__(self, dimensions: int = 256, model_name: str = "local-hashing-v1"):
        self.dimensions = dimensions
        self.model_name = model_name

    def _tokenize(self, text: str) -> list[str]:
        tokens = [t.lower() for t in _TOKEN_RE.findall(text or "")]
        return [t for t in tokens if t not in _STOPWORDS]

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = self._tokenize(text)
        if not tokens:
            return vector
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            bucket = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[bucket] += sign
        norm = math.sqrt(sum(v * v for v in vector))
        if norm == 0:
            return vector
        return [v / norm for v in vector]
