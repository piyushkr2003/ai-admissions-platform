from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.auth.schemas import LoginRequest, LogoutRequest, RefreshRequest, UserOut
from app.auth.service import AuthService
from app.core.responses import envelope
from app.db.session import get_db
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])


def _user_out(user: User) -> dict:
    return UserOut(
        id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        college_id=str(user.college_id) if user.college_id else None,
        is_active=user.is_active,
    ).model_dump()


@router.post("/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> dict:
    service = AuthService(db)
    user, tokens = service.login(payload.email, payload.password)
    db.commit()
    return envelope({**tokens, "user": _user_out(user)})


@router.post("/refresh")
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)) -> dict:
    service = AuthService(db)
    user, tokens = service.refresh(payload.refresh_token)
    db.commit()
    return envelope({**tokens, "user": _user_out(user)})


@router.post("/logout")
def logout(payload: LogoutRequest, db: Session = Depends(get_db)) -> dict:
    if payload.refresh_token:
        service = AuthService(db)
        service.logout(payload.refresh_token)
        db.commit()
    return envelope({"success": True})


@router.get("/me")
def me(user: User = Depends(get_current_user)) -> dict:
    return envelope(_user_out(user))
