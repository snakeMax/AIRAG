"""Web search without extra packages, used on Android and when the `ddgs` package fails.

Tries DuckDuckGo's HTML page, then its "lite" page, then Mojeek. Requests are sent one
at a time with a short gap, because firing several at once is what gets them blocked
(DuckDuckGo answers a blocked request with HTTP 202 and no results). When DuckDuckGo
blocks us, it's skipped for a few minutes and Mojeek is used directly.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import List, Optional
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from .base import SearchError, SearchResult

log = logging.getLogger("airag.search")

UA = ("Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/131.0.0.0 Mobile Safari/537.36")
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.8",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Upgrade-Insecure-Requests": "1",
}
GAP = 1.3            # seconds between requests to the same engine
COOLDOWN = 300       # skip DuckDuckGo this long after it blocks us

_lock = asyncio.Lock()
_last = 0.0
_ddg_blocked_until = 0.0


class Blocked(Exception):
    pass


def _real_url(href: str) -> str:
    # DuckDuckGo result links look like //duckduckgo.com/l/?uddg=<encoded url>&rut=...
    if "uddg=" in href:
        q = parse_qs(urlparse(href if href.startswith("http") else "https:" + href).query)
        if q.get("uddg"):
            return unquote(q["uddg"][0])
    return href


def _ok_url(url: str) -> bool:
    return url.startswith("http") and "duckduckgo.com/y.js" not in url and "duckduckgo.com/l/" not in url


def parse(html: str, n: int) -> List[SearchResult]:
    """DuckDuckGo html.duckduckgo.com results page."""
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
        if not _ok_url(url):
            continue
        snip = res.select_one(".result__snippet")
        out.append(SearchResult(a.get_text(" ", strip=True), url, snip.get_text(" ", strip=True) if snip else "",
                                "duckduckgo"))
        if len(out) >= n:
            break
    return out


def parse_lite(html: str, n: int) -> List[SearchResult]:
    """DuckDuckGo lite.duckduckgo.com: a table where a link row is followed by a snippet row."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    out: List[SearchResult] = []
    for a in soup.select("a.result-link"):
        url = _real_url(a.get("href") or "")
        if not _ok_url(url):
            continue
        snippet = ""
        row = a.find_parent("tr")
        nxt = row.find_next_sibling("tr") if row else None
        if nxt:
            td = nxt.select_one("td.result-snippet")
            snippet = td.get_text(" ", strip=True) if td else ""
        out.append(SearchResult(a.get_text(" ", strip=True), url, snippet, "duckduckgo"))
        if len(out) >= n:
            break
    return out


def parse_mojeek(html: str, n: int) -> List[SearchResult]:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    out: List[SearchResult] = []
    for li in soup.select("ul.results-standard > li, .results ul > li"):
        a = li.select_one("h2 a, a.title")
        if not a or not str(a.get("href", "")).startswith("http"):
            continue
        snip = li.select_one("p.s")
        out.append(SearchResult(a.get_text(" ", strip=True), a["href"], snip.get_text(" ", strip=True) if snip else "",
                                "mojeek"))
        if len(out) >= n:
            break
    return out


def _no_results_page(html: str) -> bool:
    low = html.lower()
    return "no results" in low or "no-results" in low or "keine ergebnisse" in low


async def _request(c: httpx.AsyncClient, method: str, url: str, **kw) -> httpx.Response:
    global _last
    async with _lock:
        wait = _last + GAP - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        try:
            return await c.request(method, url, **kw)
        finally:
            _last = time.monotonic()


_DF = {"day": "d", "week": "w", "month": "m", "year": "y"}


async def _ddg(c, query: str, n: int, region: str, safesearch: str, recent: str = "") -> List[SearchResult]:
    kp = {"off": "-2", "strict": "1"}.get(safesearch, "-1")
    data = {"q": query, "kl": region or "wt-wt", "kp": kp}
    if recent in _DF:
        data["df"] = _DF[recent]
    attempts = [
        ("GET", "https://lite.duckduckgo.com/lite/", parse_lite, {"params": data}),
        ("POST", "https://html.duckduckgo.com/html/", parse, {"data": data,
         "headers": {"Origin": "https://html.duckduckgo.com", "Referer": "https://html.duckduckgo.com/"}}),
        ("POST", "https://lite.duckduckgo.com/lite/", parse_lite, {"data": data,
         "headers": {"Origin": "https://lite.duckduckgo.com", "Referer": "https://lite.duckduckgo.com/"}}),
    ]
    for method, url, parser, kw in attempts:
        r = await _request(c, method, url, **kw)
        if r.status_code == 200:
            results = parser(r.text, n)
            if results or _no_results_page(r.text):
                return results
        log.info("DuckDuckGo %s %s -> HTTP %s", method, url, r.status_code)
    raise Blocked("DuckDuckGo is limiting requests right now")


async def _via_webview(query: str, n: int, region: str, safesearch: str, recent: str = "") -> Optional[List[SearchResult]]:
    """On Android: load the lite page in a hidden WebView, which looks like a normal phone browser."""
    from ..paths import ANDROID
    if not ANDROID:
        return None
    from urllib.parse import urlencode
    from .. import android_bridge
    kp = {"off": "-2", "strict": "1"}.get(safesearch, "-1")
    params = {"q": query, "kl": region or "wt-wt", "kp": kp}
    if recent in _DF:
        params["df"] = _DF[recent]
    url = "https://lite.duckduckgo.com/lite/?" + urlencode(params)
    async with _lock:
        html = await asyncio.to_thread(android_bridge.render_page, url, 20)
    if not html:
        return None
    results = parse_lite(html, n)
    return results if results or _no_results_page(html) else None


async def _mojeek(c, query: str, n: int, safesearch: str) -> List[SearchResult]:
    params = {"q": query, "safe": "0" if safesearch == "off" else "1"}
    r = await _request(c, "GET", "https://www.mojeek.com/search", params=params,
                       headers={"Referer": "https://www.mojeek.com/"})
    if r.status_code != 200:
        raise Blocked(f"Mojeek HTTP {r.status_code}")
    return parse_mojeek(r.text, n)


async def search(query: str, n: int, region: str = "us-en", safesearch: str = "moderate",
                 recent: str = "") -> List[SearchResult]:
    global _ddg_blocked_until
    errors: List[str] = []
    async with httpx.AsyncClient(timeout=15, headers=HEADERS, follow_redirects=True) as c:
        if time.monotonic() >= _ddg_blocked_until:
            try:
                return await _ddg(c, query, n, region, safesearch, recent)
            except Blocked as e:
                _ddg_blocked_until = time.monotonic() + COOLDOWN
                errors.append(str(e))
            except httpx.HTTPError as e:
                errors.append(f"DuckDuckGo: {type(e).__name__}")
        results = await _via_webview(query, n, region, safesearch, recent)
        if results is not None:
            return results
        for attempt in range(2):
            try:
                results = await _mojeek(c, query, n, safesearch)
                if results:
                    return results
                errors.append("Mojeek: no results")
                break
            except (Blocked, httpx.HTTPError) as e:
                errors.append(str(e) or type(e).__name__)
                await asyncio.sleep(2 * (attempt + 1))
    raise SearchError("; ".join(errors[:2]) + ". Try again in a minute, or add a Brave Search API key "
                      "in Settings → Search for reliable results.")


def blocked_recently() -> Optional[float]:
    left = _ddg_blocked_until - time.monotonic()
    return left if left > 0 else None
