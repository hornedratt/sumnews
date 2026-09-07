"""Standalone check for `NewsRepository` dedup.

Inserts one item, then two more that collide on ``source_url`` and on ``content_hash``
respectively, and asserts only the first lands. Cleans up its own rows so re-runs are safe.
Run: ``make db-smoke`` (or ``uv run python scripts/db_smoke.py``).
"""

import asyncio
import datetime

from sqlalchemy import delete

from sumnews.database.engine import dispose_engine, init_models, session_scope
from sumnews.database.models import NewsItem
from sumnews.database.news import NewsRepository, content_hash
from sumnews.database.schemas import NewsItemCreate
from sumnews.loggers import configure_logging, logger
from sumnews.typed import Category, Priority, SourceType

_SOURCE = "db_smoke"


def _item(url: str, title: str, text: str) -> NewsItemCreate:
    return NewsItemCreate(
        source_type=SourceType.RSS,
        source_name=_SOURCE,
        source_url=url,
        content_hash=content_hash(title, text),
        title=title,
        raw_text=text,
        published_at=datetime.datetime.now(datetime.UTC),
        matched_terms=["acme"],
        is_relevant=True,
        llm_verified=True,
        summary="A summary.",
        category=Category.REGULATION,
        priority=Priority.HIGH,
    )


async def main() -> None:
    configure_logging()
    await init_models()

    async with session_scope() as session:
        await session.execute(delete(NewsItem).where(NewsItem.source_name == _SOURCE))

    async with session_scope() as session:
        repo = NewsRepository(session)

        first = await repo.add_if_new(_item("https://x/1", "Regulator fines Acme", "Body one."))
        assert first is not None, "first insert should succeed"

        dup_url = await repo.add_if_new(_item("https://x/1", "Different headline", "Different body."))
        assert dup_url is None, "same source_url must be rejected"

        dup_hash = await repo.add_if_new(_item("https://x/2", "Regulator fines Acme", "Body one."))
        assert dup_hash is None, "same content_hash must be rejected"

    async with session_scope() as session:
        await session.execute(delete(NewsItem).where(NewsItem.source_name == _SOURCE))

    await dispose_engine()
    logger.info("db_smoke | dedup=ok url=rejected content_hash=rejected")
    print("OK: dedup on source_url and content_hash both work")


if __name__ == "__main__":
    asyncio.run(main())
