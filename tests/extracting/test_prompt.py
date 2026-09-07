"""`build_prompt` bakes the watchlist into the template and leaves the per-article slots open."""

from pathlib import Path

from sumnews.extracting.prompt import build_prompt
from sumnews.watchlist import load_watchlist


def test_prompt_renders_company_aliases_and_competitors() -> None:
    watchlist = load_watchlist(Path("watchlist.example.yaml"))
    messages = build_prompt(watchlist).format_messages(
        source_name="Regulator news",
        source_type="rss",
        url="https://example.test/1",
        published_at="2026-09-01",
        title="Заголовок",
        body="Тело статьи.",
    )

    system = messages[0].content
    assert "Acme Corp" in system
    assert "Acme" in system and "ACME" in system  # aliases
    assert "Globex" in system and "Initech" in system  # competitors

    human = messages[1].content
    assert "Тело статьи." in human
    assert "https://example.test/1" in human


def test_prompt_without_competitors_says_none() -> None:
    watchlist = load_watchlist(Path("watchlist.example.yaml")).model_copy(update={"competitors": ()})
    system = build_prompt(watchlist).format_messages(
        source_name="s", source_type="rss", url="u", published_at="p", title="t", body="b"
    )[0].content
    assert "не заданы" in system
