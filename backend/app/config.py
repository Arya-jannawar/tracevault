"""Application configuration via environment variables (.env supported)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    workspace_name: str = "default"

    # Storage
    database_url: str = "postgresql+psycopg://tracevault:tracevault@127.0.0.1:5433/tracevault"
    qdrant_url: str = "http://127.0.0.1:6333"
    qdrant_collection: str = "tracevault"
    redis_url: str = "redis://127.0.0.1:6379/0"

    # Auth
    session_secret: str = ""
    session_ttl_minutes: int = 720
    admin_username: str = "admin"
    admin_password: str = ""

    # AI adapters
    embedding_provider: str = "deterministic"  # deterministic | sentence-transformers
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dim: int = 384
    llm_provider: str = "extractive"  # extractive | openai-compatible
    llm_base_url: str = "http://127.0.0.1:11434/v1"
    llm_model: str = "qwen2.5:3b-instruct"
    llm_api_key: str = ""

    # Flags
    enable_selective_repair: bool = False
    enable_semantic_cache: bool = False
    semantic_cache_threshold: float = 0.92

    # Limits
    max_upload_mb: int = 10
    max_chunks_per_doc: int = 2000

    # Demo seeding
    seed_on_start: bool = True

    # Worker
    worker_poll_seconds: float = 1.0
    worker_lease_seconds: int = 120
    worker_max_attempts: int = 3

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
