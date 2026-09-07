"""HTTP routes for the review UI.

All routes are unauthenticated (v1 is an internal tool — see the plan's open questions).
Templates are resolved from ``sumnews/web/templates``; the feed and detail pages render
server-side, edits post back as a form, and an ``HX-Request`` edit gets the row partial instead
of a redirect.
"""

import math
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import text

from sumnews.database.schemas import NewsFilter
from sumnews.loggers import logger
from sumnews.parsing.telegram import normalize_channel
from sumnews.typed import Category, NewsSort, Priority
from sumnews.web.deps import RepoDep, SchedulerDep, SessionDep, WatchlistDep

PAGE_SIZE = 25
INGEST_JOB_ID = "ingest"

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
router = APIRouter()


def _sources(watchlist: WatchlistDep) -> list[str]:
    """Source names offered in the filter dropdown — feed names plus normalized channel names."""
    feed_names = [feed.name for feed in watchlist.rss_feeds]
    channel_names = [normalize_channel(raw) for raw in watchlist.telegram_channels]
    return sorted({*feed_names, *channel_names})


@router.get("/", response_class=HTMLResponse)
async def feed(
    request: Request,
    repo: RepoDep,
    watchlist: WatchlistDep,
    category: str | None = None,
    priority: str | None = None,
    source: str | None = None,
    q: str | None = None,
    sort: NewsSort = NewsSort.NEWEST,
    page: int = 1,
) -> Response:
    """The review feed: one filtered, sorted, paginated page of items plus filter-bar state."""
    page = max(page, 1)
    parsed_category = _parse_category(category)
    parsed_priority = _parse_priority(priority)
    filters = NewsFilter(
        category=parsed_category, priority=parsed_priority, source_name=source, query=q or None
    )
    items, total = await repo.list(
        filters, sort, limit=PAGE_SIZE, offset=(page - 1) * PAGE_SIZE
    )
    page_count = max(1, math.ceil(total / PAGE_SIZE))
    category_counts = await repo.category_counts()
    priority_counts = await repo.priority_counts()

    context = {
        "items": items,
        "total": total,
        "page": page,
        "page_count": page_count,
        "sort": sort,
        "active": {"category": parsed_category, "priority": parsed_priority, "source": source, "q": q or ""},
        "sources": _sources(watchlist),
        "categories": list(Category),
        "priorities": list(Priority),
        "category_counts": category_counts,
        "priority_counts": priority_counts,
    }
    return templates.TemplateResponse(request, "feed.html", context)


@router.get("/items/{item_id}", response_class=HTMLResponse)
async def item_detail(request: Request, repo: RepoDep, item_id: uuid.UUID) -> Response:
    news_item = await repo.get(item_id)
    if news_item is None:
        raise HTTPException(status_code=404, detail="news item not found")
    context = {
        "item": news_item,
        "categories": list(Category),
        "priorities": list(Priority),
    }
    return templates.TemplateResponse(request, "item.html", context)


def _parse_category(value: str | None) -> Category | None:
    if not value:
        return None
    try:
        return Category(value)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=f"bad category: {value!r}") from error


def _parse_priority(value: str | None) -> Priority | None:
    if not value:
        return None
    try:
        return Priority(value)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=f"bad priority: {value!r}") from error


@router.post("/items/{item_id}")
async def item_update(
    request: Request,
    repo: RepoDep,
    item_id: uuid.UUID,
    summary: Annotated[str | None, Form()] = None,
    category: Annotated[str | None, Form()] = None,
    priority: Annotated[str | None, Form()] = None,
    user_notes: Annotated[str | None, Form()] = None,
) -> Response:
    """Apply the submitted edits (`update_fields` ignores unset fields, flags `user_edited`)."""
    try:
        news_item = await repo.update_fields(
            item_id,
            summary=summary,
            category=_parse_category(category),
            priority=_parse_priority(priority),
            user_notes=user_notes,
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail="news item not found") from error

    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(request, "partials/news_row.html", {"item": news_item})
    return RedirectResponse(url=f"/items/{item_id}", status_code=303)


@router.post("/ingest/run")
async def ingest_run(request: Request, scheduler: SchedulerDep) -> Response:
    """Nudge the interval job to fire now. `max_instances=1` on the job prevents an overlap."""
    job = scheduler.get_job(INGEST_JOB_ID)
    if job is not None:
        job.modify(next_run_time=datetime.now(UTC))
        logger.info("web | ingest_run triggered job=%s", INGEST_JOB_ID)
    return RedirectResponse(url=request.headers.get("referer") or "/", status_code=303)


@router.get("/healthz")
async def healthz(session: SessionDep, scheduler: SchedulerDep) -> JSONResponse:
    db_ok = False
    try:
        await session.execute(text("SELECT 1"))
        db_ok = True
    except Exception as error:  # health probe: report the failure, don't raise
        logger.warning("web | healthz db_check failed error=%r", error)
    scheduler_ok = scheduler.running
    payload = {"db": db_ok, "scheduler": scheduler_ok}
    return JSONResponse(payload, status_code=200 if db_ok and scheduler_ok else 503)
