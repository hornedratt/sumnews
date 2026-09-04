"""`RawArticle` — a fetched article before filtering, extraction, or persistence.

Produced by the RSS and Telegram fetchers (Section 3), consumed by `extracting.Extractor` and,
after extraction, mapped to `database.schemas.NewsItemCreate`.
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
    text: str
    published_at: datetime.datetime | None
