"""Shared enums and lightweight types."""

from enum import StrEnum
from typing import Literal, get_args


class Category(StrEnum):
    """The bucket a news item falls into. Values are the wire form used in the DB and the UI.

    `PROMO` is the exception: the tracked company's own advertising or self-published statements
    (not external reporting about it). Ingest drops `PROMO` items — they never reach the DB.
    """

    REGULATION = "regulation"
    REPUTATION = "reputation"
    COMPETITORS = "competitors"
    TRENDS = "trends"
    PROMO = "promo"


class Priority(StrEnum):
    """How urgently a human should look at the item."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# Literal mirrors of the enums above — the extraction schema uses these so the JSON schema sent to
# the LLM carries an inline `enum` list instead of a `$ref`. Kept in sync by the asserts below.
CategoryValue = Literal["regulation", "reputation", "competitors", "trends", "promo"]
PriorityValue = Literal["high", "medium", "low"]

assert set(get_args(CategoryValue)) == {member.value for member in Category}
assert set(get_args(PriorityValue)) == {member.value for member in Priority}


# Ranking for the "sort by priority" feed order (higher = shown first).
PRIORITY_ORDER: dict[Priority, int] = {
    Priority.HIGH: 3,
    Priority.MEDIUM: 2,
    Priority.LOW: 1,
}


class SourceType(StrEnum):
    """Where a raw article came from."""

    RSS = "rss"
    TELEGRAM = "telegram"


class NewsSort(StrEnum):
    """Feed ordering options."""

    NEWEST = "newest"
    PRIORITY = "priority"
