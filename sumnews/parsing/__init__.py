"""News acquisition: RSS + Telegram fetch, keyword prefilter, and the ingest orchestrator.

`types.RawArticle` is the shared shape the `extracting` module consumes; import it here to avoid
a cycle (`ingest`/`manager` pull in `extracting.chain`, which imports `parsing.types`). Reach
`run_ingest` and `IngestManager` via their own modules — `sumnews.parsing.ingest` /
`sumnews.parsing.manager` — not through this package's namespace.
"""

from sumnews.parsing.types import RawArticle

__all__ = ["RawArticle"]
