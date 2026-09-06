"""Walk the RSS half of the ingest pipeline and show what it produces.

For each feed article: fetch + parse metadata, run `keyword_filter.match` (title-only), and for
every candidate fetch the article page and render it to Markdown (`parsing.article.fetch_markdown`,
the same call ingest uses). Prints the Markdown length per article and writes every fetched
document to `data/md/` for inspection.

    make run-fetch-feeds ARGS='--lookback-hours 72'
    make run-fetch-feeds ARGS='--feed "Lenta" --full'
    make run-fetch-feeds ARGS='--url https://lenta.ru/rss/top7'
    make run-fetch-feeds ARGS='--no-filter'   # treat every article as a candidate

No DB, no LLM.
"""

import argparse
import asyncio
import dataclasses
import hashlib
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

from _dump import dump_articles
from sumnews.loggers import configure_logging, logger
from sumnews.parsing.article import fetch_markdown
from sumnews.parsing.feeds import fetch_feeds
from sumnews.parsing.keyword_filter import match as keyword_match
from sumnews.parsing.types import RawArticle
from sumnews.settings import get_settings
from sumnews.watchlist import Feed, Watchlist, load_watchlist

_MD_DIR = Path("data/md")
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lookback-hours", type=int, default=None, help="window (default: from .env)")
    parser.add_argument("--feed", help="restrict to one watchlist feed, by name")
    parser.add_argument("--url", help="ad-hoc feed URL not in the watchlist")
    parser.add_argument("--full", action="store_true", help="print full Markdown, not a preview")
    parser.add_argument("--no-filter", action="store_true", help="treat every article as a candidate")
    parser.add_argument("--json", action="store_true", help="dump as JSON")
    return parser.parse_args()


def _select_feeds(args: argparse.Namespace, watchlist: Watchlist) -> tuple[Feed, ...]:
    if args.url:
        return (Feed(name="ad-hoc", url=args.url),)
    feeds = watchlist.rss_feeds
    if args.feed:
        feeds = tuple(feed for feed in feeds if feed.name == args.feed)
        if not feeds:
            raise SystemExit(f"no feed named {args.feed!r} in the watchlist")
    return feeds


def _slug(url: str) -> str:
    tail = _SLUG_RE.sub("-", url.split("://", 1)[-1].lower()).strip("-")[:80]
    return f"{tail}-{hashlib.sha1(url.encode()).hexdigest()[:8]}"


def _save_markdown(article: RawArticle, markdown: str) -> Path:
    _MD_DIR.mkdir(parents=True, exist_ok=True)
    published = article.published_at.isoformat() if article.published_at else "—"
    header = (
        f"<!-- url: {article.url} -->\n"
        f"<!-- title: {article.title} -->\n"
        f"<!-- published: {published} -->\n\n"
    )
    path = _MD_DIR / f"{_slug(article.url)}.md"
    path.write_text(header + markdown, encoding="utf-8")
    return path


async def main() -> None:
    args = _parse_args()
    configure_logging()
    settings = get_settings()
    watchlist = load_watchlist(settings.WATCHLIST_PATH)

    feeds = _select_feeds(args, watchlist)
    hours = args.lookback_hours if args.lookback_hours is not None else settings.INGEST_LOOKBACK_HOURS
    since = datetime.now(UTC) - timedelta(hours=hours)
    articles = await fetch_feeds(feeds, since)

    semaphore = asyncio.Semaphore(settings.ARTICLE_FETCH_CONCURRENCY)
    saved: list[Path] = []

    async def enrich(article: RawArticle) -> RawArticle:
        candidate = args.no_filter or bool(keyword_match(article, watchlist))
        if not candidate or article.body is not None:
            return article
        async with semaphore:
            markdown = await fetch_markdown(article.url)
        if not markdown:
            return article
        saved.append(_save_markdown(article, markdown))
        return dataclasses.replace(article, body=markdown)

    enriched = await asyncio.gather(*(enrich(article) for article in articles))

    dump_articles(
        list(enriched),
        watchlist=None if args.no_filter else watchlist,
        as_json=args.json,
        full_text=args.full,
    )
    if saved:
        logger.info("run-fetch-feeds | saved markdown files=%d dir=%s", len(saved), _MD_DIR)


if __name__ == "__main__":
    asyncio.run(main())
