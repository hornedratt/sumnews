"""`RawArticle` — a fetched article before filtering, extraction, or persistence.

Produced by the RSS and Telegram fetchers, consumed by `extracting.Extractor` and, after
extraction, mapped to `database.schemas.NewsItemCreate`.

`body` holds text the fetcher already has (a Telegram post, or an RSS `<description>` when the
feed ships one). When it is ``None`` the ingest pipeline fetches the article page and converts it
to Markdown for candidates only — see `parsing.article.fetch_markdown`.
"""

import dataclasses
import datetime

from sumnews.typed import SourceType


@dataclasses.dataclass(frozen=True, slots=True)
class RawArticle:
    source_type: SourceType
    source_name: str
    url: str
    title: str
    published_at: datetime.datetime | None
    body: str | None = None
