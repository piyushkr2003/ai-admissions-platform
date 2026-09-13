"""Strongly typed application settings loaded from environment variables."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Application
    app_env: str = "development"
    app_debug: bool = True
    app_name: str = "AI Admissions Platform"
    api_v1_prefix: str = "/api/v1"

    # Database
    database_url: str = "postgresql+psycopg://admissions:admissions@localhost:5432/admissions"
    database_url_test: str = "postgresql+psycopg://admissions:admissions@localhost:5432/admissions_test"

    # Security / Auth
    jwt_secret_key: str = "insecure-development-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 14

    # CORS
    cors_allowed_origins: str = "http://localhost:3000"

    # Logging
    log_level: str = "INFO"

    # Embeddings / RAG
    embedding_provider: str = "local"
    embedding_model: str = "local-hashing-v1"
    embedding_dimensions: int = 256
    rag_relevance_threshold: float = 0.15
    rag_top_k: int = 5
    knowledge_max_file_size_mb: int = 15

    # Agent / LLM - "mock" (default) never calls out; the LLM is only ever
    # used for bounded conversational reasoning (open-ended/small-talk
    # phrasing), never as the source of truth for admissions facts - see
    # app/agent/providers/ and the orchestrator's _open_ended_reply (Task 016).
    agent_llm_provider: str = "mock"
    llm_api_key: str = ""
    llm_model: str = "claude-sonnet-4-5-20250929"
    llm_api_base_url: str = "https://api.anthropic.com"
    llm_timeout_seconds: float = 8.0
    agent_max_tool_calls_per_turn: int = 6

    # Gemini LLM provider (alternative to anthropic, same LLMProvider
    # interface and same single call site - see app/agent/providers/gemini.py).
    google_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    gemini_api_base_url: str = "https://generativelanguage.googleapis.com"

    # Future providers
    stt_api_key: str = ""
    tts_api_key: str = ""
    voice_provider_api_key: str = ""
    storage_access_key: str = ""
    storage_secret_key: str = ""

    # Voice (Task 011) - provider names default to the deterministic mock
    # adapter; selecting anything else without the matching credential
    # above configured raises a clear error rather than pretending to work.
    stt_provider: str = "mock"
    tts_provider: str = "mock"
    voice_transport_provider: str = "mock"
    telephony_provider: str = "mock"
    telephony_webhook_secret: str = ""
    voice_session_max_duration_seconds: int = 1800
    voice_session_idle_timeout_seconds: int = 60
    voice_max_concurrent_sessions_per_college: int = 20

    # Realtime web voice transport (Task 015) - set VOICE_TRANSPORT_PROVIDER=livekit
    # and all three of these to use real LiveKit infrastructure instead of the
    # mock transport. LIVEKIT_API_SECRET signs short-lived room-join tokens
    # server-side and must never be sent to the frontend.
    livekit_url: str = ""
    livekit_api_key: str = ""
    livekit_api_secret: str = ""
    livekit_token_ttl_seconds: int = 600

    # Realtime voice agent worker (Task 016) - a separate process that joins
    # a LiveKit room, performs STT, drives the existing AgentOrchestrator,
    # and publishes synthesized speech back. Irrelevant/unused in mock mode.
    livekit_worker_identity: str = "admissions-agent"
    voice_worker_poll_interval_seconds: float = 2.0
    voice_worker_sample_rate: int = 48000
    voice_worker_channels: int = 1

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]

    def validate_for_production(self) -> None:
        """Fail clearly when required production configuration is missing."""
        if not self.is_production:
            return
        problems: list[str] = []
        if self.jwt_secret_key in ("", "insecure-development-secret-change-me"):
            problems.append("JWT_SECRET_KEY must be set to a strong secret in production")
        if len(self.jwt_secret_key) < 32:
            problems.append("JWT_SECRET_KEY must be at least 32 characters in production")
        if self.app_debug:
            problems.append("APP_DEBUG must be false in production")
        if "*" in self.cors_origins_list:
            problems.append("CORS_ALLOWED_ORIGINS must not be a wildcard in production")
        if self.voice_transport_provider.lower() == "livekit" and not (
            self.livekit_url and self.livekit_api_key and self.livekit_api_secret
        ):
            problems.append(
                "LIVEKIT_URL, LIVEKIT_API_KEY, and LIVEKIT_API_SECRET must all be set in production "
                "when VOICE_TRANSPORT_PROVIDER=livekit"
            )
        if self.agent_llm_provider.lower() == "anthropic" and not self.llm_api_key:
            problems.append(
                f"LLM_API_KEY must be set in production when AGENT_LLM_PROVIDER={self.agent_llm_provider}"
            )
        if self.agent_llm_provider.lower() == "gemini" and not self.google_api_key:
            problems.append(
                f"GOOGLE_API_KEY must be set in production when AGENT_LLM_PROVIDER={self.agent_llm_provider}"
            )
        if problems:
            raise RuntimeError(
                "Invalid production configuration: " + "; ".join(problems)
            )


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_for_production()
    return settings
