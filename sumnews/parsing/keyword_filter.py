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

    Terms match as a word-start prefix (Unicode-aware, so Cyrillic works) — no boundary is
    required at the end, since Russian noun/verb endings inflect (a "грант" keyword must still
    match "грантов", "телеком" must still match "телекоммуникационная"). Domains are matched as
    substrings against the text and the source URL.
    """
    haystack = _normalize(f"{article.title} {article.text}")
    url = article.url.lower()
    hits: set[str] = set()

    for term in watchlist.all_terms:
        if re.search(rf"\b{re.escape(term)}", haystack):
            hits.add(term)

    for domain in watchlist.all_domains:
        if domain in haystack or domain in url:
            hits.add(domain)

    return sorted(hits)
