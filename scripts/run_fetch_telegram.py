"""Fetch Telegram channels and print the `RawArticle` objects — inspect what ingest actually sees.

    make run-fetch-telegram ARGS='--lookback-hours 72'
    make run-fetch-telegram ARGS='cipr_russia @arpp_russia --full'
    make run-fetch-telegram ARGS='--json'
    make run-fetch-telegram ARGS='--no-filter'

Needs TELEGRAM_* in .env (run scripts/tg_login.py first). With no channel args, uses
watchlist.yaml's telegram_channels. Runs `keyword_filter.match` against the watchlist per post.
No DB, no LLM.
"""

import argparse
import asyncio
from datetime import UTC, datetime, timedelta

from _dump import dump_articles
from sumnews.loggers import configure_logging
from sumnews.parsing.telegram import TelegramSource
from sumnews.settings import get_settings
from sumnews.watchlist import load_watchlist


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("channels", nargs="*", help="usernames / t.me links (default: watchlist)")
    parser.add_argument("--lookback-hours", type=int, default=None, help="window (default: from .env)")
    parser.add_argument("--full", action="store_true", help="print full post text, not a preview")
    parser.add_argument("--no-filter", action="store_true", help="skip the keyword filter")
    parser.add_argument("--json", action="store_true", help="dump as JSON")
    return parser.parse_args()


async def main() -> None:
    args = _parse_args()
    configure_logging()
    settings = get_settings()
    settings.require_telegram()
    watchlist = load_watchlist(settings.WATCHLIST_PATH)

    channels = args.channels or list(watchlist.telegram_channels)
    if not channels:
        raise SystemExit("no channels given and watchlist.telegram_channels is empty")

    hours = args.lookback_hours if args.lookback_hours is not None else settings.INGEST_LOOKBACK_HOURS
    since = datetime.now(UTC) - timedelta(hours=hours)

    source = TelegramSource(
        settings.TELEGRAM_API_ID, settings.TELEGRAM_API_HASH, settings.TELEGRAM_SESSION
    )
    await source.connect()
    try:
        articles = await source.fetch(channels, since)
    finally:
        await source.disconnect()

    dump_articles(
        articles,
        watchlist=None if args.no_filter else watchlist,
        as_json=args.json,
        full_text=args.full,
    )


if __name__ == "__main__":
    asyncio.run(main())
