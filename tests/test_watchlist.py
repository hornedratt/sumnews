"""Watchlist parsing + the derived term/domain sets the keyword prefilter depends on."""

from pathlib import Path

from sumnews.watchlist import load_watchlist


def test_example_watchlist_loads_and_derives_terms() -> None:
    watchlist = load_watchlist(Path("watchlist.example.yaml"))

    assert watchlist.company.name == "Acme Corp"
    assert {company.name for company in watchlist.competitors} == {"Globex", "Initech"}

    # Company names + aliases + keywords + tags, all lowercased.
    assert "acme corp" in watchlist.all_terms
    assert "globex inc" in watchlist.all_terms
    assert "тендер" in watchlist.all_terms
    assert "fintech" in watchlist.all_terms

    assert watchlist.all_domains == {"acme.example", "globex.example", "initech.example"}


def test_all_companies_puts_subject_first() -> None:
    watchlist = load_watchlist(Path("watchlist.example.yaml"))

    assert watchlist.all_companies[0].name == "Acme Corp"
    assert len(watchlist.all_companies) == 3
