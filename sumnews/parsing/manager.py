"""`IngestManager` — the dependencies one ingest pass needs, built once by the caller and
reused by `scripts/run_ingest.py` (and later the scheduler job).

Holds a `NewsRepository` bound to a caller-provided session: the caller owns the session's
lifetime (commit/rollback), `run_ingest` just uses it.
"""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from sumnews.database.news import NewsRepository
from sumnews.extracting.chain import Extractor
from sumnews.loggers import logger
from sumnews.parsing.telegram import TelegramSource
from sumnews.settings import Settings
from sumnews.watchlist import Watchlist


@dataclass(slots=True)
class IngestManager:
    repo: NewsRepository
    watchlist: Watchlist
    telegram: TelegramSource | None
    extractor: Extractor
    lookback_hours: int
    llm_verify_enabled: bool
    llm_max_concurrency: int
    article_fetch_concurrency: int

    @classmethod
    def build(
        cls,
        settings: Settings,
        watchlist: Watchlist,
        session: AsyncSession,
        *,
        telegram: TelegramSource | None = None,
        llm_verify_enabled: bool | None = None,
        lookback_hours: int | None = None,
    ) -> "IngestManager":
        """Assemble the per-pass dependencies. Pass `telegram` to reuse an already-connected
        client (the scheduler builds one manager per run but connects Telethon once at startup);
        omit it and one is created from `TELEGRAM_*` when those are set."""
        if telegram is None and (
            settings.TELEGRAM_API_ID and settings.TELEGRAM_API_HASH and settings.TELEGRAM_SESSION
        ):
            telegram = TelegramSource(
                settings.TELEGRAM_API_ID, settings.TELEGRAM_API_HASH, settings.TELEGRAM_SESSION
            )
        elif telegram is None:
            logger.warning("manager | telegram disabled — TELEGRAM_* not set; feeds only")

        return cls(
            repo=NewsRepository(session),
            watchlist=watchlist,
            telegram=telegram,
            extractor=Extractor(settings, watchlist),
            lookback_hours=lookback_hours
            if lookback_hours is not None
            else settings.INGEST_LOOKBACK_HOURS,
            llm_verify_enabled=llm_verify_enabled
            if llm_verify_enabled is not None
            else settings.LLM_VERIFY_ENABLED,
            llm_max_concurrency=settings.LLM_MAX_CONCURRENCY,
            article_fetch_concurrency=settings.ARTICLE_FETCH_CONCURRENCY,
        )
