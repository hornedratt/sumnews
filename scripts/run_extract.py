"""Run the extraction chain against one article and print the result.

    make run-extract ARGS='--text "Регулятор оштрафовал Acme Corp на 5 млн..."'
    make run-extract ARGS='--file article.txt'
    make run-extract ARGS='--url https://example.com/news/123'

`--url` does a plain GET and strips tags — good enough to exercise the chain, not a real parser
(that is Section 3).
"""

import argparse
import asyncio
import datetime
import re
from pathlib import Path

import httpx

from sumnews.extracting.chain import Extractor
from sumnews.loggers import configure_logging
from sumnews.parsing.types import RawArticle
from sumnews.settings import get_settings
from sumnews.typed import SourceType
from sumnews.watchlist import load_watchlist

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\n\s*\n\s*\n+")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract summary/category/priority for one article")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--text", help="article body as a literal string")
    source.add_argument("--file", help="path to a file holding the article body")
    source.add_argument("--url", help="URL to GET and strip to text")
    parser.add_argument("--title", default=None, help="article title (defaults to a stub)")
    args = parser.parse_args()
    return args


def _load_article(args: argparse.Namespace) -> RawArticle:
    if args.text is not None:
        text, url = args.text, "manual://input"
    elif args.file is not None:
        text, url = Path(args.file).read_text(encoding="utf-8"), f"file://{args.file}"
    else:
        response = httpx.get(args.url, timeout=20.0, follow_redirects=True)
        response.raise_for_status()
        text = _WS.sub("\n\n", _TAG.sub("", response.text)).strip()
        url = args.url

    title = args.title or f"{text[:80]}..."
    return RawArticle(
        source_type=SourceType.RSS,
        source_name="run_extract",
        url=url,
        title=title,
        text=text,
        published_at=datetime.datetime.now(datetime.UTC),
    )


async def main() -> None:
    configure_logging()
    settings = get_settings()
    watchlist = load_watchlist(settings.WATCHLIST_PATH)
    article = _load_article(_parse_args())

    extractor = Extractor(settings, watchlist)
    extraction = await extractor.extract(article)
    print(extraction.model_dump_json(indent=2))


if __name__ == "__main__":
    asyncio.run(main())
