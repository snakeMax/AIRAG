from __future__ import annotations

from typing import List

import httpx

from . import register
from .base import ImageResult, SearchBackend, SearchError, SearchResult, range_to_period


@register
class SearXNG(SearchBackend):
    name = "searxng"
    label = "SearXNG (self-hosted, aggregates Google/Bing/...)"
    supports_images = True
    fields = [
        {"key": "url", "label": "SearXNG URL", "type": "url", "default": "http://localhost:8080",
         "help": "Your instance must have the JSON format enabled (search.formats: [html, json])."},
    ]

    async def _get(self, query: str, category: str, recent: str = "") -> list:
        params = {"q": query, "format": "json", "categories": category,
                  "safesearch": {"off": 0, "moderate": 1, "strict": 2}.get(self.common.get("safesearch"), 1)}
        period = range_to_period(recent)
        if period:
            params["time_range"] = period
        try:
            async with httpx.AsyncClient(timeout=20) as c:
                r = await c.get(str(self.cfg.get("url", "")).rstrip("/") + "/search", params=params)
            r.raise_for_status()
            return r.json().get("results", [])
        except Exception as e:
            raise SearchError(f"SearXNG: {e}")

    async def text(self, query: str, n: int = 10, recent: str = "") -> List[SearchResult]:
        res = await self._get(query, "general", recent)
        return [SearchResult(r.get("title", ""), r["url"], r.get("content", ""), self.name)
                for r in res[:n] if r.get("url")]

    async def images(self, query: str, n: int = 10) -> List[ImageResult]:
        res = await self._get(query, "images")
        return [ImageResult(r.get("title", ""), r.get("img_src", ""), r.get("thumbnail_src", ""), r.get("url", ""),
                            source=r.get("engine", "")) for r in res[:n] if r.get("img_src")]
