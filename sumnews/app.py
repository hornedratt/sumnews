"""FastAPI application factory.

`create_app` wires the web layer to the domain modules and owns the process-wide lifespan:
schema creation, a connected `TelegramSource`, and an `AsyncIOScheduler` running `run_ingest`
on an interval (with an immediate first pass). Run it with::

    make run-web            # uvicorn sumnews.app:create_app --factory --reload
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from sumnews.database.engine import dispose_engine, init_models, session_scope
from sumnews.loggers import configure_logging, logger
from sumnews.parsing.ingest import run_ingest
from sumnews.parsing.manager import IngestManager
from sumnews.parsing.telegram import TelegramSource
from sumnews.settings import Settings, get_settings
from sumnews.watchlist import Watchlist, load_watchlist
from sumnews.web.routes import INGEST_JOB_ID, router

_STATIC_DIR = Path(__file__).parent / "web" / "static"


async def _run_ingest_pass(
    settings: Settings, watchlist: Watchlist, telegram: TelegramSource | None
) -> None:
    """One scheduled ingest pass. A scheduler job must never let an exception escape."""
    try:
        async with session_scope() as session:
            manager = IngestManager.build(settings, watchlist, session, telegram=telegram)
            await run_ingest(manager)
    except Exception as error:
        logger.exception("app | ingest pass failed error=%r", error)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    settings = get_settings()
    watchlist = load_watchlist(settings.WATCHLIST_PATH)
    await init_models()

    telegram: TelegramSource | None = None
    if settings.TELEGRAM_API_ID and settings.TELEGRAM_API_HASH and settings.TELEGRAM_SESSION:
        telegram = TelegramSource(
            settings.TELEGRAM_API_ID, settings.TELEGRAM_API_HASH, settings.TELEGRAM_SESSION
        )
        await telegram.connect()
    else:
        logger.warning("app | telegram disabled — TELEGRAM_* not set; feeds only")

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        _run_ingest_pass,
        trigger=IntervalTrigger(minutes=settings.INGEST_INTERVAL_MINUTES),
        id=INGEST_JOB_ID,
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now(UTC),
        kwargs={"settings": settings, "watchlist": watchlist, "telegram": telegram},
    )
    scheduler.start()

    app.state.settings = settings
    app.state.watchlist = watchlist
    app.state.telegram = telegram
    app.state.scheduler = scheduler
    logger.info(
        "app | started interval_minutes=%d telegram=%s",
        settings.INGEST_INTERVAL_MINUTES, telegram is not None,
    )

    try:
        yield
    finally:
        scheduler.shutdown(wait=False)
        if telegram is not None:
            await telegram.disconnect()
        await dispose_engine()


def create_app() -> FastAPI:
    app = FastAPI(title="sumnews", lifespan=lifespan)
    app.include_router(router)
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")
    return app
