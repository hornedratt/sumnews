"""News acquisition: RSS + Telegram fetch, keyword prefilter, and the ingest orchestrator.

Only `types.RawArticle` exists so far — it is the shared shape the `extracting` module consumes.
The fetchers and `ingest` land in Section 3.
"""

from sumnews.parsing.types import RawArticle

__all__ = ["RawArticle"]
