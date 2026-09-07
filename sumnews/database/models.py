"""SQLAlchemy ORM models.

One table, ``news_items``. Enum columns are stored as short strings (``native_enum=False``) so the
schema stays additive-friendly — a new `Category` needs no `ALTER TYPE`.
"""

import datetime
import uuid

from sqlalchemy import Boolean, DateTime, Enum, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from sumnews.typed import Category, Priority, SourceType


def utcnow() -> datetime.datetime:
    """Timezone-aware current time. Passed as a callable default — SQLAlchemy calls it per row."""
    return datetime.datetime.now(datetime.UTC)


def _enum_column(enum_type: type, length: int) -> Enum:
    """A VARCHAR-backed enum column that stores ``.value`` and hands back the enum member."""
    return Enum(
        enum_type,
        native_enum=False,
        length=length,
        values_callable=lambda members: [member.value for member in members],
    )


class Base(DeclarativeBase):
    """Declarative base; ``Base.metadata`` is what `init_models` builds the schema from."""


class NewsItem(Base):
    """A single gathered, filtered and (usually) extracted news item."""

    __tablename__ = "news_items"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    # Provenance
    source_type: Mapped[SourceType] = mapped_column(_enum_column(SourceType, length=16))
    source_name: Mapped[str] = mapped_column(String(200))
    source_url: Mapped[str] = mapped_column(Text, unique=True)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)

    # Raw content
    title: Mapped[str] = mapped_column(Text)
    raw_text: Mapped[str] = mapped_column(Text)
    published_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    # Filtering
    matched_terms: Mapped[list[str]] = mapped_column(JSONB, default=list)
    is_relevant: Mapped[bool] = mapped_column(Boolean, default=True)
    llm_verified: Mapped[bool] = mapped_column(Boolean, default=False)

    # Extraction
    summary: Mapped[str | None] = mapped_column(Text)
    category: Mapped[Category | None] = mapped_column(_enum_column(Category, length=16))
    priority: Mapped[Priority | None] = mapped_column(_enum_column(Priority, length=8))

    # Human review
    user_notes: Mapped[str] = mapped_column(Text, default="")
    user_edited: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
