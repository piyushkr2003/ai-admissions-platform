"""Knowledge ingestion pipeline (docs/rag.md section 12, Task 005 section 12).

Source -> validate -> extract -> normalize -> chunk -> embed -> store ->
mark ready. A source is never marked ready unless it has at least one
usable chunk, and a failure never leaves a source falsely "ready".
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.knowledge import KnowledgeChunk, KnowledgeSource
from app.rag.ingestion.chunking import chunk_text
from app.rag.ingestion.extractors import ExtractionError, extract_pdf_text, extract_plain_text
from app.rag.providers.factory import get_embedding_provider
from app.services.audit import record_audit

logger = logging.getLogger("app.rag.ingestion")


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class IngestionService:
    def __init__(self, db: Session):
        self.db = db

    def _extract(self, source_type: str, *, text: str | None, file_base64: str | None) -> str:
        if source_type == "pdf":
            if not file_base64:
                raise ExtractionError("UNSUPPORTED_FILE_TYPE", "file_base64 is required for source_type 'pdf'.")
            return extract_pdf_text(file_base64)
        if source_type in ("txt", "manual", "faq"):
            if not text:
                raise ExtractionError("EMPTY_DOCUMENT", "text is required for this source_type.")
            return extract_plain_text(text)
        raise ExtractionError("UNSUPPORTED_FILE_TYPE", f"Unsupported source_type '{source_type}'.")

    def ingest(
        self,
        *,
        college_id: uuid.UUID,
        name: str,
        source_type: str,
        text: str | None = None,
        file_base64: str | None = None,
        visibility: str = "public",
        effective_from: datetime | None = None,
        effective_until: datetime | None = None,
        actor_user_id: uuid.UUID | None = None,
    ) -> KnowledgeSource:
        extracted = self._extract(source_type, text=text, file_base64=file_base64)
        content_hash = _content_hash(extracted)

        existing = self.db.execute(
            select(KnowledgeSource).where(
                KnowledgeSource.college_id == college_id,
                KnowledgeSource.content_hash == content_hash,
                KnowledgeSource.status == "ready",
            )
        ).scalar_one_or_none()
        if existing is not None:
            logger.info("ingestion_skipped_duplicate college_id=%s source_id=%s", college_id, existing.id)
            return existing

        source = KnowledgeSource(
            college_id=college_id,
            name=name,
            source_type=source_type,
            status="processing",
            content_hash=content_hash,
            visibility=visibility,
            effective_from=effective_from,
            effective_until=effective_until,
        )
        self.db.add(source)
        self.db.flush()

        try:
            self._process(source, extracted)
        except AppError:
            # `source` (status=failed, error_message set) stays attached to
            # the session so the caller can still commit and persist it for
            # admin visibility/retry - a failed source must never vanish or
            # be silently marked ready.
            raise
        except Exception as exc:  # noqa: BLE001 - convert to a categorized, safe failure
            logger.exception("ingestion_failed source_id=%s", source.id)
            source.status = "failed"
            source.error_message = "Processing failed unexpectedly."
            self.db.flush()
            raise AppError("EXTRACTION_FAILED", "Knowledge source processing failed.") from exc

        record_audit(
            self.db, college_id=college_id, user_id=actor_user_id,
            action="knowledge_source_uploaded", entity_type="knowledge_source", entity_id=source.id,
            meta={"source_type": source_type, "chunk_count": self._chunk_count(source.id)},
        )
        return source

    def _process(self, source: KnowledgeSource, extracted_text: str) -> None:
        provider = get_embedding_provider()
        pieces = chunk_text(extracted_text)
        if not pieces:
            source.status = "failed"
            source.error_message = "No usable content could be extracted."
            self.db.flush()
            raise ExtractionError("EMPTY_DOCUMENT", "No usable content could be extracted.")

        for index, piece in enumerate(pieces):
            embedding = provider.embed(piece)
            chunk = KnowledgeChunk(
                college_id=source.college_id,
                knowledge_source_id=source.id,
                content=piece,
                chunk_index=index,
                meta={"source_type": source.source_type},
                embedding=embedding,
            )
            self.db.add(chunk)

        source.status = "ready"
        source.embedding_model = provider.model_name
        source.last_synced_at = datetime.now(timezone.utc)
        source.error_message = None
        self.db.flush()

    def _chunk_count(self, source_id: uuid.UUID) -> int:
        stmt = select(KnowledgeChunk.id).where(KnowledgeChunk.knowledge_source_id == source_id)
        return len(self.db.execute(stmt).all())

    def reprocess(self, source: KnowledgeSource) -> KnowledgeSource:
        """Re-run chunking/embedding using the source's stored chunk text
        (there is no separate raw-file store in this implementation, so
        reprocessing re-embeds existing chunks rather than re-extracting)."""
        stmt = select(KnowledgeChunk).where(KnowledgeChunk.knowledge_source_id == source.id)
        chunks = list(self.db.execute(stmt).scalars().all())
        if not chunks:
            source.status = "failed"
            source.error_message = "No stored content available to reprocess."
            self.db.flush()
            raise ExtractionError("EMPTY_DOCUMENT", "No stored content available to reprocess.")

        provider = get_embedding_provider()
        for chunk in chunks:
            chunk.embedding = provider.embed(chunk.content)
        source.status = "ready"
        source.embedding_model = provider.model_name
        source.last_synced_at = datetime.now(timezone.utc)
        source.error_message = None
        self.db.flush()
        return source

    def archive(self, source: KnowledgeSource, *, actor_user_id: uuid.UUID | None) -> KnowledgeSource:
        source.status = "archived"
        self.db.flush()
        record_audit(
            self.db, college_id=source.college_id, user_id=actor_user_id,
            action="knowledge_source_archived", entity_type="knowledge_source", entity_id=source.id,
        )
        return source
