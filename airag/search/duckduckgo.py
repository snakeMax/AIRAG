from __future__ import annotations

import asyncio
from typing import List

from . import register
from .base import ImageResult, SearchBackend, SearchError, SearchResult, to_int


def _ddgs():
    try:
        from ddgs import DDGS  # current package name
    except ImportError:
        try:
            from duckduckgo_search import DDGS  # legacy name
        except ImportError:
            raise SearchError("DuckDuckGo search needs the 'ddgs' package: pip install ddgs")
    return DDGS()


@register
class DuckDuckGo(SearchBackend):
    name = "duckduckgo"
    label = "DuckDuckGo (no key needed)"
    supports_images = True
    fields: list = []

    def _kw(self) -> dict:
        return {"region": self.common.get("region") or "us-en",
                "safesearch": self.common.get("safesearch") or "moderate"}

    async def text(self, query: str, n: int = 10) -> List[SearchResult]:
        def run():
            return list(_ddgs().text(query, max_results=n, **self._kw()) or [])
        raw = None
        for attempt in range(2):
            try:
                raw = await asyncio.to_thread(run)
                break
            except Exception:  # package missing (Android), rate limit or network error
                await asyncio.sleep(1.0 + attempt)
        if raw is None:
            from . import ddg_html  # plain-HTML fallback
            kw = self._kw()
            return await ddg_html.search(query, n, kw["region"], kw["safesearch"])
        out = []
        for r in raw:
            url = r.get("href") or r.get("url")
            if url:
                out.append(SearchResult(r.get("title", ""), url, r.get("body", ""), self.name))
        return out

    async def images(self, query: str, n: int = 10) -> List[ImageResult]:
        def run():
            return list(_ddgs().images(query, max_results=n, **self._kw()) or [])
        try:
            raw = await asyncio.to_thread(run)
        except Exception as e:
            raise SearchError(f"DuckDuckGo images: {e}")
        return [ImageResult(r.get("title", ""), r.get("image", ""), r.get("thumbnail", ""), r.get("url", ""),
                            to_int(r.get("width")), to_int(r.get("height")), r.get("source", ""))
                for r in raw if r.get("image")]
