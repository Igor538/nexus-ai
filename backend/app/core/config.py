"""Application configuration loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(BACKEND_DIR / ".env", BACKEND_DIR.parent / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "Nexus AI"
    app_env: str = "development"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    frontend_url: str = "http://localhost:5173"
    cors_origins: str = "http://localhost:5173,http://localhost:4173,http://localhost:3000"
    log_level: str = "INFO"
    auto_create_tables: bool = True

    database_url: str = "postgresql+psycopg://nexus:nexus_dev_password@localhost:5432/nexus"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret_key: str = "dev-only-insecure-secret-change-me-please-32chars"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    password_reset_expire_minutes: int = 30
    credentials_encryption_key: str | None = None

    execution_mode: str = "inline"
    execution_timeout_seconds: int = 300
    execution_max_steps: int = 200
    execution_max_output_bytes: int = 262_144
    node_default_max_attempts: int = 1
    max_active_executions_per_workflow: int = 1

    http_timeout_seconds: int = 30
    http_max_response_bytes: int = 1_000_000
    http_allow_private_networks: bool = False

    ai_default_provider: str = "gemini"
    ai_default_model: str = "gemini-2.0-flash"
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    gemini_api_key: str | None = None
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    groq_api_key: str | None = None
    groq_base_url: str = "https://api.groq.com/openai/v1"
    openrouter_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_model: str = "llama3.1"
    ai_agent_max_iterations: int = 5
    ai_daily_token_limit: int = 200_000
    ai_request_timeout_seconds: int = 90

    rate_limit_enabled: bool = True
    auth_rate_limit_per_minute: int = 20
    webhook_rate_limit_per_minute: int = 60
    webhook_max_body_bytes: int = 262_144
    webhook_signature_tolerance_seconds: int = 300

    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str = "no-reply@nexus.local"
    smtp_use_tls: bool = True

    webhook_base_url: str = "http://localhost:8000"

    @field_validator("database_url")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        value = value.strip()
        if value.startswith("postgres://"):
            value = "postgresql://" + value[len("postgres://") :]
        if value.startswith("postgresql://"):
            value = "postgresql+psycopg://" + value[len("postgresql://") :]
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in {"production", "prod"}

    @property
    def run_inline(self) -> bool:
        return self.execution_mode.lower() != "celery"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

