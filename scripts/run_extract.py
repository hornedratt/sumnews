"""Run the extraction chain against one article and print the result.

    make run-extract ARGS='--text "Регулятор оштрафовал Acme Corp на 5 млн..."'
    make run-extract ARGS='--file article.md'
    make run-extract ARGS='--url https://lenta.ru/news/2026/09/06/...'

`--url` fetches + renders to Markdown via `parsing.article.fetch_markdown` (same as ingest).
"""

import argparse
import asyncio
import datetime
from pathlib import Path

from sumnews.extracting.chain import Extractor
from sumnews.loggers import configure_logging
from sumnews.parsing.article import fetch_markdown
from sumnews.parsing.types import RawArticle
from sumnews.settings import get_settings
from sumnews.typed import SourceType
from sumnews.watchlist import load_watchlist


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract summary/category/priority for one article")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--text", help="article body as a literal string")
    source.add_argument("--file", help="path to a file holding the article body")
    source.add_argument("--url", help="URL to fetch and render to Markdown")
    parser.add_argument("--title", default=None, help="article title (defaults to a stub)")
    return parser.parse_args()


async def _load(args: argparse.Namespace) -> tuple[RawArticle, str]:
    if args.text is not None:
        body, url = args.text, "manual://input"
    elif args.file is not None:
        body, url = Path(args.file).read_text(encoding="utf-8"), f"file://{args.file}"
    else:
        fetched = await fetch_markdown(args.url)
        if fetched is None:
            raise SystemExit(f"could not fetch/extract {args.url}")
        body, url = fetched, args.url

    article = RawArticle(
        source_type=SourceType.RSS,
        source_name="run_extract",
        url=url,
        title=args.title or f"{body[:80]}...",
        published_at=datetime.datetime.now(datetime.UTC),
    )
    return article, body


async def main() -> None:
    configure_logging()
    settings = get_settings()
    watchlist = load_watchlist(settings.WATCHLIST_PATH)
    article, body = await _load(_parse_args())

    extractor = Extractor(settings, watchlist)
    extraction = await extractor.extract(article, body)
    print(extraction.model_dump_json(indent=2))


if __name__ == "__main__":
    asyncio.run(main())
