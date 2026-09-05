"""Validate a Telegram channel before adding it as a source.

    make tg-resolve ARGS='@cipr_russia'
    make tg-resolve ARGS='https://t.me/arpp_russia'

Prints the bare username (store this), numeric id and display title, or a clear
reason why it can't be used. Reads TELEGRAM_* from .env.
"""

import asyncio
import sys

from sumnews.loggers import configure_logging
from sumnews.parsing.telegram import TelegramSource
from sumnews.settings import get_settings


async def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("usage: tg_resolve.py <@username | t.me link>")
    raw = sys.argv[1]

    configure_logging()

    settings = get_settings()
    settings.require_telegram()
    src = TelegramSource(settings.TELEGRAM_API_ID, settings.TELEGRAM_API_HASH, settings.TELEGRAM_SESSION)
    await src.connect()
    try:
        resolved = await src.resolve_channel(raw)
    except ValueError as error:
        print(f"\nREJECTED: {error}")
        return
    finally:
        await src.disconnect()

    print("\nOK — source can be added:")
    print(f"  store username : {resolved.username}")
    print(f"  channel id     : {resolved.channel_id}")
    print(f"  display title  : {resolved.title}")


if __name__ == "__main__":
    asyncio.run(main())
