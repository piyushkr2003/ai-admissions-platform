"""Versioned API router foundation.

Individual feature routers (auth, colleges, courses, ...) register
themselves here as they are implemented in later tasks.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import health

api_router = APIRouter()
api_router.include_router(health.router)
