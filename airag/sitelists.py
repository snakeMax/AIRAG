"""Blocked and favourite sites.

Both are comma-separated lists. An entry without a path ("example.com") covers that site and all
its subdomains (news.example.com). An entry with a path ("example.com/blog") covers only addresses
that start with that directory, and everything below it (example.com/blog/2024/post).
"""
from __future__ import annotations

from typing import List, Tuple
from urllib.parse import urlsplit

FAVOURITE_BOOST = 2


def parse(text: str) -> List[Tuple[str, str]]:
    """'a.com, b.org/docs/' -> [('a.com', ''), ('b.org', '/docs')]"""
    out = []
    for raw in str(text or "").replace("\n", ",").split(","):
        e = raw.strip().lower()
        if not e:
            continue
        if "://" in e:
            e = e.split("://", 1)[1]
        host, _, path = e.partition("/")
        host = host.split("@")[-1].split(":")[0].lstrip("*.").strip(".")
        if host.startswith("www."):
            host = host[4:]
        path = ("/" + path).rstrip("/") if path else ""
        if host:
            out.append((host, path))
    return out


def matches(url: str, entries: List[Tuple[str, str]]) -> bool:
    try:
        parts = urlsplit(url if "://" in url else "https://" + url)
    except ValueError:
        return False
    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = (parts.path or "/").lower()
    for h, p in entries:
        if host == h or host.endswith("." + h):
            if not p or path == p or path.startswith(p + "/"):
                return True
    return False


class SiteLists:
    def __init__(self, research: dict):
        self.blocked = parse(research.get("skip_domains", ""))
        self.favourites = parse(research.get("favourite_sites", ""))

    def blocked_url(self, url: str) -> bool:
        return matches(url, self.blocked)

    def adjust(self, url: str, prior: int, label: str) -> Tuple[int, str]:
        """Favourite sites start with a higher trust score."""
        if matches(url, self.favourites):
            return min(10, prior + FAVOURITE_BOOST), (label + " · " if label else "") + "Your favourite site"
        return prior, label
