"""`NewsRepository` — every read and write the ingest pipeline and web UI need against `news_items`."""

import datetime
import hashlib
import re
import uuid

from sqlalchemy import ColumnElement, Select, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from sumnews.database.models import NewsItem
from sumnews.database.schemas import NewsFilter, NewsItemCreate
from sumnews.typed import Category, NewsSort, Priority

_WHITESPACE = re.compile(r"\s+")

# HIGH first when sorting by priority; NULL / unknown sink to the bottom.
_PRIORITY_RANK = case(
    (NewsItem.priority == Priority.HIGH, 3),
    (NewsItem.priority == Priority.MEDIUM, 2),
    (NewsItem.priority == Priority.LOW, 1),
    else_=0,
)


def content_hash(title: str, text: str) -> str:
    """Stable fingerprint of an article's content — same story on two URLs hashes identically."""
    normalized = _WHITESPACE.sub(" ", f"{title}\n{text}".strip().casefold())
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return digest


def _filter_conditions(filters: NewsFilter) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = []
    if filters.category is not None:
        conditions.append(NewsItem.category == filters.category)
    if filters.priority is not None:
        conditions.append(NewsItem.priority == filters.priority)
    if filters.source_name is not None:
        conditions.append(NewsItem.source_name == filters.source_name)
    if filters.is_relevant is not None:
        conditions.append(NewsItem.is_relevant.is_(filters.is_relevant))
    if filters.query:
        pattern = f"%{filters.query}%"
        conditions.append(or_(NewsItem.title.ilike(pattern), NewsItem.summary.ilike(pattern)))
    return conditions


def _apply_order(statement: Select[tuple[NewsItem]], sort: NewsSort) -> Select[tuple[NewsItem]]:
    if sort is NewsSort.PRIORITY:
        return statement.order_by(_PRIORITY_RANK.desc(), NewsItem.published_at.desc().nullslast())
    return statement.order_by(
        NewsItem.published_at.desc().nullslast(), NewsItem.fetched_at.desc()
    )


class NewsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def exists(self, source_url: str, content_hash: str) -> bool:
        """Cheap existence probe — same identity rule as `add_if_new`, without inserting."""
        existing = await self._session.scalar(
            select(NewsItem.id)
            .where(or_(NewsItem.source_url == source_url, NewsItem.content_hash == content_hash))
            .limit(1)
        )
        return existing is not None

    async def add_if_new(self, item: NewsItemCreate) -> NewsItem | None:
        """Insert unless an item with the same ``source_url`` or ``content_hash`` already exists."""
        existing = await self._session.scalar(
            select(NewsItem.id)
            .where(
                or_(
                    NewsItem.source_url == item.source_url,
                    NewsItem.content_hash == item.content_hash,
                )
            )
            .limit(1)
        )
        if existing is not None:
            return None
        news_item = NewsItem(**item.model_dump())
        self._session.add(news_item)
        await self._session.flush()
        return news_item

    async def get(self, item_id: uuid.UUID) -> NewsItem | None:
        news_item = await self._session.get(NewsItem, item_id)
        return news_item

    async def list(
        self,
        filters: NewsFilter,
        sort: NewsSort = NewsSort.NEWEST,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[NewsItem], int]:
        """Return one page of items matching `filters` in `sort` order, plus the total match count."""
        conditions = _filter_conditions(filters)

        total = await self._session.scalar(
            select(func.count()).select_from(NewsItem).where(*conditions)
        )

        statement = _apply_order(select(NewsItem).where(*conditions), sort).limit(limit).offset(offset)
        rows = list(await self._session.scalars(statement))
        return rows, total or 0

    async def update_fields(
        self,
        item_id: uuid.UUID,
        *,
        summary: str | None = None,
        category: Category | None = None,
        priority: Priority | None = None,
        user_notes: str | None = None,
    ) -> NewsItem:
        """Apply the non-``None`` fields and flag the row as human-edited."""
        news_item = await self._session.get(NewsItem, item_id)
        if news_item is None:
            raise LookupError(f"news_item id={item_id} not found")

        changes: dict[str, object | None] = {
            "summary": summary,
            "category": category,
            "priority": priority,
            "user_notes": user_notes,
        }
        for field, value in changes.items():
            if value is not None:
                setattr(news_item, field, value)
        news_item.user_edited = True
        await self._session.flush()
        return news_item

    async def latest_published(self, source_name: str) -> datetime.datetime | None:
        """Newest ``published_at`` seen for a source — the incremental-fetch cursor."""
        value = await self._session.scalar(
            select(func.max(NewsItem.published_at)).where(NewsItem.source_name == source_name)
        )
        return value
