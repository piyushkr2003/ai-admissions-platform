"""Analytics & reporting API (Task 013, docs/api-contract.md section 64).

Two endpoints intentionally cover every domain rather than one endpoint
per entity (`/analytics/leads`, `/analytics/appointments`, ...): a
dashboard needs a single efficient snapshot plus a single time-series
call, not a dozen near-identical round trips. `overview` returns
current totals/breakdowns for the resolved range; `trends` returns the
same range bucketed into local calendar days for charting.

Tenant resolution follows the exact pattern used by every other router
in this codebase (`resolve_tenant_college_id`) - a college-scoped
caller's `college_id` query parameter is never trusted, only a
platform_admin may select one explicitly.
"""
from __future__ import annotations

import logging
import time
import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.analytics.dates import resolve_date_range
from app.analytics.service import AnalyticsService
from app.auth.dependencies import require_permission, resolve_tenant_college_id
from app.core.responses import envelope
from app.db.session import get_db
from app.models.user import User

router = APIRouter(prefix="/analytics", tags=["analytics"])
logger = logging.getLogger("app.analytics")

RangeParam = Literal["today", "last_7_days", "last_30_days", "last_90_days", "custom"]


def _log_request(endpoint: str, college_id: uuid.UUID, range_: str, start: float, status: str) -> None:
    duration_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "analytics_request endpoint=%s college_id=%s range=%s status=%s duration_ms=%.2f",
        endpoint, college_id, range_, status, duration_ms,
    )


@router.get("/overview")
def get_overview(
    college_id: uuid.UUID | None = Query(default=None),
    range: RangeParam = Query(default="last_30_days"),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("analytics:read")),
) -> dict:
    tenant_id = resolve_tenant_college_id(user, college_id)
    started = time.perf_counter()
    service = AnalyticsService(db)
    college = service.get_college_or_404(tenant_id)
    resolved = resolve_date_range(range_=range, start_date=start_date, end_date=end_date, tz_name=college.timezone)
    try:
        data = service.build_overview(tenant_id, resolved)
    except Exception:
        _log_request("overview", tenant_id, range, started, "error")
        raise
    _log_request("overview", tenant_id, range, started, "ok")
    return envelope(data)


@router.get("/trends")
def get_trends(
    college_id: uuid.UUID | None = Query(default=None),
    range: RangeParam = Query(default="last_30_days"),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("analytics:read")),
) -> dict:
    tenant_id = resolve_tenant_college_id(user, college_id)
    started = time.perf_counter()
    service = AnalyticsService(db)
    college = service.get_college_or_404(tenant_id)
    resolved = resolve_date_range(range_=range, start_date=start_date, end_date=end_date, tz_name=college.timezone)
    try:
        data = service.build_trends(tenant_id, resolved)
    except Exception:
        _log_request("trends", tenant_id, range, started, "error")
        raise
    _log_request("trends", tenant_id, range, started, "ok")
    return envelope(data)
