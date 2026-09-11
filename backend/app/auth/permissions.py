"""Centralized RBAC permission matrix (docs/api-contract.md section 6).

Do not scatter hardcoded role checks throughout route handlers - add the
permission here and depend on `require_permission(...)`.
"""
from __future__ import annotations

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "platform_admin": {"*"},
    "college_admin": {
        "college_configuration:read", "college_configuration:write",
        "courses:read", "courses:write",
        "leads:read", "leads:write",
        "appointments:read", "appointments:write",
        "applications:read", "applications:write",
        "knowledge:read", "knowledge:write",
        "analytics:read",
        "agent_config:read", "agent_config:write",
    },
    "admissions_staff": {
        "college_configuration:read",
        "courses:read",
        "leads:read", "leads:write",
        "appointments:read", "appointments:write",
        "applications:read", "applications:write",
        "knowledge:read", "knowledge:write",
        "analytics:read",
        "agent_config:read",
    },
    "counselor": {
        "college_configuration:read",
        "courses:read",
        "leads:read",
        "appointments:read", "appointments:write",
        "applications:read",
        "knowledge:read",
        "analytics:read",
        "agent_config:read",
    },
}


def has_permission(role: str, permission: str) -> bool:
    granted = ROLE_PERMISSIONS.get(role, set())
    return "*" in granted or permission in granted
