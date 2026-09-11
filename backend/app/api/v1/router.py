"""Versioned API router foundation.

Individual feature routers (auth, colleges, courses, ...) register
themselves here as they are implemented in later tasks.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import health, internal_test
from app.auth.router import router as auth_router
from app.agent.router import router as agent_router
from app.applications.router import router as applications_router
from app.appointments.router import appointments_router, counselors_router
from app.colleges.router import router as colleges_router
from app.conversations.router import router as conversations_router
from app.knowledge.router import router as knowledge_router
from app.leads.router import router as leads_router

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth_router)
api_router.include_router(internal_test.router)
api_router.include_router(colleges_router)
api_router.include_router(knowledge_router)
api_router.include_router(agent_router)
api_router.include_router(conversations_router)
api_router.include_router(leads_router)
api_router.include_router(counselors_router)
api_router.include_router(appointments_router)
api_router.include_router(applications_router)
