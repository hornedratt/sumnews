from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from sumnews.parsing.telegram import TelegramSource
from sumnews.typed import SourceType
from telethon.sessions import StringSession

NOW = datetime(2025, 1, 10, 12, 0, tzinfo=UTC)
SINCE = NOW - timedelta(hours=24)

# A valid (empty) session string so the client constructs offline without a real login.
EMPTY_SESSION = StringSession().save()


def _msg(msg_id: int, text: str | None, date: datetime) -> SimpleNamespace:
    return SimpleNamespace(id=msg_id, message=text, date=date)


class FakeClient:
    """Stands in for TelegramClient — only the two methods the source calls."""

    def __init__(self, messages: list[Any] | None = None, entity: Any = None) -> None:
        self._messages = messages or []
        self._entity = entity

    def iter_messages(
        self, entity: str, offset_date: datetime | None = None, reverse: bool = False
    ) -> AsyncIterator[Any]:
        async def gen() -> AsyncIterator[Any]:
            for message in self._messages:
                yield message

        return gen()

    async def get_entity(self, name: str) -> Any:
        return self._entity


def _source_with(client: FakeClient) -> TelegramSource:
    src = TelegramSource(1, "hash", EMPTY_SESSION)
    src._client = client  # type: ignore[assignment]  # swap in the fake for the network client
    return src


async def test_fetch_maps_fields_and_builds_url() -> None:
    src = _source_with(FakeClient([_msg(42, "Заголовок\nтекст поста", NOW)]))
    articles = await src.fetch(["cipr_russia"], SINCE)

    assert len(articles) == 1
    article = articles[0]
    assert article.source_type is SourceType.TELEGRAM
    assert article.source_name == "cipr_russia"
    assert article.url == "https://t.me/cipr_russia/42"
    assert article.title == "Заголовок"
    assert article.published_at == NOW


async def test_fetch_skips_media_only_and_empty() -> None:
    src = _source_with(
        FakeClient([_msg(1, None, NOW), _msg(2, "   ", NOW), _msg(3, "real", NOW)])
    )
    articles = await src.fetch(["c"], SINCE)
    assert [a.url for a in articles] == ["https://t.me/c/3"]


async def test_fetch_drops_messages_older_than_since() -> None:
    old = _msg(1, "old", SINCE - timedelta(hours=1))
    fresh = _msg(2, "fresh", NOW)
    src = _source_with(FakeClient([old, fresh]))
    articles = await src.fetch(["c"], SINCE)
    assert [a.title for a in articles] == ["fresh"]


async def test_fetch_respects_per_channel_cap() -> None:
    msgs = [_msg(i, f"post {i}", NOW) for i in range(5)]
    src = TelegramSource(1, "hash", EMPTY_SESSION, per_channel_cap=2)
    src._client = FakeClient(msgs)  # type: ignore[assignment]
    articles = await src.fetch(["c"], SINCE)
    assert len(articles) == 2


async def test_fetch_one_bad_channel_does_not_abort() -> None:
    class HalfBroken(FakeClient):
        def iter_messages(
            self, entity: str, offset_date: datetime | None = None, reverse: bool = False
        ) -> AsyncIterator[Any]:
            if entity == "bad":
                raise RuntimeError("boom")
            return super().iter_messages(entity, offset_date, reverse)

    src = _source_with(HalfBroken([_msg(1, "ok", NOW)]))
    articles = await src.fetch(["bad", "good"], SINCE)
    assert [a.source_name for a in articles] == ["good"]


async def test_resolve_rejects_non_channel() -> None:
    not_a_channel = SimpleNamespace(username="somebot", id=7, title="Bot")
    src = _source_with(FakeClient(entity=not_a_channel))
    with pytest.raises(ValueError, match="not a broadcast channel"):
        await src.resolve_channel("@somebot")
