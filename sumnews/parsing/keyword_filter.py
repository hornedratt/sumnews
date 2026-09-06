"""Cheap pre-LLM relevance gate: does an article mention anything on the watchlist?

`match` runs before the extraction chain so a plainly irrelevant article never costs an LLM call.
"""

import re

from sumnews.parsing.types import RawArticle
from sumnews.watchlist import Watchlist


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def match(article: RawArticle, watchlist: Watchlist) -> list[str]:
    """Return sorted matched terms/domains. Empty list = not a candidate.

    Terms are matched on word boundaries (Unicode-aware, so Cyrillic works) against the title
    only — `RawArticle` carries no body at this stage. Domains are matched as substrings against
    the title and the source URL.
    """
    haystack = _normalize(article.title)
    url = article.url.lower()
    hits: set[str] = set()

    for term in watchlist.all_terms:
        if re.search(rf"\b{re.escape(term)}\w*", haystack):
            hits.add(term)

    for domain in watchlist.all_domains:
        if domain in haystack or domain in url:
            hits.add(domain)

    return sorted(hits)
