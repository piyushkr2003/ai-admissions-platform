"""Import every model module so Base.metadata is fully populated for
Alembic autogeneration and for test schema creation."""
from app.db.base import Base  # noqa: F401
from app.models.college import College  # noqa: F401
from app.models.user import User  # noqa: F401
from app.models.auth import RefreshSession  # noqa: F401
from app.models.student import Student  # noqa: F401
from app.models.academics import (  # noqa: F401
    Course,
    CourseEligibilityRule,
    Scholarship,
    AdmissionDate,
    RequiredDocument,
)
from app.models.counseling import Counselor, CounselorAvailability, Appointment  # noqa: F401
from app.models.leads import Lead, LeadScoreEvent  # noqa: F401
from app.models.applications import Application, ApplicationDocument  # noqa: F401
from app.models.conversations import Conversation, Message  # noqa: F401
from app.models.knowledge import KnowledgeSource, KnowledgeChunk  # noqa: F401
from app.models.agent_config import AgentConfig  # noqa: F401
from app.models.support import FAQ, SupportTicket, AuditLog  # noqa: F401

__all__ = [
    "Base",
    "College",
    "User",
    "RefreshSession",
    "Student",
    "Course",
    "CourseEligibilityRule",
    "Scholarship",
    "AdmissionDate",
    "RequiredDocument",
    "Counselor",
    "CounselorAvailability",
    "Appointment",
    "Lead",
    "LeadScoreEvent",
    "Application",
    "ApplicationDocument",
    "Conversation",
    "Message",
    "KnowledgeSource",
    "KnowledgeChunk",
    "AgentConfig",
    "FAQ",
    "SupportTicket",
    "AuditLog",
]
