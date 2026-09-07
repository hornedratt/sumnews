"""`NewsRepository` behaviour: dedup, filtered/sorted listing, partial updates, the fetch cursor."""

import datetime
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sumnews.database.news import NewsRepository
from sumnews.database.schemas import NewsFilter
from sumnews.typed import Category, NewsSort, Priority

from tests.conftest import NewsItemFactory

UTC = datetime.UTC


def _now() -> datetime.datetime:
    return datetime.datetime.now(UTC)


async def test_add_if_new_rejects_duplicate_url_and_duplicate_hash(
    session: AsyncSession, news_item_factory: NewsItemFactory
) -> None:
    repo = NewsRepository(session)
    source = f"src-{uuid.uuid4()}"

    first = await repo.add_if_new(
        news_item_factory(source_name=source, source_url="https://dup.test/1", title="A", raw_text="B")
    )
    assert first is not None

    same_url = await repo.add_if_new(
        news_item_factory(source_name=source, source_url="https://dup.test/1", title="X", raw_text="Y")
    )
    same_hash = await repo.add_if_new(
        news_item_factory(source_name=source, source_url="https://dup.test/2", title="A", raw_text="B")
    )
    assert same_url is None
    assert same_hash is None


async def test_exists_matches_on_url_or_hash_without_inserting(
    session: AsyncSession, news_item_factory: NewsItemFactory
) -> None:
    repo = NewsRepository(session)
    item = news_item_factory(source_name=f"src-{uuid.uuid4()}", source_url="https://dup.test/probe")

    assert await repo.exists(item.source_url, item.content_hash) is False

    stored = await repo.add_if_new(item)
    assert stored is not None

    assert await repo.exists(item.source_url, "unrelated-hash") is True
    assert await repo.exists("https://unrelated.test/", item.content_hash) is True
    assert await repo.exists("https://unrelated.test/", "unrelated-hash") is False


async def test_list_filters_by_category_priority_and_query(
    session: AsyncSession, news_item_factory: NewsItemFactory
) -> None:
    repo = NewsRepository(session)
    source = f"src-{uuid.uuid4()}"

    await repo.add_if_new(
        news_item_factory(
            source_name=source, title="Acme wins tender", category=Category.COMPETITORS,
            priority=Priority.LOW, summary="Acme won a tender.",
        )
    )
    wanted = await repo.add_if_new(
        news_item_factory(
            source_name=source, title="Regulator fines Acme", category=Category.REGULATION,
            priority=Priority.HIGH, summary="A fine was issued.",
        )
    )
    assert wanted is not None

    rows, total = await repo.list(
        NewsFilter(source_name=source, category=Category.REGULATION, priority=Priority.HIGH)
    )
    assert [row.id for row in rows] == [wanted.id]
    assert total == 1

    rows, _ = await repo.list(NewsFilter(source_name=source, query="fines"))
    assert [row.id for row in rows] == [wanted.id]


async def test_list_priority_sort_orders_high_before_low(
    session: AsyncSession, news_item_factory: NewsItemFactory
) -> None:
    repo = NewsRepository(session)
    source = f"src-{uuid.uuid4()}"

    low = await repo.add_if_new(
        news_item_factory(source_name=source, priority=Priority.LOW, published_at=_now())
    )
    high = await repo.add_if_new(
        news_item_factory(
            source_name=source, priority=Priority.HIGH,
            published_at=_now() - datetime.timedelta(days=3),
        )
    )
    medium = await repo.add_if_new(
        news_item_factory(source_name=source, priority=Priority.MEDIUM, published_at=_now())
    )
    assert low and high and medium

    rows, _ = await repo.list(NewsFilter(source_name=source), NewsSort.PRIORITY)
    assert [row.id for row in rows] == [high.id, medium.id, low.id]

    rows, _ = await repo.list(NewsFilter(source_name=source), NewsSort.NEWEST)
    assert rows[-1].id == high.id  # oldest published_at sorts last


async def test_update_fields_applies_only_set_values_and_flags_edited(
    session: AsyncSession, news_item_factory: NewsItemFactory
) -> None:
    repo = NewsRepository(session)
    source = f"src-{uuid.uuid4()}"
    item = await repo.add_if_new(
        news_item_factory(
            source_name=source, category=Category.TRENDS, priority=Priority.LOW, summary="Original.",
        )
    )
    assert item is not None

    updated = await repo.update_fields(
        item.id, priority=Priority.HIGH, user_notes="Escalated — see legal."
    )
    assert updated.priority is Priority.HIGH
    assert updated.user_notes == "Escalated — see legal."
    assert updated.category is Category.TRENDS  # untouched
    assert updated.summary == "Original."  # untouched
    assert updated.user_edited is True


async def test_latest_published_returns_source_max(
    session: AsyncSession, news_item_factory: NewsItemFactory
) -> None:
    repo = NewsRepository(session)
    source = f"src-{uuid.uuid4()}"
    other_source = f"src-{uuid.uuid4()}"
    newest = _now()

    await repo.add_if_new(
        news_item_factory(source_name=source, published_at=newest - datetime.timedelta(hours=5))
    )
    await repo.add_if_new(news_item_factory(source_name=source, published_at=newest))
    await repo.add_if_new(
        news_item_factory(source_name=other_source, published_at=newest + datetime.timedelta(days=1))
    )

    latest = await repo.latest_published(source)
    assert latest == newest
    assert await repo.latest_published(f"missing-{uuid.uuid4()}") is None
