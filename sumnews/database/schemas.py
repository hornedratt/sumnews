"""Pydantic models for the persistence boundary.

`NewsItemCreate` is what `parsing.ingest` hands to the repository; `NewsItemUpdate` / `NewsFilter`
are the web layer's write and query inputs; `NewsItemRead` is the ORM row serialized out.
"""

import datetime
import uuid

from pydantic import BaseModel, ConfigDict, Field

from sumnews.typed import Category, Priority, SourceType


class NewsItemCreate(BaseModel):
    """A fully-formed item ready to persist. `content_hash` is computed by the caller."""

    source_type: SourceType
    source_name: str
    source_url: str
    content_hash: str
    title: str
    raw_text: str
    published_at: datetime.datetime | None
    matched_terms: list[str] = Field(default_factory=list)
    is_relevant: bool = True
    llm_verified: bool = False
    entities: list[str] = Field(default_factory=list)
    summary: str | None = None
    category: Category | None = None
    priority: Priority | None = None


class NewsItemUpdate(BaseModel):
    """User edits from the review UI. Every field optional — only set ones are applied."""

    summary: str | None = None
    category: Category | None = None
    priority: Priority | None = None
    user_notes: str | None = None


class NewsFilter(BaseModel):
    """Feed filters. ``None`` means 'no constraint on this field'."""

    category: Category | None = None
    priority: Priority | None = None
    source_name: str | None = None
    is_relevant: bool | None = None
    query: str | None = None


class NewsItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_type: SourceType
    source_name: str
    source_url: str
    content_hash: str
    title: str
    raw_text: str
    published_at: datetime.datetime | None
    fetched_at: datetime.datetime
    matched_terms: list[str]
    is_relevant: bool
    llm_verified: bool
    entities: list[str]
    summary: str | None
    category: Category | None
    priority: Priority | None
    user_notes: str
    user_edited: bool
    created_at: datetime.datetime
    updated_at: datetime.datetime