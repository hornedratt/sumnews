"""Run one ingest pass: fetch RSS + Telegram, keyword-filter, extract, store.

    make run-ingest ARGS='--lookback-hours 168'
    make run-ingest ARGS='--no-llm'

Reads config from .env + watchlist.yaml. `--no-llm` marks stored items llm_verified=False.
Periodic scheduling lives in the FastAPI app (Section 5); here we always run once.
"""

import argparse
import asyncio
import dataclasses

from sumnews.database.engine import dispose_engine, session_scope
from sumnews.loggers import configure_logging
from sumnews.parsing.ingest import run_ingest
from sumnews.parsing.manager import IngestManager
from sumnews.settings import get_settings
from sumnews.watchlist import load_watchlist


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--no-llm", action="store_true", help="trust keyword relevance; llm_verified=False"
    )
    parser.add_argument(
        "--lookback-hours", type=int, default=None, help="override the ingest window"
    )
    return parser.parse_args()


async def main() -> None:
    args = _parse_args()
    configure_logging()

    settings = get_settings()
    watchlist = load_watchlist(settings.WATCHLIST_PATH)

    async with session_scope() as session:
        manager = IngestManager.build(
            settings,
            watchlist,
            session,
            llm_verify_enabled=False if args.no_llm else None,
            lookback_hours=args.lookback_hours,
        )

        telegram = manager.telegram
        if telegram is not None:
            await telegram.connect()
        try:
            stats = await run_ingest(manager)
        finally:
            if telegram is not None:
                await telegram.disconnect()

    await dispose_engine()

    print("\n=== ingest stats ===")
    for field, value in dataclasses.asdict(stats).items():
        print(f"  {field:<16} {value}")


if __name__ == "__main__":
    asyncio.run(main())
