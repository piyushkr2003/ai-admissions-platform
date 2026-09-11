from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CollegeCreate(BaseModel):
    """Explicit create schema - only fields a caller may set.

    id/status/created_at/etc. are always server-derived (mass-assignment
    protection, Task 004 section 43).
    """

    name: str = Field(min_length=1, max_length=255)
    slug: str | None = Field(default=None, max_length=100)
    description: str | None = None
    website_url: str | None = None
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    postal_code: str | None = None
    timezone: str = "Asia/Kolkata"
    default_language: str = "en"
    supported_languages: list[str] = Field(default_factory=lambda: ["en"])


class CollegeIdentityUpdate(BaseModel):
    """PATCH /colleges/{id} - identity/contact fields only."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    website_url: str | None = None
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    postal_code: str | None = None


class CollegeConfigurationUpdate(BaseModel):
    """PATCH /colleges/{id}/configuration - operational settings only."""

    timezone: str | None = None
    default_language: str | None = None
    supported_languages: list[str] | None = None
    feature_flags: dict | None = None
    logo_url: str | None = None


class ConfigurationStatusOut(BaseModel):
    identity: str
    branding: str
    languages: str
    admissions: str
    knowledge: str
    agent: str


class CollegeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    slug: str
    description: str | None
    logo_url: str | None
    website_url: str | None
    email: str | None
    phone: str | None
    city: str | None
    state: str | None
    country: str | None
    timezone: str
    default_language: str
    supported_languages: list[str]
    feature_flags: dict
    status: str
    configuration_status: ConfigurationStatusOut


class ValidationResultOut(BaseModel):
    valid: bool
    errors: list[str]
