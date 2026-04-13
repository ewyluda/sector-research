"""Centralized configuration via pydantic-settings. Reads from .env at project root."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root is two levels up from backend/app/config.py
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── API keys ──────────────────────────────────────────────────────────────
    fmp_api_key: str
    x_bearer_token: str
    anthropic_api_key: str
    fred_api_key: str = ""  # Optional — macro section skipped if empty

    # ── Database ──────────────────────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/sector_research"
    database_url_sync: str = "postgresql://postgres:postgres@localhost:5432/sector_research"

    # ── Service URLs ──────────────────────────────────────────────────────────
    fmp_base_url: str = "https://financialmodelingprep.com/stable"
    x_base_url: str = "https://api.twitter.com/2"

    # ── App ───────────────────────────────────────────────────────────────────
    log_level: str = "INFO"
    cors_origins: list[str] = ["http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
