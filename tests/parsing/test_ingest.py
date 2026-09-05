import uuid
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sumnews.database.news import NewsRepository
from sumnews.database.schemas import NewsFilter
from sumnews.extracting.schema import Extraction
from sumnews.parsing.ingest import run_ingest
from sumnews.parsing.manager import IngestManager
from sumnews.parsing.telegram import normalize_channel
from sumnews.parsing.types import RawArticle
from sumnews.typed import Category, Priority, SourceType
from sumnews.watchlist import Company, Watchlist

NOW = datetime(2025, 3, 1, 12, 0, tzinfo=UTC)


class FakeTelegram:
    def __init__(self, articles: list[RawArticle]) -> None:
        self._articles = articles

    async def fetch(self, channels: Iterable[str], since: datetime) -> list[RawArticle]:
        return list(self._articles)


class FakeExtractor:
    """No LLM call — keyword match already decided candidacy in these tests."""

    async def extract(self, article: RawArticle) -> Extraction:
        return Extraction(
            is_relevant=True,
            relevance_reason="matched a watchlist term",
            summary="",
            category=Category.TRENDS,
            priority=Priority.LOW,
            priority_reason="",
        )


def _watchlist(channel: str) -> Watchlist:
    return Watchlist(
        company=Company(name="Ромашка"),
        keywords=("импортозамещение",),
        telegram_channels=(channel,),
    )


def _art(channel: str, url: str, title: str, text: str) -> RawArticle:
    return RawArticle(SourceType.TELEGRAM, channel, url, title, text, NOW)


def _manager(
    session: AsyncSession, channel: str, telegram: FakeTelegram | None, *, llm_verify: bool = True
) -> IngestManager:
    return IngestManager(
        repo=NewsRepository(session),
        watchlist=_watchlist(channel),
        telegram=telegram,
        extractor=FakeExtractor(),
        lookback_hours=168,
        llm_verify_enabled=llm_verify,
        llm_max_concurrency=4,
    )


async def test_ingest_stores_candidates_and_skips_noise(session: AsyncSession) -> None:
    channel = f"chan-{uuid.uuid4()}"
    articles = [
        _art(channel, f"https://t.me/{channel}/1", "Про Ромашку", "Компания Ромашка растёт"),
        _art(channel, f"https://t.me/{channel}/2", "Погода", "сегодня солнечно"),  # not candidate
        _art(channel, f"https://t.me/{channel}/3", "Реформа", "курс на импортозамещение"),
    ]
    stats = await run_ingest(_manager(session, channel, FakeTelegram(articles)))

    assert stats.fetched == 3
    assert stats.candidates == 2
    assert stats.stored == 2
    assert stats.skipped_existing == 0

    rows, total = await NewsRepository(session).list(NewsFilter(source_name=channel))
    assert total == 2
    assert rows  # sanity: rows were actually persisted


async def test_rerun_is_incremental(session: AsyncSession) -> None:
    channel = f"chan-{uuid.uuid4()}"
    articles = [_art(channel, f"https://t.me/{channel}/1", "Про Ромашку", "Ромашка снова в новостях")]

    first = await run_ingest(_manager(session, channel, FakeTelegram(articles)))
    assert first.stored == 1

    # same session, fresh manager -> the item is already stored
    second = await run_ingest(_manager(session, channel, FakeTelegram(articles)))
    assert second.stored == 0
    assert second.skipped_existing == 1


async def test_no_llm_marks_items_unverified(session: AsyncSession) -> None:
    channel = f"chan-{uuid.uuid4()}"
    articles = [_art(channel, f"https://t.me/{channel}/1", "Ромашка", "Ромашка и импортозамещение")]
    await run_ingest(_manager(session, channel, FakeTelegram(articles), llm_verify=False))

    rows, _ = await NewsRepository(session).list(NewsFilter(source_name=channel))
    assert rows[0].llm_verified is False
    assert rows[0].matched_terms  # keyword hits recorded


async def test_runs_without_telegram(session: AsyncSession) -> None:
    channel = f"chan-{uuid.uuid4()}"
    stats = await run_ingest(_manager(session, channel, None))  # feeds-only, empty rss_feeds
    assert stats.fetched == 0
    assert stats.stored == 0


class RecordingTelegram:
    """Records the `since` cursor it is called with, so we can assert the cursor advances."""

    def __init__(self, articles: list[RawArticle]) -> None:
        self._articles = articles
        self.since_calls: list[datetime] = []

    async def fetch(self, channels: Iterable[str], since: datetime) -> list[RawArticle]:
        self.since_calls.append(since)
        return list(self._articles)


async def test_cursor_is_keyed_by_normalized_channel(session: AsyncSession) -> None:
    # Watchlist holds an @-prefixed entry; TelegramSource stores the bare name. The incremental
    # cursor must resume from the stored item, not fall back to the lookback floor.
    raw_entry = f"@Chan_{uuid.uuid4().hex[:8]}"
    stored_name = normalize_channel(raw_entry)
    recent = datetime.now(UTC) - timedelta(hours=1)
    article = RawArticle(
        SourceType.TELEGRAM, stored_name, f"https://t.me/{stored_name}/1",
        "Ромашка", "Ромашка и импортозамещение", recent,
    )
    telegram = RecordingTelegram([article])
    manager = IngestManager(
        repo=NewsRepository(session),
        watchlist=_watchlist(raw_entry),
        telegram=telegram,
        extractor=FakeExtractor(),
        lookback_hours=168,
        llm_verify_enabled=True,
        llm_max_concurrency=4,
    )

    await run_ingest(manager)  # stores the item
    await run_ingest(manager)  # second pass — cursor should now point at `recent`

    assert telegram.since_calls[0] < recent  # first pass: lookback floor
    assert telegram.since_calls[1] == recent  # second pass: resumed at the stored published_at
