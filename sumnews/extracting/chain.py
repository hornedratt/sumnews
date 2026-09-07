"""The extraction chain and the `Extractor` the ingest pipeline calls.

`build_chain` wires ``prompt | llm.with_structured_output(Extraction)`` against the configured
OpenAI-compatible endpoint. `Extractor` adds the per-article concerns: input truncation, one retry,
and a logged fallback so a single failed call never sinks an ingest run.
"""

from typing import Any, cast

from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI

from sumnews.extracting.prompt import build_prompt
from sumnews.extracting.schema import Extraction
from sumnews.loggers import logger
from sumnews.parsing.types import RawArticle
from sumnews.settings import Settings
from sumnews.typed import Category, Priority
from sumnews.watchlist import Watchlist

_TRUNCATION_NOTE = "\n\n[... текст статьи усечён по длине ...]"


def build_chain(
    settings: Settings, watchlist: Watchlist
) -> Runnable[dict[str, Any], Extraction]:
    llm = ChatOpenAI(
        base_url=settings.LLM_URL,
        api_key=settings.LLM_API_KEY,
        model=settings.LLM_MODEL,
        temperature=0,
        timeout=settings.LLM_TIMEOUT_SECONDS,
        max_retries=0,
        max_tokens=settings.LLM_MAX_OUTPUT_TOKENS,
    )
    # method="function_calling": the default (strict json_schema response_format) comes back with
    # a null `choices` list against some OpenAI-compatible routers (observed on routerai.ru/Qwen).
    structured = llm.with_structured_output(schema=Extraction, method="function_calling")
    chain = build_prompt(watchlist) | structured
    return cast("Runnable[dict[str, Any], Extraction]", chain)


def _fallback(reason: str) -> Extraction:
    return Extraction(
        is_relevant=True,
        relevance_reason=reason,
        summary="",
        category=Category.TRENDS,
        priority=Priority.LOW,
        priority_reason=reason,
    )


class Extractor:
    def __init__(self, settings: Settings, watchlist: Watchlist) -> None:
        self._chain = build_chain(settings, watchlist)
        self._max_input_chars = settings.LLM_MAX_INPUT_CHARS

    async def extract(self, article: RawArticle) -> Extraction:
        """Run the chain for one article. Never raises — returns a fallback `Extraction` on failure."""
        payload: dict[str, Any] = {
            "source_name": article.source_name,
            "source_type": article.source_type.value,
            "url": article.url,
            "published_at": article.published_at.isoformat() if article.published_at else "неизвестно",
            "title": article.title,
            "body": self._body(article.text),
        }

        for attempt in (1, 2):
            try:
                result = await self._chain.ainvoke(payload)
            except Exception as error:  # the LLM endpoint is an external boundary
                logger.warning("extract | attempt=%d url=%s error=%r", attempt, article.url, error)
                continue
            return result

        logger.error("extract | fallback url=%s", article.url)
        fallback = _fallback("сбой извлечения; оставлено для ручной проверки")
        return fallback

    def _body(self, text: str) -> str:
        if len(text) <= self._max_input_chars:
            return text
        clipped = text[: self._max_input_chars].rstrip()
        return clipped + _TRUNCATION_NOTE
