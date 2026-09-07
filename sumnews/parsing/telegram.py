"""Telegram fetching: `TelegramSource` wraps one Telethon user-client.

Requires a user session (not a bot token) — the Bot API cannot read arbitrary public channel
history. Get the session string via `scripts/tg_login.py`.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from telethon import TelegramClient
from telethon.errors import (
    ChannelPrivateError,
    FloodWaitError,
    UsernameInvalidError,
    UsernameNotOccupiedError,
)
from telethon.sessions import StringSession
from telethon.tl.types import Channel

from sumnews.loggers import logger
from sumnews.parsing.types import RawArticle
from sumnews.typed import SourceType

_TITLE_MAX = 120


def normalize_channel(raw: str) -> str:
    """'@cipr' / 'https://t.me/cipr' / 't.me/s/cipr' -> 'cipr'.

    This is the canonical channel identity: `fetch` stores it as `RawArticle.source_name`, so
    `run_ingest` must key its per-source cursor by the same value.
    """
    channel = raw.strip()
    for prefix in ("https://", "http://"):
        if channel.startswith(prefix):
            channel = channel[len(prefix) :]
    channel = channel.removeprefix("www.").removeprefix("t.me/").removeprefix("s/")
    channel = channel.lstrip("@")
    return channel.split("/", 1)[0].split("?", 1)[0]


def _title_from_text(text: str) -> str:
    """Telegram posts have no title — use the first non-empty line, truncated."""
    first = next((line.strip() for line in text.splitlines() if line.strip()), "")
    if len(first) <= _TITLE_MAX:
        return first
    return first[:_TITLE_MAX].rsplit(" ", 1)[0] + "…"


@dataclass(slots=True)
class ResolvedChannel:
    """Result of validating a user-entered channel before it's saved as a source."""

    username: str  # bare username — what you store and pass to fetch()
    channel_id: int
    title: str  # human-readable name, for display in the UI


class TelegramSource:
    """Wraps one Telethon user-client. Built once, reused by the scheduler job and scripts."""

    def __init__(
        self,
        api_id: int | str,
        api_hash: str,
        session: str,
        *,
        per_channel_cap: int = 200,
        flood_threshold: int = 60,
    ) -> None:
        self._client = TelegramClient(
            StringSession(session),
            int(api_id),
            api_hash,
            flood_sleep_threshold=flood_threshold,  # auto-sleep on short flood waits
        )
        self._per_channel_cap = per_channel_cap

    async def connect(self) -> None:
        await self._client.connect()
        if not await self._client.is_user_authorized():
            raise RuntimeError(
                "telegram | not authorized — run scripts/tg_login.py and set TELEGRAM_SESSION"
            )
        me = await self._client.get_me()
        logger.info("telegram | connected as=%s", getattr(me, "username", None) or me.id)

    async def disconnect(self) -> None:
        await self._client.disconnect()

    async def resolve_channel(self, raw: str) -> ResolvedChannel:
        """Validate a user-entered channel (username / t.me link) before saving it.

        Raises ValueError with a readable reason if the channel doesn't exist, is
        private/inaccessible, or isn't a channel. On success returns the bare username
        (store this), the numeric id and the display title (show this in the UI).
        """
        name = normalize_channel(raw)
        try:
            entity = await self._client.get_entity(name)
        except (UsernameNotOccupiedError, UsernameInvalidError, ValueError) as error:
            raise ValueError(f"channel not found: {raw!r}") from error
        except ChannelPrivateError as error:
            raise ValueError(f"channel is private or not accessible: {raw!r}") from error

        if not isinstance(entity, Channel) or entity.broadcast is False:
            # a Channel with broadcast=True is a real channel; chats/users/bots are not
            raise ValueError(f"{raw!r} is not a broadcast channel ({type(entity).__name__})")

        resolved = ResolvedChannel(
            username=entity.username or name,
            channel_id=entity.id,
            title=entity.title,
        )
        logger.info(
            "telegram | resolved input=%r username=%s id=%s title=%s",
            raw, resolved.username, resolved.channel_id, resolved.title,
        )
        return resolved

    async def fetch(self, channels: Iterable[str], since: datetime) -> list[RawArticle]:
        """Fetch posts newer than `since` from each channel. One bad channel never aborts."""
        channels = list(channels)
        out: list[RawArticle] = []
        for raw in channels:
            name = normalize_channel(raw)
            try:
                out.extend(await self._fetch_channel(name, since))
            except FloodWaitError as error:
                logger.warning(
                    "telegram | flood_wait channel=%s seconds=%s (skipped)", name, error.seconds
                )
            except Exception as error:  # a single channel is an external boundary; isolate it
                logger.warning("telegram | fetch_failed channel=%s error=%r", name, error)
        logger.info("telegram | fetched articles=%d channels=%d", len(out), len(channels))
        return out

    async def _fetch_channel(self, name: str, since: datetime) -> list[RawArticle]:
        articles: list[RawArticle] = []
        count = 0
        # reverse=True -> oldest→newest; with offset_date it returns posts *after* `since`.
        async for msg in self._client.iter_messages(name, offset_date=since, reverse=True):
            if msg.date is not None and msg.date < since:  # belt-and-suspenders vs boundary edges
                continue
            text = (msg.message or "").strip()
            if not text:  # media-only or service message
                continue
            articles.append(
                RawArticle(
                    source_type=SourceType.TELEGRAM,
                    source_name=name,
                    url=f"https://t.me/{name}/{msg.id}",
                    title=_title_from_text(text),
                    published_at=msg.date,
                    body=text,
                )
            )
            count += 1
            if count >= self._per_channel_cap:
                logger.warning("telegram | cap_hit channel=%s cap=%d", name, self._per_channel_cap)
                break
        logger.info("telegram | channel=%s new=%d since=%s", name, count, since.isoformat())
        return articles
