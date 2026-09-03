"""Shared enums and lightweight types."""

from enum import StrEnum


class Category(StrEnum):
    """The bucket a news item falls into. Values are the wire form used in the DB and the UI."""

    REGULATION = "regulation"
    REPUTATION = "reputation"
    COMPETITORS = "competitors"
    TRENDS = "trends"


class Priority(StrEnum):
    """How urgently a human should look at the item."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


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
