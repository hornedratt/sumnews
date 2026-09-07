"""Fetch an article URL and return its main content as Markdown.

Used by the ingest pipeline for candidates whose `RawArticle.body` is ``None`` (i.e. RSS items —
most news feeds ship only a headline + link). `trafilatura` does the download, boilerplate
removal, and Markdown rendering; both calls are sync, so they run in a worker thread.
"""

import asyncio

import trafilatura

from sumnews.loggers import logger


def _extract(url: str) -> str | None:
    html = trafilatura.fetch_url(url)
    if html is None:
        logger.warning("article | download_failed url=%s", url)
        return None
    markdown = trafilatura.extract(
        html, output_format="markdown", include_links=True, with_metadata=False
    )
    if not markdown:
        logger.warning("article | no_content url=%s", url)
        return None
    return markdown


async def fetch_markdown(url: str) -> str | None:
    """Return the article's main text as Markdown, or ``None`` if it can't be fetched/extracted.

    Never raises — a failed fetch is logged and returns ``None`` so one bad URL can't sink an
    ingest pass.
    """
    try:
        markdown = await asyncio.to_thread(_extract, url)
    except Exception as error:  # trafilatura / network is an external boundary
        logger.warning("article | fetch_failed url=%s error=%r", url, error)
        return None
    return markdown
