"""DuckDuckGo's plain HTML page, read with httpx. No extra packages needed, so it
works on Android and serves as a fallback when the `ddgs` package fails."""
from __future__ import annotations

import asyncio
from typing import List
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from .base import SearchError, SearchResult

URL = "https://html.duckduckgo.com/html/"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"


def _real_url(href: str) -> str:
    # result links look like //duckduckgo.com/l/?uddg=<encoded url>&rut=...
    if "uddg=" in href:
        q = parse_qs(urlparse(href if href.startswith("http") else "https:" + href).query)
        if q.get("uddg"):
            return unquote(q["uddg"][0])
    return href


def parse(html: str, n: int) -> List[SearchResult]:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    out: List[SearchResult] = []
    for res in soup.select("div.result"):
        if "result--ad" in (res.get("class") or []):
            continue
        a = res.select_one("a.result__a")
        if not a or not a.get("href"):
            continue
        url = _real_url(a["href"])
        if not url.startswith("http") or "duckduckgo.com/y.js" in url:
            continue
        snip = res.select_one(".result__snippet")
        out.append(SearchResult(a.get_text(" ", strip=True), url, snip.get_text(" ", strip=True) if snip else "",
                                "duckduckgo"))
        if len(out) >= n:
            break
    return out


async def search(query: str, n: int, region: str = "us-en", safesearch: str = "moderate") -> List[SearchResult]:
    data = {"q": query, "kl": region or "wt-wt", "kp": {"off": "-2", "strict": "1"}.get(safesearch, "-1")}
    last = None
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=15, headers={"User-Agent": UA}, follow_redirects=True) as c:
                r = await c.post(URL, data=data)
            if r.status_code == 200:
                results = parse(r.text, n)
                if results or "No results" in r.text or "no-results" in r.text:
                    return results
                last = "empty page (rate limited?)"
            else:
                last = f"HTTP {r.status_code}"
        except httpx.HTTPError as e:
            last = type(e).__name__
        await asyncio.sleep(1.5 * (attempt + 1))
    raise SearchError(f"DuckDuckGo: {last}")
