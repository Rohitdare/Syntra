"""Application configuration and typed settings using pydantic-settings."""

import sys
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application Environment
    APP_ENV: Literal["local", "staging", "production"] = "local"
    LOG_LEVEL: str = "INFO"
    CORS_ALLOWED_ORIGINS: str | list[str] = Field(default="http://localhost:3000")

    # Authentication
    AUTH_MODE: Literal["dev", "jwt"] = "dev"
    AUTH_ISSUER: str | None = None
    AUTH_AUDIENCE: str | None = None
    AUTH_JWKS_URL: str | None = None

    # PostgreSQL
    DATABASE_URL: SecretStr = SecretStr("")
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 5

    # Gemini
    GEMINI_API_KEY: SecretStr = SecretStr("")
    GEMINI_MODEL_FAST: str = ""
    GEMINI_MODEL_STRONG: str = ""
    GEMINI_EMBEDDING_MODEL: str = "gemini-embedding-001"
    EMBEDDING_DIM: int = 768
    GEMINI_MAX_CONCURRENCY: int = 2
    LLM_MIN_INTERVAL_MS: int = 2000
    EMBED_MIN_INTERVAL_MS: int = 700
    LLM_ENABLED: bool = True

    # Qdrant
    QDRANT_URL: str = ""
    QDRANT_API_KEY: SecretStr = SecretStr("")
    QDRANT_COLLECTION: str = "knowledge"

    # Ingestion & document limits
    MAX_SOURCES_PER_PROJECT: int = 8
    MAX_UPLOAD_MB: int = 8
    MAX_PDF_PAGES: int = 100
    PDF_PARSE_TIMEOUT_S: int = 30
    MAX_EXTRACTED_CHARS: int = 400000
    MAX_PASTE_CHARS: int = 400000
    MIN_SOURCE_CHARS: int = 500
    CHUNK_TARGET_CHARS: int = 1200
    CHUNK_OVERLAP_CHARS: int = 150
    EMBED_BATCH_SIZE: int = 50

    # Agent limits
    MAX_ANALYST_CHARS: int = 80000
    MAX_CLAIMS_PER_SOURCE: int = 8
    CRITIC_TOP_K: int = 3
    CRITIC_MIN_SIMILARITY: float = 0.60
    CRITIC_MAX_PAIRS_PER_CALL: int = 24
    WRITER_TOP_CHUNKS: int = 6
    WRITER_TOP_CLAIMS: int = 10
    WRITER_MAX_CONFLICTS: int = 5
    LLM_MAX_RETRIES: int = 2

    # Timeouts & operational limits
    LLM_TIMEOUT_S: int = 60
    EMBED_TIMEOUT_S: int = 30
    QDRANT_TIMEOUT_S: int = 10
    STAGE_TIMEOUT_S: int = 180
    JOB_LEASE_S: int = 60
    JOB_HEARTBEAT_S: int = 15
    STREAM_HEARTBEAT_S: int = 15
    MAX_ACTIVE_JOBS: int = 4
    MAX_ACTIVE_JOBS_PER_USER: int = 2
    RATE_LIMIT_POST_PER_USER: str = "30/10m"
    RATE_LIMIT_IP_PER_MIN: int = 60
    USER_DAILY_LLM_CALLS: int | None = None
    USER_DAILY_EMBED_TEXTS: int | None = None
    SHUTDOWN_GRACE_S: int = 30
    URL_MAX_REDIRECTS: int = 3
    URL_MAX_BYTES: int = 5 * 1024 * 1024
    URL_TIMEOUT_S: int = 10

    @field_validator("CORS_ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @model_validator(mode="after")
    def validate_environment_rules(self) -> "Settings":
        """Enforce environment constraints: refuse dev auth outside local."""
        if self.AUTH_MODE == "dev" and self.APP_ENV != "local":
            raise ValueError(
                f"Security configuration error: AUTH_MODE=dev is only permitted when APP_ENV=local "
                f"(current APP_ENV='{self.APP_ENV}'). Startup refused."
            )
        return self


def get_settings() -> Settings:
    """Load and validate settings, failing fast with a clean error message if invalid."""
    try:
        return Settings()
    except Exception as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        raise
