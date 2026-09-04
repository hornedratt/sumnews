"""`Extractor` retry / fallback / truncation — exercised without a live LLM by stubbing the chain."""

import datetime
from pathlib import Path

import pytest
from sumnews.extracting.chain import Extractor
from sumnews.extracting.schema import Extraction
from sumnews.parsing.types import RawArticle
from sumnews.settings import Settings
from sumnews.typed import Category, Priority, SourceType
from sumnews.watchlist import load_watchlist


class _ScriptedChain:
    """Yields queued outcomes in order; an Exception instance is raised, anything else returned."""

    def __init__(self, *outcomes: object) -> None:
        self._outcomes = list(outcomes)
        self.calls = 0

    async def ainvoke(self, _payload: dict[str, object]) -> object:
        outcome = self._outcomes[self.calls]
        self.calls += 1
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@pytest.fixture
def article() -> RawArticle:
    return RawArticle(
        source_type=SourceType.RSS,
        source_name="test",
        url="https://example.test/1",
        title="Регулятор оштрафовал Acme",
        text="Регулятор оштрафовал Acme Corp на 5 млн.",
        published_at=datetime.datetime(2026, 9, 1, tzinfo=datetime.UTC),
    )


@pytest.fixture
def extractor() -> Extractor:
    watchlist = load_watchlist(Path("watchlist.example.yaml"))
    return Extractor(Settings(), watchlist)


def _extraction() -> Extraction:
    return Extraction(
        is_relevant=True,
        relevance_reason="про Acme",
        summary="Регулятор оштрафовал Acme Corp на 5 млн.",
        category=Category.REGULATION,
        priority=Priority.HIGH,
        priority_reason="действие регулятора",
    )


async def test_returns_result_on_first_success(extractor: Extractor, article: RawArticle) -> None:
    wanted = _extraction()
    extractor._chain = _ScriptedChain(wanted)  # type: ignore[assignment]

    result = await extractor.extract(article)

    assert result is wanted
    assert extractor._chain.calls == 1  # type: ignore[attr-defined]


async def test_retries_once_then_succeeds(extractor: Extractor, article: RawArticle) -> None:
    wanted = _extraction()
    extractor._chain = _ScriptedChain(RuntimeError("boom"), wanted)  # type: ignore[assignment]

    result = await extractor.extract(article)

    assert result is wanted
    assert extractor._chain.calls == 2  # type: ignore[attr-defined]


async def test_falls_back_after_two_failures(extractor: Extractor, article: RawArticle) -> None:
    extractor._chain = _ScriptedChain(  # type: ignore[assignment]
        RuntimeError("boom"), TimeoutError("slow")
    )

    result = await extractor.extract(article)

    assert result.is_relevant is True
    assert result.summary == ""
    assert result.category is Category.TRENDS
    assert result.priority is Priority.LOW
    assert extractor._chain.calls == 2  # type: ignore[attr-defined]


def test_body_truncates_long_text_with_note(extractor: Extractor) -> None:
    extractor._max_input_chars = 20

    body = extractor._body("а" * 200)

    assert body.startswith("а" * 20)
    assert body.endswith("усечён по длине ...]")
    assert "а" * 21 not in body
