from datetime import UTC, datetime

from sumnews.parsing import keyword_filter
from sumnews.parsing.types import RawArticle
from sumnews.typed import SourceType
from sumnews.watchlist import Company, Watchlist

WL = Watchlist(
    company=Company(name="Ромашка", domains=("cbr.ru",)),
    competitors=(Company(name="Конкурент А"),),
    keywords=("импортозамещение",),
)


def _article(title: str = "", text: str = "", url: str = "") -> RawArticle:
    return RawArticle(SourceType.RSS, "src", url, title, text, datetime.now(UTC))


def test_matches_term_on_word_boundary_cyrillic() -> None:
    hits = keyword_filter.match(_article(text="Компания Ромашка объявила о планах"), WL)
    assert hits == ["ромашка"]


def test_no_partial_match() -> None:
    # 'ромашковый' must not trigger the term 'ромашка'
    hits = keyword_filter.match(_article(text="ромашковый чай"), WL)
    assert hits == []


def test_matches_keyword_and_competitor() -> None:
    hits = keyword_filter.match(
        _article(title="Курс на импортозамещение", text="Конкурент А отчитался"), WL
    )
    assert hits == ["импортозамещение", "конкурент а"]


def test_matches_domain_in_url() -> None:
    hits = keyword_filter.match(_article(text="без терминов", url="https://cbr.ru/press/123"), WL)
    assert hits == ["cbr.ru"]


def test_empty_when_nothing_matches() -> None:
    assert keyword_filter.match(_article(text="ничего интересного"), WL) == []
