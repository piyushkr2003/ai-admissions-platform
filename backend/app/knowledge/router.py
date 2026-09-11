from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import require_permission, resolve_tenant_college_id
from app.core.errors import NotFoundError
from app.core.responses import envelope
from app.db.session import get_db
from app.knowledge.schemas import KnowledgeSearchRequest, KnowledgeSourceCreate
from app.models.knowledge import KnowledgeSource
from app.models.user import User
from app.rag.ingestion.service import IngestionService
from app.rag.retrieval.service import RetrievalService

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


def _source_out(source: KnowledgeSource) -> dict:
    return {
        "id": str(source.id),
        "college_id": str(source.college_id),
        "name": source.name,
        "source_type": source.source_type,
        "status": source.status,
        "version": source.version,
        "visibility": source.visibility,
        "content_hash": source.content_hash,
        "embedding_model": source.embedding_model,
        "error_message": source.error_message,
        "last_synced_at": source.last_synced_at.isoformat() if source.last_synced_at else None,
        "created_at": source.created_at.isoformat(),
    }


@router.post("/sources", status_code=201)
def create_source(
    payload: KnowledgeSourceCreate,
    college_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("knowledge:write")),
) -> dict:
    tenant_id = resolve_tenant_college_id(user, college_id)
    service = IngestionService(db)
    try:
        source = service.ingest(
            college_id=tenant_id,
            name=payload.name,
            source_type=payload.source_type,
            text=payload.text,
            file_base64=payload.file_base64,
            visibility=payload.visibility,
            effective_from=payload.effective_from,
            effective_until=payload.effective_until,
            actor_user_id=user.id,
        )
    finally:
        db.commit()  # persist even a failed source, for admin visibility/retry
    return envelope(_source_out(source))


@router.get("/sources")
def list_sources(
    college_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("knowledge:read")),
) -> dict:
    tenant_id = resolve_tenant_college_id(user, college_id)
    stmt_sources = (
        db.query(KnowledgeSource)
        .filter(KnowledgeSource.college_id == tenant_id)
        .order_by(KnowledgeSource.created_at.desc())
        .all()
    )
    items = [_source_out(s) for s in stmt_sources]
    return envelope(items)


def _get_source_or_404(db: Session, tenant_id: uuid.UUID, source_id: uuid.UUID) -> KnowledgeSource:
    source = db.get(KnowledgeSource, source_id)
    if source is None or source.college_id != tenant_id:
        raise NotFoundError("Knowledge source not found.")
    return source


@router.get("/sources/{source_id}")
def get_source(
    source_id: uuid.UUID,
    college_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("knowledge:read")),
) -> dict:
    tenant_id = resolve_tenant_college_id(user, college_id)
    source = _get_source_or_404(db, tenant_id, source_id)
    return envelope(_source_out(source))


@router.post("/sources/{source_id}/reprocess")
def reprocess_source(
    source_id: uuid.UUID,
    college_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("knowledge:write")),
) -> dict:
    tenant_id = resolve_tenant_college_id(user, college_id)
    source = _get_source_or_404(db, tenant_id, source_id)
    service = IngestionService(db)
    try:
        service.reprocess(source)
    finally:
        db.commit()
    return envelope(_source_out(source))


@router.delete("/sources/{source_id}")
def archive_source(
    source_id: uuid.UUID,
    college_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("knowledge:write")),
) -> dict:
    tenant_id = resolve_tenant_college_id(user, college_id)
    source = _get_source_or_404(db, tenant_id, source_id)
    service = IngestionService(db)
    service.archive(source, actor_user_id=user.id)
    db.commit()
    return envelope(_source_out(source))


@router.post("/search")
def search_knowledge(
    payload: KnowledgeSearchRequest,
    college_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("knowledge:read")),
) -> dict:
    tenant_id = resolve_tenant_college_id(user, college_id)
    service = RetrievalService(db)
    result = service.search(
        college_id=tenant_id, query=payload.query, top_k=payload.top_k, include_internal=True
    )
    db.commit()
    return envelope(
        {
            "results": [
                {
                    "chunk_id": r.chunk_id,
                    "source_id": r.source_id,
                    "title": r.title,
                    "content": r.content,
                    "score": r.score,
                }
                for r in result.results
            ],
            "has_reliable_evidence": result.has_reliable_evidence,
        }
    )
