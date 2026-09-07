"""Request-scoped dependencies for the web layer.

Long-lived objects (the scheduler, the connected `TelegramSource`, the loaded `Watchlist`)
are put on ``app.state`` by the lifespan in :mod:`sumnews.app` and read back here. The DB
session is created fresh per request and committed on a clean response.
"""

from collections.abc import AsyncIterator
from typing import Annotated

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from sumnews.database.engine import session_scope
from sumnews.database.news import NewsRepository
from sumnews.watchlist import Watchlist


async def get_session() -> AsyncIterator[AsyncSession]:
    """One session per request: commits on a clean exit, rolls back on an exception."""
    async with session_scope() as session:
        yield session


def get_repo(session: Annotated[AsyncSession, Depends(get_session)]) -> NewsRepository:
    repo = NewsRepository(session)
    return repo


def get_scheduler(request: Request) -> AsyncIOScheduler:
    scheduler: AsyncIOScheduler = request.app.state.scheduler
    return scheduler


def get_watchlist(request: Request) -> Watchlist:
    watchlist: Watchlist = request.app.state.watchlist
    return watchlist


SessionDep = Annotated[AsyncSession, Depends(get_session)]
RepoDep = Annotated[NewsRepository, Depends(get_repo)]
SchedulerDep = Annotated[AsyncIOScheduler, Depends(get_scheduler)]
WatchlistDep = Annotated[Watchlist, Depends(get_watchlist)]
