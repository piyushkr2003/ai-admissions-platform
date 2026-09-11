"""Internal endpoints that exist only to prove the auth/RBAC dependency
chain works end-to-end (Task 003 section 38). Not part of the public
product API surface.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends

from app.auth.dependencies import require_college_access, require_platform_admin
from app.auth.router import _user_out
from app.core.responses import envelope
from app.models.user import User

router = APIRouter(prefix="/_internal", tags=["internal"])


@router.get("/college-check/{college_id}")
def college_check(college_id: uuid.UUID, user: User = Depends(require_college_access)) -> dict:
    return envelope({"college_id": str(college_id), "authorized_as": _user_out(user)})


@router.get("/platform-only")
def platform_only(user: User = Depends(require_platform_admin)) -> dict:
    return envelope({"authorized_as": _user_out(user)})
