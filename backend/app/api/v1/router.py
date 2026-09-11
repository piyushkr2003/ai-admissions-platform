"""Versioned API router foundation.

Individual feature routers (auth, colleges, courses, ...) register
themselves here as they are implemented in later tasks.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import health, internal_test
from app.auth.router import router as auth_router

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth_router)
api_router.include_router(internal_test.router)
