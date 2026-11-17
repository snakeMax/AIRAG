from __future__ import annotations

from typing import List

import httpx

from . import register
from .base import ImageResult, SearchBackend, SearchError, SearchResult, to_int


@register
class GoogleCSE(SearchBackend):
    name = "google_cse"
    label = "Google (Programmable Search API)"
    supports_images = True
    fields = [
        {"key": "api_key", "label": "Google API key", "type": "secret", "default": "", "env": "GOOGLE_API_KEY"},
        {"key": "cx", "label": "Search engine ID (cx)", "type": "text", "default": "",
         "help": "Create one at programmablesearchengine.google.com, enable 'Search the entire web' and 'Image search'."},
    ]

    async def _get(self, params: dict) -> list:
        if not (self.cfg.get("api_key") and self.cfg.get("cx")):
            raise SearchError("Google search needs an API key and a search engine ID (Settings → Search).")
        params.update({"key": self.cfg["api_key"], "cx": self.cfg["cx"],
                       "safe": "off" if self.common.get("safesearch") == "off" else "active"})
        items: list = []
        try:
            async with httpx.AsyncClient(timeout=20) as c:
                want = params.pop("n")
                start = 1
                while len(items) < want and start <= 91:
                    r = await c.get("https://www.googleapis.com/customsearch/v1",
                                    params={**params, "num": min(10, want - len(items)), "start": start})
                    r.raise_for_status()
                    batch = r.json().get("items", [])
                    if not batch:
                        break
                    items += batch
                    start += len(batch)
        except Exception as e:
            raise SearchError(f"Google: {e}")
        return items

    async def text(self, query: str, n: int = 10, recent: str = "") -> List[SearchResult]:
        params = {"q": query, "n": n}
        if recent in ("day", "week", "month", "year"):
            params["dateRestrict"] = {"day": "d1", "week": "w1", "month": "m1", "year": "y1"}[recent]
        items = await self._get(params)
        return [SearchResult(i.get("title", ""), i["link"], i.get("snippet", ""), self.name) for i in items if i.get("link")]

    async def images(self, query: str, n: int = 10) -> List[ImageResult]:
        items = await self._get({"q": query, "n": n, "searchType": "image"})
        out = []
        for i in items:
            im = i.get("image") or {}
            out.append(ImageResult(i.get("title", ""), i.get("link", ""), im.get("thumbnailLink", ""),
                                   im.get("contextLink", ""), to_int(im.get("width")), to_int(im.get("height")), "google"))
        return out
