"""The ingest orchestrator: fetch → dedup → keyword filter → extract → persist.

`run_ingest` is what `scripts/run_ingest.py` (and later the scheduler job) calls each pass.
"""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum, auto

from sumnews.database.news import NewsRepository, content_hash
from sumnews.database.schemas import NewsItemCreate
from sumnews.loggers import logger
from sumnews.parsing import dedup, keyword_filter
from sumnews.parsing.feeds import fetch_feeds
from sumnews.parsing.manager import IngestManager
from sumnews.parsing.telegram import normalize_channel
from sumnews.parsing.types import RawArticle


@dataclass(slots=True)
class IngestStats:
    fetched: int = 0
    candidates: int = 0
    rejected: int = 0
    stored: int = 0
    skipped_existing: int = 0
    entity_duplicates: int = 0
    errors: int = 0


class _Outcome(Enum):
    SKIPPED_EXISTING = auto()
    NOT_CANDIDATE = auto()
    REJECTED = auto()
    STORED = auto()
    DUP = auto()  # lost a dedup race at insert time
    ENTITY_DUP = auto()  # same story, different source — caught by entity overlap


async def run_ingest(manager: IngestManager) -> IngestStats:
    """Fetch every watchlist source, keyword-filter, extract, and persist. One pass, no loop."""
    now = datetime.now(UTC)
    floor = now - timedelta(hours=manager.lookback_hours)
    repo = manager.repo

    # Per-source cursor: pick up where the last successful ingest left off, but never go
    # further back than the lookback floor (a source with no stored items yet is capped there).
    feed_sources = [
        (feed, await _since(repo, feed.name, floor)) for feed in manager.watchlist.rss_feeds
    ]
    # Key the cursor by the same normalized name TelegramSource stores as source_name.
    channel_sources = [
        (channel, await _since(repo, channel, floor))
        for channel in (normalize_channel(raw) for raw in manager.watchlist.telegram_channels)
    ]

    tasks = [fetch_feeds((feed,), since) for feed, since in feed_sources]
    if manager.telegram is not None:
        tasks += [manager.telegram.fetch([channel], since) for channel, since in channel_sources]

    results = await asyncio.gather(*tasks, return_exceptions=True)
    articles: list[RawArticle] = []
    fetch_errors = 0
    for result in results:
        if isinstance(result, BaseException):
            fetch_errors += 1
            logger.warning("ingest | source_failed error=%r", result)
        else:
            articles.extend(result)

    sem = asyncio.Semaphore(manager.llm_max_concurrency)
    repo_lock = asyncio.Lock()  # AsyncSession isn't safe for concurrent use; extraction still is
    # Seeded from recent DB history, then appended to (under repo_lock) as this pass's own
    # candidates clear the check — so two near-duplicates in the same batch also get caught.
    entity_pool: list[list[str]] = []
    if manager.entity_dedup_enabled:
        dedup_floor = now - timedelta(hours=manager.entity_dedup_window_hours)
        entity_pool = await repo.recent_entities(dedup_floor)

    outcomes = await asyncio.gather(
        *(_handle(article, manager, sem, repo_lock, entity_pool) for article in articles)
    )

    stats = IngestStats(fetched=len(articles), errors=fetch_errors)
    for outcome in outcomes:
        if outcome in (_Outcome.SKIPPED_EXISTING, _Outcome.DUP):
            stats.skipped_existing += 1
        elif outcome is _Outcome.ENTITY_DUP:
            stats.candidates += 1
            stats.entity_duplicates += 1
        elif outcome is _Outcome.REJECTED:
            stats.candidates += 1
            stats.rejected += 1
        elif outcome is _Outcome.STORED:
            stats.candidates += 1
            stats.stored += 1

    logger.info(
        "ingest | done fetched=%d candidates=%d stored=%d rejected=%d skipped_existing=%d "
        "entity_duplicates=%d errors=%d",
        stats.fetched, stats.candidates, stats.stored, stats.rejected,
        stats.skipped_existing, stats.entity_duplicates, stats.errors,
    )
    return stats


async def _since(repo: NewsRepository, source_name: str, floor: datetime) -> datetime:
    latest = await repo.latest_published(source_name)
    return max(latest, floor) if latest is not None else floor


async def _handle(
    article: RawArticle,
    manager: IngestManager,
    sem: asyncio.Semaphore,
    repo_lock: asyncio.Lock,
    entity_pool: list[list[str]],
) -> _Outcome:
    chash = content_hash(article.title, article.text)
    async with repo_lock:
        if await manager.repo.exists(article.url, chash):
            return _Outcome.SKIPPED_EXISTING

    matched = keyword_filter.match(article, manager.watchlist)
    if not matched:
        return _Outcome.NOT_CANDIDATE

    entities: list[str] = []
    if manager.entity_dedup_enabled:
        entities = await asyncio.to_thread(
            manager.entity_extractor.extract, article.title, article.text
        )
        async with repo_lock:
            if dedup.is_duplicate(
                entities,
                entity_pool,
                threshold=manager.entity_dedup_threshold,
                min_shared=manager.entity_dedup_min_shared,
            ):
                return _Outcome.ENTITY_DUP
            entity_pool.append(entities)

    async with sem:
        extraction = await manager.extractor.extract(article)  # never raises; falls back on error

    if manager.llm_verify_enabled and not extraction.is_relevant:
        return _Outcome.REJECTED

    item = NewsItemCreate(
        source_type=article.source_type,
        source_name=article.source_name,
        source_url=article.url,
        content_hash=chash,
        title=article.title,
        raw_text=article.text,
        published_at=article.published_at,
        matched_terms=matched,
        is_relevant=extraction.is_relevant,
        llm_verified=manager.llm_verify_enabled,
        entities=entities,
        summary=extraction.summary,
        category=extraction.category,
        priority=extraction.priority,
    )
    async with repo_lock:
        stored = await manager.repo.add_if_new(item)
    return _Outcome.STORED if stored is not None else _Outcome.DUP
