"""Runtime configuration, loaded from the environment / ``.env``.

Secrets and per-deployment values live here. The editorial watchlist (company name, competitors,
feeds, channels) is a separate YAML file — see :mod:`sumnews.watchlist`.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-backed settings."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    DATABASE_URL: str = Field(default="postgresql+asyncpg://sumnews:sumnews@localhost:5432/sumnews",
        description="Async SQLAlchemy DSN (asyncpg driver)")

    # LLM — self-hosted OpenAI-compatible endpoint
    LLM_URL: str = Field(default="http://localhost:8000/v1",
        description="Base URL of the OpenAI-compatible chat completions endpoint")
    LLM_API_KEY: str = Field(default="not-set",
        description="Bearer key for the LLM endpoint")
    LLM_MODEL: str = Field(default="local-model",
        description="Model name to request from the LLM endpoint")
    LLM_VERIFY_ENABLED: bool = Field(default=True,
        description="Whether the LLM relevance flag gates ingestion; the extraction chain runs either way")
    LLM_TIMEOUT_SECONDS: float = Field(default=60.0,
        description="Per-call timeout for the extraction chain")
    LLM_MAX_CONCURRENCY: int = Field(default=4,
        description="Max concurrent extraction calls during an ingestion pass")
    LLM_MAX_INPUT_CHARS: int = Field(default=12000,
        description="Article text is truncated to this many characters before the extraction call")
    LLM_MAX_OUTPUT_TOKENS: int = Field(default=2048,
        description="Max completion tokens requested per extraction call")

    # Entity-overlap dedup (natasha NER) — catches the same story reported by different sources
    ENTITY_DEDUP_ENABLED: bool = Field(default=True,
        description="Skip storing a candidate whose named entities overlap a recent item's")
    ENTITY_DEDUP_WINDOW_HOURS: int = Field(default=48,
        description="How far back (by published_at) to compare candidates against stored items")
    ENTITY_DEDUP_JACCARD_THRESHOLD: float = Field(default=0.6,
        description="Minimum Jaccard similarity between two entity sets to call them duplicates")
    ENTITY_DEDUP_MIN_SHARED: int = Field(default=2,
        description="Minimum shared entities required before two articles are considered duplicates")

    # Telegram (Telethon)
    TELEGRAM_API_ID: int = Field(default=0,
        description="Telegram API ID from https://my.telegram.org")
    TELEGRAM_API_HASH: str = Field(default="",
        description="Telegram API hash from https://my.telegram.org")
    TELEGRAM_SESSION: str = Field(default="",
        description="Telethon StringSession value; mint one with scripts/tg_login.py")

    # Watchlist + ingestion
    WATCHLIST_PATH: Path = Field(default=Path("watchlist.yaml"),
        description="Path to the watchlist YAML file")
    INGEST_INTERVAL_MINUTES: int = Field(default=60,
        description="How often the scheduler runs an ingestion pass")
    INGEST_LOOKBACK_HOURS: int = Field(default=48,
        description="How far back to look when a source has no stored items yet")
    FEED_FETCH_TIMEOUT_SECONDS: float = Field(default=20.0,
        description="Per-feed HTTP timeout for RSS fetches")

    def require_telegram(self) -> None:
        """Raise a readable error if the credentials needed to talk to Telegram are missing."""
        missing = [
            name
            for name, value in (
                ("TELEGRAM_API_ID", self.TELEGRAM_API_ID),
                ("TELEGRAM_API_HASH", self.TELEGRAM_API_HASH),
                ("TELEGRAM_SESSION", self.TELEGRAM_SESSION),
            )
            if not value
        ]
        if missing:
            raise RuntimeError(
                "missing env: "
                + ", ".join(missing)
                + " — set them in .env (run scripts/tg_login.py to obtain TELEGRAM_SESSION)"
            )


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide :class:`Settings` singleton."""
    settings = Settings()
    return settings
