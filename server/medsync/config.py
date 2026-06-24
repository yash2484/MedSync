"""Application configuration via Pydantic BaseSettings.

All values are environment-overridable. Defaults target the Docker Compose
network (service hostnames: postgres, redis). For local-without-Docker runs,
override DATABASE_URL / REDIS_URL via a .env file (see .env.example).
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_env: Literal["dev", "test", "prod"] = "dev"

    # PostgreSQL (async driver)
    database_url: str = "postgresql+asyncpg://medsync:medsync@postgres:5432/medsync"

    # Redis (Celery broker/result backend + status pub/sub)
    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str = "redis://redis:6379/1"
    celery_result_backend: str = "redis://redis:6379/2"

    # Embeddings provider for Phase 2 RAG (configurable now per CLAUDE.md §8)
    embedding_provider: Literal["local", "openai"] = "local"

    # Deduplication thresholds (Fellegi-Sunter, Increment 4)
    dedup_upper_threshold: float = 6.0
    dedup_lower_threshold: float = 0.0
    dedup_name_similarity_cutoff: float = 0.85


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
