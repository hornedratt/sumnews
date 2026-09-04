"""Shared fixtures.

DB tests run against the dev Postgres from ``compose.yaml`` (``make db-up``). Each test gets a
session inside a transaction that is rolled back on teardown, so nothing persists and tests are
order-independent even when the tables already hold data.

The engine is function-scoped with `NullPool`: pytest-asyncio gives each test its own event loop,
and a pooled asyncpg connection cannot cross loops.
"""

import datetime
import uuid
from collections.abc import AsyncIterator, Callable

import pytest
import pytest_asyncio
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool
from sumnews.database.models import Base
from sumnews.database.news import content_hash
from sumnews.database.schemas import NewsItemCreate
from sumnews.settings import get_settings
from sumnews.typed import Category, Priority, SourceType

NewsItemFactory = Callable[..., NewsItemCreate]


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(get_settings().DATABASE_URL, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
    except OperationalError:  # pragma: no cover - infra guard
        await engine.dispose()
        pytest.skip("Postgres not reachable — run `make db-up`")
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with engine.connect() as connection:
        transaction = await connection.begin()
        db_session = AsyncSession(
            bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        try:
            yield db_session
        finally:
            await db_session.close()
            await transaction.rollback()


@pytest.fixture
def news_item_factory() -> NewsItemFactory:
    """Build a `NewsItemCreate` with sane defaults; override any field per call."""

    def make(
        *,
        source_name: str,
        source_url: str | None = None,
        title: str = "Regulator opens probe into Acme",
        raw_text: str | None = None,
        published_at: datetime.datetime | None = None,
        source_type: SourceType = SourceType.RSS,
        matched_terms: list[str] | None = None,
        is_relevant: bool = True,
        llm_verified: bool = True,
        summary: str | None = "Regulator opened a probe into Acme.",
        category: Category | None = Category.REGULATION,
        priority: Priority | None = Priority.MEDIUM,
    ) -> NewsItemCreate:
        # Unique by default so independent items don't collide on content_hash; the dedup test
        # passes title + raw_text explicitly to force a collision.
        body = raw_text if raw_text is not None else f"The regulator opened a probe. ({uuid.uuid4()})"
        return NewsItemCreate(
            source_type=source_type,
            source_name=source_name,
            source_url=source_url or f"https://example.test/{uuid.uuid4()}",
            content_hash=content_hash(title, body),
            title=title,
            raw_text=body,
            published_at=published_at,
            matched_terms=matched_terms or ["acme"],
            is_relevant=is_relevant,
            llm_verified=llm_verified,
            summary=summary,
            category=category,
            priority=priority,
        )

    return make
