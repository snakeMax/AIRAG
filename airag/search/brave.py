from __future__ import annotations

from typing import List

import httpx

from . import register
from .base import ImageResult, SearchBackend, SearchError, SearchResult, date_range


@register
class Brave(SearchBackend):
    name = "brave"
    label = "Brave Search API"
    supports_images = True
    fields = [
        {"key": "api_key", "label": "Brave API key", "type": "secret", "default": "", "env": "BRAVE_API_KEY",
         "help": "Free tier at api-dashboard.search.brave.com"},
    ]

    async def _get(self, path: str, params: dict) -> dict:
        if not self.cfg.get("api_key"):
            raise SearchError("Add a Brave API key in Settings → Search.")
        params.setdefault("safesearch", self.common.get("safesearch", "moderate"))
        try:
            async with httpx.AsyncClient(timeout=20) as c:
                r = await c.get("https://api.search.brave.com/res/v1" + path, params=params,
                                headers={"X-Subscription-Token": self.cfg["api_key"], "Accept": "application/json"})
            r.raise_for_status()
            return r.json()
        except Exception as e:
            raise SearchError(f"Brave: {e}")

    async def text(self, query: str, n: int = 10, recent: str = "") -> List[SearchResult]:
        params = {"q": query, "count": min(n, 20)}
        if recent in ("day", "week", "month", "year"):
            params["freshness"] = {"day": "pd", "week": "pw", "month": "pm", "year": "py"}[recent]
        elif date_range(recent):
            params["freshness"] = "to".join(date_range(recent))
        d = await self._get("/web/search", params)
        return [SearchResult(r.get("title", ""), r["url"], r.get("description", ""), self.name)
                for r in d.get("web", {}).get("results", []) if r.get("url")]

    async def images(self, query: str, n: int = 10) -> List[ImageResult]:
        d = await self._get("/images/search", {"q": query, "count": min(n, 50), "safesearch": "strict"})
        return [ImageResult(r.get("title", ""), (r.get("properties") or {}).get("url", ""),
                            (r.get("thumbnail") or {}).get("src", ""), r.get("url", ""), source=r.get("source", ""))
                for r in d.get("results", []) if (r.get("properties") or {}).get("url")]
