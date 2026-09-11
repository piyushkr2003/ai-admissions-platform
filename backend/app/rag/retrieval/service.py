"""College-scoped knowledge retrieval (docs/rag.md sections 21-31).

Tenant filtering is part of the SQL query itself, not a post-filter -
there is no code path here that fetches candidates across colleges and
narrows down afterward.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.knowledge import KnowledgeChunk, KnowledgeSource, UnansweredQuestion
from app.rag.providers.factory import get_embedding_provider

logger = logging.getLogger("app.rag.retrieval")


@dataclass
class RetrievedChunk:
    chunk_id: str
    source_id: str
    title: str
    content: str
    score: float
    chunk_index: int | None


@dataclass
class RetrievalResult:
    results: list[RetrievedChunk] = field(default_factory=list)
    has_reliable_evidence: bool = False


class RetrievalService:
    def __init__(self, db: Session):
        self.db = db

    def search(
        self,
        *,
        college_id: uuid.UUID,
        query: str,
        top_k: int | None = None,
        include_internal: bool = False,
        record_unanswered: bool = True,
    ) -> RetrievalResult:
        settings = get_settings()
        top_k = top_k or settings.rag_top_k
        query = (query or "").strip()
        if not query:
            return RetrievalResult(results=[], has_reliable_evidence=False)

        provider = get_embedding_provider()
        query_vector = provider.embed(query)
        if all(v == 0.0 for v in query_vector):
            # No recognizable tokens (e.g. pure punctuation) - nothing to rank.
            if record_unanswered:
                self._record_unanswered(college_id, query, top_score=None)
            return RetrievalResult(results=[], has_reliable_evidence=False)

        distance = KnowledgeChunk.embedding.cosine_distance(query_vector)
        now = datetime.now(timezone.utc)

        stmt = (
            select(KnowledgeChunk, KnowledgeSource, distance.label("distance"))
            .join(KnowledgeSource, KnowledgeChunk.knowledge_source_id == KnowledgeSource.id)
            .where(
                KnowledgeChunk.college_id == college_id,
                KnowledgeSource.college_id == college_id,
                KnowledgeSource.status == "ready",
                or_(KnowledgeSource.effective_from.is_(None), KnowledgeSource.effective_from <= now),
                or_(KnowledgeSource.effective_until.is_(None), KnowledgeSource.effective_until >= now),
            )
        )
        if not include_internal:
            stmt = stmt.where(KnowledgeSource.visibility == "public")

        stmt = stmt.order_by(distance).limit(top_k)
        rows = self.db.execute(stmt).all()

        candidates = [
            RetrievedChunk(
                chunk_id=str(chunk.id),
                source_id=str(source.id),
                title=source.name,
                content=chunk.content,
                score=max(0.0, 1.0 - float(dist)) if dist is not None else 0.0,
                chunk_index=chunk.chunk_index,
            )
            for chunk, source, dist in rows
        ]

        threshold = settings.rag_relevance_threshold
        reliable = [c for c in candidates if c.score >= threshold]
        has_reliable = len(reliable) > 0

        if not has_reliable and record_unanswered:
            top_score = candidates[0].score if candidates else None
            self._record_unanswered(college_id, query, top_score=top_score)

        return RetrievalResult(results=reliable, has_reliable_evidence=has_reliable)

    def _record_unanswered(self, college_id: uuid.UUID, query: str, *, top_score: float | None) -> None:
        self.db.add(UnansweredQuestion(college_id=college_id, query=query, top_score=top_score))
        self.db.flush()
        logger.info("rag_no_answer college_id=%s", college_id)
