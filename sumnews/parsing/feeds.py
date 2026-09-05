"""RSS/Atom fetching: `fetch_feeds` pulls entries newer than `since` from each configured feed.

Fed by `Watchlist.rss_feeds` (Section 3 plan); output is a plain list of `RawArticle`, consumed
downstream by the keyword prefilter and `extracting.Extractor`.
"""

import re
import time
from asyncio import to_thread
from datetime import UTC, datetime

import feedparser

from sumnews.loggers import logger
from sumnews.parsing.types import RawArticle
from sumnews.typed import SourceType
from sumnews.watchlist import Feed

_TAG_RE = re.compile(r"<[^>]+>")


def _struct_to_dt(parsed: time.struct_time | None) -> datetime | None:
    if not parsed:
        return None
    return datetime(*parsed[:6], tzinfo=UTC)


def _entry_text(entry: object) -> str:
    content = getattr(entry, "content", None)
    if content:
        return _TAG_RE.sub(" ", content[0].get("value", "")).strip()
    raw = entry.get("summary", "") if hasattr(entry, "get") else ""
    return _TAG_RE.sub(" ", raw).strip()


def _parse_one(feed: Feed, since: datetime | None) -> list[RawArticle]:
    parsed = feedparser.parse(feed.url)
    out: list[RawArticle] = []
    for entry in parsed.entries:
        published = _struct_to_dt(entry.get("published_parsed"))
        if since is not None and published is not None and published < since:
            continue  # older than the window; keep undated entries (can't prove they're old)
        out.append(
            RawArticle(
                source_type=SourceType.RSS,
                source_name=feed.name,
                url=entry.get("link", ""),
                title=(entry.get("title") or "").strip(),
                text=_entry_text(entry),
                published_at=published,
            )
        )
    return out


async def fetch_feeds(feeds: tuple[Feed, ...], since: datetime | None) -> list[RawArticle]:
    """Fetch entries newer than `since` from each feed. One bad feed never aborts the run."""
    out: list[RawArticle] = []
    for feed in feeds:
        try:
            articles = await to_thread(_parse_one, feed, since)
            out.extend(articles)
            logger.info("feeds | feed=%s entries=%d", feed.name, len(articles))
        except Exception as error:  # a single feed is an external boundary; isolate its failure
            logger.warning("feeds | fetch_failed feed=%s error=%r", feed.name, error)
    logger.info("feeds | fetched articles=%d feeds=%d", len(out), len(feeds))
    return out
