from __future__ import annotations

from typing import List
from urllib.parse import quote

import httpx

from . import register
from .base import SearchBackend, SearchError, SearchResult


@register
class Marginalia(SearchBackend):
    """Marginalia Search: a small independent search engine that favours text-heavy, non-commercial pages
    (blogs, hobby sites, documentation). Free; the shared "public" key has a rate limit."""
    name = "marginalia"
    label = "Marginalia (independent, free)"
    supports_images = False
    fields = [
        {"key": "api_key", "label": "Marginalia API key", "type": "secret", "default": "public",
         "help": "\"public\" works for everyone but is rate limited. Ask Marginalia for your own key if you use it a lot."},
    ]

    async def text(self, query: str, n: int = 10, recent: str = "") -> List[SearchResult]:
        key = (self.cfg.get("api_key") or "public").strip()
        url = f"https://api.marginalia.nu/{quote(key)}/search/{quote(query)}"
        try:
            async with httpx.AsyncClient(timeout=20, headers={"Accept": "application/json"}) as c:
                r = await c.get(url, params={"count": min(n, 20)})
            if r.status_code == 503:
                raise SearchError("Marginalia is busy (the free key's limit was reached). Try again in a minute.")
            r.raise_for_status()
            data = r.json()
        except SearchError:
            raise
        except Exception as e:
            raise SearchError(f"Marginalia: {e}")
        return [SearchResult(x.get("title") or x.get("url", ""), x["url"], x.get("description", ""), self.name)
                for x in data.get("results", []) if x.get("url")]
