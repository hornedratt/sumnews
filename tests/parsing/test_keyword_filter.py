from datetime import UTC, datetime

from sumnews.parsing import keyword_filter
from sumnews.parsing.types import RawArticle
from sumnews.typed import SourceType
from sumnews.watchlist import Company, Watchlist

WL = Watchlist(
    company=Company(name="Ромашка", domains=("cbr.ru",)),
    competitors=(Company(name="Конкурент А"),),
    keywords=("импортозамещение", "штраф"),
)


def _article(title: str = "", url: str = "", body: str | None = None) -> RawArticle:
    return RawArticle(SourceType.RSS, "src", url, title, datetime.now(UTC), body)


def test_matches_exact_term_in_title() -> None:
    hits = keyword_filter.match(_article(title="Компания Ромашка объявила о планах"), WL)
    assert hits == ["ромашка"]


def test_w_star_catches_inflections_only_when_the_term_is_the_stem() -> None:
    # 'штраф' is a bare stem — \w* catches every case/derivation.
    assert keyword_filter.match(_article(title="Суд назначил штрафы"), WL) == ["штраф"]
    assert keyword_filter.match(_article(title="Штрафной удар"), WL) == ["штраф"]
    # 'Ромашка' ends in a vowel — every inflected form changes that vowel, so \w* can't help;
    # only the exact nominative matches. (Would need real stemming / a lemmatizer.)
    assert keyword_filter.match(_article(title="Помощь Ромашке одобрена"), WL) == []
    assert keyword_filter.match(_article(title="Иск против Ромашки"), WL) == []


def test_no_prefix_match() -> None:
    assert keyword_filter.match(_article(title="слово нарОмашка внутри"), WL) == []


def test_matches_keyword_and_competitor_in_title() -> None:
    hits = keyword_filter.match(
        _article(title="Конкурент А объявил курс на импортозамещение"), WL
    )
    assert hits == ["импортозамещение", "конкурент а"]


def test_matches_domain_in_url() -> None:
    hits = keyword_filter.match(_article(title="Без терминов", url="https://cbr.ru/press/123"), WL)
    assert hits == ["cbr.ru"]


def test_empty_when_title_has_nothing() -> None:
    assert keyword_filter.match(_article(title="Ничего интересного сегодня"), WL) == []


def test_matches_term_in_body_when_title_is_bare() -> None:
    # Telegram posts get their body here — a term only in the body still makes a candidate.
    hits = keyword_filter.match(
        _article(title="Первая строка без терминов", body="А ниже речь про штрафы и Ромашка"), WL
    )
    assert hits == ["ромашка", "штраф"]
