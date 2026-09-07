"""Shared pretty-printer for `RawArticle` lists — used by the `run_fetch_*` inspection scripts.

Imported as a sibling module (`from _dump import dump_articles`); works because CPython puts the
running script's directory on `sys.path`.

When a `Watchlist` is passed, each article is run through the same `keyword_filter.match` the
ingest pipeline uses, and the matched terms (empty = not a candidate) are shown per article.
"""

import dataclasses
import json
import textwrap

from sumnews.parsing.keyword_filter import match as keyword_match
from sumnews.parsing.types import RawArticle
from sumnews.watchlist import Watchlist


def _as_dict(article: RawArticle, matched: list[str] | None) -> dict[str, object]:
    data = dataclasses.asdict(article)
    data["source_type"] = article.source_type.value
    data["published_at"] = article.published_at.isoformat() if article.published_at else None
    if matched is not None:
        data["matched_terms"] = matched
        data["is_candidate"] = bool(matched)
    return data


def dump_articles(
    articles: list[RawArticle],
    *,
    watchlist: Watchlist | None = None,
    as_json: bool = False,
    full_text: bool = False,
    preview: int = 600,
) -> None:
    """Print the articles as indented JSON or as a readable block each; add keyword-filter results
    when `watchlist` is given."""
    matches: list[list[str] | None] = [
        keyword_match(article, watchlist) if watchlist is not None else None for article in articles
    ]

    if as_json:
        payload = [_as_dict(article, matched) for article, matched in zip(articles, matches, strict=True)]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    for index, (article, matched) in enumerate(zip(articles, matches, strict=True), start=1):
        when = article.published_at.isoformat() if article.published_at else "—"
        raw_body = article.body or ""
        body = raw_body if full_text else textwrap.shorten(raw_body, width=preview, placeholder=" …")
        body_note = f"{len(raw_body)} chars" if article.body is not None else "— (not fetched)"
        print(f"\n[{index}] {article.source_type.value}  source_name={article.source_name!r}")
        print(f"    published_at : {when}")
        print(f"    url          : {article.url}")
        print(f"    title        : {article.title}")
        print(f"    body         : {body_note}")
        if matched is not None:
            print(f"    matched      : {', '.join(matched) if matched else '— (not a candidate)'}")
        for line in body.splitlines():
            print(f"      {line}")

    if watchlist is None:
        print(f"\n{len(articles)} article(s)")
    else:
        candidates = sum(1 for matched in matches if matched)
        print(f"\n{len(articles)} article(s), {candidates} candidate(s) after keyword filter")
