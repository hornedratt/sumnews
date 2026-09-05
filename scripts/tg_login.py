"""One-time interactive Telethon login -> prints a StringSession for TELEGRAM_SESSION.

    make tg-login

Get api_id / api_hash from https://my.telegram.org -> "API development tools".
Put them in .env as TELEGRAM_API_ID / TELEGRAM_API_HASH (or paste when prompted). You'll
be asked for your phone number, the login code, and your 2FA password if you have one.
Copy the printed TELEGRAM_SESSION=... line into .env — treat it like a password.
"""

import asyncio

from sumnews.settings import get_settings
from telethon import TelegramClient
from telethon.sessions import StringSession


async def main() -> None:
    settings = get_settings()  # reads .env if present
    api_id = settings.TELEGRAM_API_ID or int(input("api_id: ").strip())
    api_hash = settings.TELEGRAM_API_HASH or input("api_hash: ").strip()

    # `async with` triggers Telethon's interactive login (phone / code / 2FA).
    async with TelegramClient(StringSession(), api_id, api_hash) as client:
        session = client.session.save()
        me = await client.get_me()
        print("\nLogged in as:", getattr(me, "username", None) or me.id)
        print("\nAdd this to your .env (keep it secret):\n")
        print(f"TELEGRAM_SESSION={session}")


if __name__ == "__main__":
    asyncio.run(main())
