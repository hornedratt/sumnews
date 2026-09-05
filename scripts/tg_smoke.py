"""Quick standalone check that Telegram fetching works.

    make tg-smoke ARGS='cipr_russia --hours 72'

Reads TELEGRAM_* from .env. Run scripts/tg_login.py first to get TELEGRAM_SESSION.
"""

import argparse
import asyncio
from datetime import UTC, datetime, timedelta

from sumnews.loggers import configure_logging
from sumnews.parsing.telegram import TelegramSource
from sumnews.settings import get_settings


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("channels", nargs="+", help="channel usernames or t.me links")
    parser.add_argument(
        "--hours", type=int, default=None, help="lookback window (default: from .env)"
    )
    return parser.parse_args()


async def main() -> None:
    args = _parse_args()
    configure_logging()

    settings = get_settings()
    settings.require_telegram()
    hours = args.hours if args.hours is not None else settings.INGEST_LOOKBACK_HOURS
    since = datetime.now(UTC) - timedelta(hours=hours)

    src = TelegramSource(settings.TELEGRAM_API_ID, settings.TELEGRAM_API_HASH, settings.TELEGRAM_SESSION)
    await src.connect()
    try:
        articles = await src.fetch(args.channels, since)
    finally:
        await src.disconnect()

    print(f"\n=== {len(articles)} articles since {since.isoformat()} ===\n")
    for article in articles[:20]:
        when = article.published_at.isoformat() if article.published_at else "?"
        print(f"[{when}] {article.source_name} - {article.title}")
        print(f"    {article.url}")


if __name__ == "__main__":
    asyncio.run(main())
