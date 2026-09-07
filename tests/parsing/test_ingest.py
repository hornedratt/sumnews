import uuid
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sumnews.database.news import NewsRepository
from sumnews.database.schemas import NewsFilter
from sumnews.extracting.schema import Extraction
from sumnews.parsing import ingest as ingest_module
from sumnews.parsing.ingest import run_ingest
from sumnews.parsing.manager import IngestManager
from sumnews.parsing.telegram import normalize_channel
from sumnews.parsing.types import RawArticle
from sumnews.typed import SourceType
from sumnews.watchlist import Company, Feed, Watchlist

NOW = datetime(2025, 3, 1, 12, 0, tzinfo=UTC)


class FakeTelegram:
    def __init__(self, articles: list[RawArticle]) -> None:
        self._articles = articles

    async def fetch(self, channels: Iterable[str], since: datetime) -> list[RawArticle]:
        return list(self._articles)


class FakeExtractor:
    """No LLM call — keyword match already decided candidacy in these tests."""

    def __init__(self, category: str = "trends") -> None:
        self.bodies: list[str] = []
        self._category = category

    async def extract(self, article: RawArticle, body: str) -> Extraction:
        self.bodies.append(body)
        return Extraction(
            is_relevant=True,
            relevance_reason="matched a watchlist term",
            summary="",
            category=self._category,  # type: ignore[arg-type]
            priority="low",
            priority_reason="",
        )


class FakeEntityExtractor:
    """No natasha model load — returns configured entities per article title, else none."""

    def __init__(self, by_title: dict[str, list[str]] | None = None) -> None:
        self._by_title = by_title or {}

    def extract(self, title: str, text: str) -> list[str]:
        return self._by_title.get(title, [])


def _watchlist(channel: str, *, feeds: tuple[Feed, ...] = ()) -> Watchlist:
    return Watchlist(
        company=Company(name="Ромашка"),
        keywords=("импортозамещение",),
        telegram_channels=(channel,),
        rss_feeds=feeds,
    )


def _tg_article(channel: str, msg_id: int, title: str, body: str) -> RawArticle:
    return RawArticle(
        SourceType.TELEGRAM, channel, f"https://t.me/{channel}/{msg_id}", title, NOW, body=body
    )


def _manager(
    session: AsyncSession,
    watchlist: Watchlist,
    telegram: object,
    *,
    llm_verify: bool = True,
    extractor: FakeExtractor | None = None,
    entity_dedup_enabled: bool = False,
    entity_extractor: FakeEntityExtractor | None = None,
) -> IngestManager:
    return IngestManager(
        repo=NewsRepository(session),
        watchlist=watchlist,
        telegram=telegram,
        extractor=extractor or FakeExtractor(),
        entity_extractor=entity_extractor or FakeEntityExtractor(),
        lookback_hours=168,
        llm_verify_enabled=llm_verify,
        llm_max_concurrency=4,
        entity_dedup_enabled=entity_dedup_enabled,
        entity_dedup_window_hours=48,
        entity_dedup_threshold=0.6,
        entity_dedup_min_shared=2,
        article_fetch_concurrency=4,
    )


async def test_ingest_stores_candidates_and_skips_noise(session: AsyncSession) -> None:
    channel = f"chan-{uuid.uuid4()}"
    articles = [
        _tg_article(channel, 1, "Ромашка снова растёт", "Компания Ромашка растёт"),
        _tg_article(channel, 2, "Погода", "сегодня солнечно"),  # title has no term
        _tg_article(channel, 3, "Курс на импортозамещение", "детали курса"),
    ]
    stats = await run_ingest(_manager(session, _watchlist(channel), FakeTelegram(articles)))

    assert stats.fetched == 3
    assert stats.candidates == 2
    assert stats.stored == 2
    assert stats.skipped_existing == 0

    _, total = await NewsRepository(session).list(NewsFilter(source_name=channel))
    assert total == 2


async def test_promo_category_is_dropped_not_stored(session: AsyncSession) -> None:
    channel = f"chan-{uuid.uuid4()}"
    article = _tg_article(channel, 1, "Ромашка запускает новый вклад", "рекламный текст")
    stats = await run_ingest(
        _manager(
            session, _watchlist(channel), FakeTelegram([article]),
            extractor=FakeExtractor(category="promo"),
        )
    )

    assert stats.candidates == 1
    assert stats.promo == 1
    assert stats.stored == 0
    rows, total = await NewsRepository(session).list(NewsFilter(source_name=channel))
    assert total == 0 and rows == []


async def test_entity_dedup_skips_overlapping_recent_story(session: AsyncSession) -> None:
    channel = f"chan-{uuid.uuid4()}"
    first = _tg_article(channel, 1, "Ромашка отчиталась", "Ромашка отчиталась о дивидендах")
    second = _tg_article(channel, 2, "Ромашка снова о дивидендах", "ещё раз про дивиденды Ромашки")
    entity_extractor = FakeEntityExtractor(by_title={
        first.title: ["ромашка", "дивиденды"],
        second.title: ["ромашка", "дивиденды"],
    })

    first_stats = await run_ingest(
        _manager(session, _watchlist(channel), FakeTelegram([first]),
                entity_dedup_enabled=True, entity_extractor=entity_extractor)
    )
    assert first_stats.stored == 1

    second_stats = await run_ingest(
        _manager(session, _watchlist(channel), FakeTelegram([second]),
                entity_dedup_enabled=True, entity_extractor=entity_extractor)
    )
    assert second_stats.stored == 0
    assert second_stats.entity_duplicates == 1

    _, total = await NewsRepository(session).list(NewsFilter(source_name=channel))
    assert total == 1


async def test_telegram_body_is_used_verbatim_as_raw_text(session: AsyncSession) -> None:
    channel = f"chan-{uuid.uuid4()}"
    extractor = FakeExtractor()
    article = _tg_article(channel, 1, "Ромашка и импортозамещение", "Полный текст поста про Ромашку.")
    await run_ingest(
        _manager(session, _watchlist(channel), FakeTelegram([article]), extractor=extractor)
    )

    assert extractor.bodies == ["Полный текст поста про Ромашку."]
    rows, _ = await NewsRepository(session).list(NewsFilter(source_name=channel))
    assert rows[0].raw_text == "Полный текст поста про Ромашку."


async def test_rss_candidate_fetches_markdown_into_raw_text(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    feed = Feed(name="Wire", url="https://wire.test/rss")
    watchlist = _watchlist(f"chan-{uuid.uuid4()}", feeds=(feed,))
    rss_item = RawArticle(
        SourceType.RSS, feed.name, f"https://wire.test/{uuid.uuid4()}",
        "Ромашка получила лицензию", NOW, body=None,
    )

    async def fake_fetch_feeds(feeds: object, since: object) -> list[RawArticle]:
        return [rss_item]

    async def fake_fetch_markdown(url: str) -> str:
        return "# Ромашка\n\nПолный markdown статьи."

    monkeypatch.setattr(ingest_module, "fetch_feeds", fake_fetch_feeds)
    monkeypatch.setattr(ingest_module, "fetch_markdown", fake_fetch_markdown)

    extractor = FakeExtractor()
    await run_ingest(_manager(session, watchlist, None, extractor=extractor))

    assert extractor.bodies == ["# Ромашка\n\nПолный markdown статьи."]
    rows, _ = await NewsRepository(session).list(NewsFilter(source_name=feed.name))
    assert rows[0].raw_text == "# Ромашка\n\nПолный markdown статьи."


async def test_rss_candidate_stored_empty_when_fetch_fails(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    feed = Feed(name="Wire", url="https://wire.test/rss")
    watchlist = _watchlist(f"chan-{uuid.uuid4()}", feeds=(feed,))
    rss_item = RawArticle(
        SourceType.RSS, feed.name, f"https://wire.test/{uuid.uuid4()}",
        "Ромашка под санкциями", NOW, body=None,
    )

    async def fake_fetch_feeds(feeds: object, since: object) -> list[RawArticle]:
        return [rss_item]

    async def fake_fetch_markdown(url: str) -> None:
        return None

    monkeypatch.setattr(ingest_module, "fetch_feeds", fake_fetch_feeds)
    monkeypatch.setattr(ingest_module, "fetch_markdown", fake_fetch_markdown)

    await run_ingest(_manager(session, watchlist, None))

    rows, total = await NewsRepository(session).list(NewsFilter(source_name=feed.name))
    assert total == 1
    assert rows[0].raw_text == ""


async def test_rerun_is_incremental(session: AsyncSession) -> None:
    channel = f"chan-{uuid.uuid4()}"
    articles = [_tg_article(channel, 1, "Ромашка в новостях", "Ромашка снова в новостях")]

    first = await run_ingest(_manager(session, _watchlist(channel), FakeTelegram(articles)))
    assert first.stored == 1

    second = await run_ingest(_manager(session, _watchlist(channel), FakeTelegram(articles)))
    assert second.stored == 0
    assert second.skipped_existing == 1


async def test_no_llm_marks_items_unverified(session: AsyncSession) -> None:
    channel = f"chan-{uuid.uuid4()}"
    articles = [_tg_article(channel, 1, "Ромашка и импортозамещение", "тело")]
    await run_ingest(
        _manager(session, _watchlist(channel), FakeTelegram(articles), llm_verify=False)
    )

    rows, _ = await NewsRepository(session).list(NewsFilter(source_name=channel))
    assert rows[0].llm_verified is False
    assert rows[0].matched_terms


async def test_runs_without_telegram(session: AsyncSession) -> None:
    channel = f"chan-{uuid.uuid4()}"
    stats = await run_ingest(_manager(session, _watchlist(channel), None))
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
    raw_entry = f"@Chan_{uuid.uuid4().hex[:8]}"
    stored_name = normalize_channel(raw_entry)
    recent = datetime.now(UTC) - timedelta(hours=1)
    article = RawArticle(
        SourceType.TELEGRAM, stored_name, f"https://t.me/{stored_name}/1",
        "Ромашка", recent, body="Ромашка и импортозамещение",
    )
    telegram = RecordingTelegram([article])
    manager = _manager(session, _watchlist(raw_entry), telegram)

    await run_ingest(manager)
    await run_ingest(manager)

    assert telegram.since_calls[0] < recent  # first pass: lookback floor
    assert telegram.since_calls[1] == recent  # second pass: resumed at the stored published_at
