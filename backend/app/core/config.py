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

    # Agent / LLM
    agent_llm_provider: str = "mock"
    llm_api_key: str = ""
    agent_max_tool_calls_per_turn: int = 6

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
        if problems:
            raise RuntimeError(
                "Invalid production configuration: " + "; ".join(problems)
            )


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_for_production()
    return settings
