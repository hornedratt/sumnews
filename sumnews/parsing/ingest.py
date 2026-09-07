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
from sumnews.parsing import keyword_filter
from sumnews.parsing.article import fetch_markdown
from sumnews.parsing.feeds import fetch_feeds
from sumnews.parsing.manager import IngestManager
from sumnews.parsing.telegram import normalize_channel
from sumnews.parsing.types import RawArticle
from sumnews.typed import Category, Priority


@dataclass(slots=True)
class IngestStats:
    fetched: int = 0
    candidates: int = 0
    rejected: int = 0
    promo: int = 0
    stored: int = 0
    skipped_existing: int = 0
    errors: int = 0


class _Outcome(Enum):
    SKIPPED_EXISTING = auto()
    NOT_CANDIDATE = auto()
    REJECTED = auto()
    PROMO = auto()  # tracked company's own ad / PR — dropped, not stored
    STORED = auto()
    DUP = auto()  # lost a dedup race at insert time


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

    llm_sem = asyncio.Semaphore(manager.llm_max_concurrency)
    http_sem = asyncio.Semaphore(manager.article_fetch_concurrency)
    repo_lock = asyncio.Lock()  # AsyncSession isn't safe for concurrent use; fetch/extract are
    outcomes = await asyncio.gather(
        *(_handle(article, manager, llm_sem, http_sem, repo_lock) for article in articles)
    )

    stats = IngestStats(fetched=len(articles), errors=fetch_errors)
    for outcome in outcomes:
        if outcome in (_Outcome.SKIPPED_EXISTING, _Outcome.DUP):
            stats.skipped_existing += 1
        elif outcome is _Outcome.REJECTED:
            stats.candidates += 1
            stats.rejected += 1
        elif outcome is _Outcome.PROMO:
            stats.candidates += 1
            stats.promo += 1
        elif outcome is _Outcome.STORED:
            stats.candidates += 1
            stats.stored += 1

    logger.info(
        "ingest | done fetched=%d candidates=%d stored=%d rejected=%d promo=%d "
        "skipped_existing=%d errors=%d",
        stats.fetched, stats.candidates, stats.stored, stats.rejected, stats.promo,
        stats.skipped_existing, stats.errors,
    )
    return stats


async def _since(repo: NewsRepository, source_name: str, floor: datetime) -> datetime:
    latest = await repo.latest_published(source_name)
    return max(latest, floor) if latest is not None else floor


async def _handle(
    article: RawArticle,
    manager: IngestManager,
    llm_sem: asyncio.Semaphore,
    http_sem: asyncio.Semaphore,
    repo_lock: asyncio.Lock,
) -> _Outcome:
    # URL-based early-out — cheap, and done before any fetch/extract work.
    async with repo_lock:
        if await manager.repo.exists(article.url):
            return _Outcome.SKIPPED_EXISTING

    matched = keyword_filter.match(article, manager.watchlist)
    if not matched:
        return _Outcome.NOT_CANDIDATE

    # Body: Telegram posts (and the rare feed teaser) already carry it; RSS items get the
    # article page fetched and rendered to Markdown.
    if article.body is not None:
        body = article.body
    else:
        async with http_sem:
            body = await fetch_markdown(article.url) or ""

    async with llm_sem:
        extraction = await manager.extractor.extract(article, body)  # never raises
    category = Category(extraction.category)

    if category is Category.PROMO:  # the company's own ad / PR — never stored
        return _Outcome.PROMO
    if manager.llm_verify_enabled and not extraction.is_relevant:
        return _Outcome.REJECTED

    item = NewsItemCreate(
        source_type=article.source_type,
        source_name=article.source_name,
        source_url=article.url,
        content_hash=content_hash(article.title, body),
        title=article.title,
        raw_text=body,
        published_at=article.published_at,
        matched_terms=matched,
        is_relevant=extraction.is_relevant,
        llm_verified=manager.llm_verify_enabled,
        summary=extraction.summary,
        category=category,
        priority=Priority(extraction.priority),
    )
    async with repo_lock:
        stored = await manager.repo.add_if_new(item)
    return _Outcome.STORED if stored is not None else _Outcome.DUP
