"""Async persistence layer: ORM models, engine/session plumbing, and the news repository."""

from sumnews.database.engine import get_engine, get_sessionmaker, init_models, session_scope
from sumnews.database.news import NewsRepository, content_hash

__all__ = [
    "NewsRepository",
    "content_hash",
    "get_engine",
    "get_sessionmaker",
    "init_models",
    "session_scope",
]
