from __future__ import annotations

from dataclasses import dataclass
from typing import List


class SearchError(Exception):
    pass


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str = ""
    backend: str = ""


@dataclass
class ImageResult:
    title: str
    image: str
    thumbnail: str = ""
    page_url: str = ""
    width: int = 0
    height: int = 0
    source: str = ""


class SearchBackend:
    name = "base"
    label = "Base"
    supports_images = False
    fields: List[dict] = []

    def __init__(self, cfg: dict, common: dict):
        self.cfg = cfg
        self.common = common

    async def text(self, query: str, n: int = 10, recent: str = "") -> List[SearchResult]:
        """recent: "" (any time), "day", "week", "month", "year", or a date range "2026-01-01..2026-02-15"
        (either end may be empty) - only results from that period."""
        raise NotImplementedError

    async def images(self, query: str, n: int = 10) -> List[ImageResult]:
        return []


def to_int(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def date_range(recent: str):
    """'2026-01-01..2026-02-15' -> ('2026-01-01', '2026-02-15'); open ends are filled in; None if not a range."""
    import datetime as dt
    if not recent or ".." not in recent:
        return None
    a, b = (x.strip() for x in recent.split("..", 1))
    try:
        a = dt.date.fromisoformat(a).isoformat() if a else "1990-01-01"
        b = dt.date.fromisoformat(b).isoformat() if b else dt.date.today().isoformat()
    except ValueError:
        return None
    return (a, b) if a <= b else (b, a)


def range_to_period(recent: str) -> str:
    """Closest named period for engines without custom ranges (SearXNG): smallest one covering the start date."""
    import datetime as dt
    r = date_range(recent)
    if not r:
        return recent if recent in ("day", "week", "month", "year") else ""
    days = (dt.date.today() - dt.date.fromisoformat(r[0])).days
    for name, limit in (("day", 1), ("week", 7), ("month", 31), ("year", 366)):
        if days <= limit:
            return name
    return ""
