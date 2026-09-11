from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db

logger = logging.getLogger("app.health")

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    """Liveness check: confirms the application process is running."""
    return {"status": "ok"}


@router.get("/ready")
def ready(db: Session = Depends(get_db)) -> dict:
    """Readiness check: confirms required dependencies (database) are reachable."""
    try:
        db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:  # pragma: no cover - defensive, exercised via integration env
        logger.exception("readiness_db_check_failed")
        db_status = "unavailable"
    overall = "ok" if db_status == "ok" else "degraded"
    return {"status": overall, "checks": {"database": db_status}}
