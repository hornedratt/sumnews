"""The editorial watchlist: who and what we track.

Loaded from a YAML file (path in :attr:`sumnews.settings.Settings.WATCHLIST_PATH`). This is
version-controlled config, edited by hand; it holds no secrets.
"""

from functools import cached_property
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class Company(BaseModel):
    """A company we track — the subject, or one of its competitors."""

    model_config = {"frozen": True}

    name: str
    aliases: tuple[str, ...] = ()
    domains: tuple[str, ...] = ()

    @property
    def names(self) -> tuple[str, ...]:
        """The canonical name plus every alias."""
        return (self.name, *self.aliases)


class Feed(BaseModel):
    """One RSS/Atom feed."""

    model_config = {"frozen": True}

    name: str
    url: str


class Watchlist(BaseModel):
    """The full tracking configuration."""

    model_config = {"frozen": True}

    company: Company
    competitors: tuple[Company, ...] = ()
    keywords: tuple[str, ...] = Field(default=(),
        description="Extra topical terms that mark an article as a candidate")
    tags: tuple[str, ...] = ()
    rss_feeds: tuple[Feed, ...] = ()
    telegram_channels: tuple[str, ...] = ()

    @cached_property
    def all_companies(self) -> tuple[Company, ...]:
        """The subject company followed by every competitor."""
        return (self.company, *self.competitors)

    @cached_property
    def all_terms(self) -> frozenset[str]:
        """Lowercased set of every term the keyword prefilter matches on."""
        terms: set[str] = set()
        for company in self.all_companies:
            terms.update(name.lower() for name in company.names)
        terms.update(keyword.lower() for keyword in self.keywords)
        terms.update(tag.lower() for tag in self.tags)
        return frozenset(terms)

    @cached_property
    def all_domains(self) -> frozenset[str]:
        """Lowercased set of every domain associated with a tracked company."""
        domains: set[str] = set()
        for company in self.all_companies:
            domains.update(domain.lower() for domain in company.domains)
        return frozenset(domains)


def load_watchlist(path: Path) -> Watchlist:
    """Parse and validate the watchlist YAML at ``path``."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    watchlist = Watchlist.model_validate(raw)
    return watchlist
