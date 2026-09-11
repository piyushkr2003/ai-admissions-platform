"""Reusable FastAPI authentication/authorization dependencies.

These are the only place protected routes should derive identity, role,
and tenant authorization from - do not duplicate this logic in
individual endpoints.
"""
from __future__ import annotations

import uuid
from collections.abc import Callable

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.auth.permissions import has_permission
from app.core.errors import ForbiddenError, TenantAccessDeniedError, UnauthorizedError
from app.core.security import InvalidTokenError, decode_token
from app.db.session import get_db
from app.models.user import User


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the authenticated user from a Bearer access token.

    Never trusts client-supplied role/college_id fields - only the
    server-issued, signed JWT and the corresponding database row.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise UnauthorizedError("Missing bearer token.")
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = decode_token(token, expected_type="access")
    except InvalidTokenError as exc:
        raise UnauthorizedError("Invalid or expired access token.") from exc

    try:
        user_id = uuid.UUID(payload.get("sub", ""))
    except ValueError as exc:
        raise UnauthorizedError("Invalid access token.") from exc

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("Account is no longer active.")
    return user


# Alias matching the task's suggested naming; identical behavior.
require_authenticated_user = get_current_user


def require_role(*roles: str) -> Callable[[User], User]:
    def _dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise ForbiddenError("Your role does not permit this action.")
        return user

    return _dependency


# Alias: a role-set check is the same operation regardless of name used.
require_any_role = require_role


def require_permission(permission: str) -> Callable[[User], User]:
    def _dependency(user: User = Depends(get_current_user)) -> User:
        if not has_permission(user.role, permission):
            raise ForbiddenError(f"Role '{user.role}' is not permitted to perform this action.")
        return user

    return _dependency


def require_platform_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "platform_admin":
        raise ForbiddenError("Platform administrator access required.")
    return user


def require_college_access(college_id: uuid.UUID, user: User = Depends(get_current_user)) -> User:
    """Authorize that `user` may act on `college_id`.

    `college_id` is resolved by FastAPI from the enclosing route's path
    parameter of the same name - a client can change it freely, but the
    comparison below still runs server-side on every request.
    """
    if user.role == "platform_admin":
        return user
    if user.college_id is None or user.college_id != college_id:
        raise TenantAccessDeniedError()
    return user


def resolve_tenant_college_id(user: User, college_id: uuid.UUID | None) -> uuid.UUID:
    """Derive the tenant to operate on from trusted server-side context.

    College-scoped users always operate on their own college_id, taken
    from the signed token - the `college_id` argument (if any) is
    ignored for them, not merely checked. Only a platform_admin, who has
    no single home college, may explicitly select a tenant this way.
    """
    if user.role == "platform_admin":
        if college_id is None:
            raise ForbiddenError("college_id is required for platform admin requests.")
        return college_id
    if user.college_id is None:
        raise ForbiddenError("This account is not associated with a college.")
    return user.college_id


def require_college_permission(permission: str) -> Callable[..., User]:
    """Combine tenant-ownership and role-permission checks for a
    `{college_id}`-scoped route in one dependency."""

    def _dependency(college_id: uuid.UUID, user: User = Depends(get_current_user)) -> User:
        if user.role != "platform_admin":
            if user.college_id is None or user.college_id != college_id:
                raise TenantAccessDeniedError()
        if not has_permission(user.role, permission):
            raise ForbiddenError(f"Role '{user.role}' is not permitted to perform this action.")
        return user

    return _dependency
