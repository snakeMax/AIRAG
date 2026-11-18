"""Wikis searched alongside the normal search engine ("Use wiki" in Settings -> Search).

Wikipedia is on by default (in the answer's language) and trusted; any MediaWiki-based wiki can be
added (Fandom, PsychonautWiki, the Minecraft wiki...). Only titles and short snippets come back from
the search; the pages themselves are read like any other source (relevant passages only).
"""
from __future__ import annotations

import asyncio
import html
import re
from typing import List, Optional
from urllib.parse import quote, urlsplit

import httpx

UA = "AIRAG (research assistant; https://github.com/snakeMax/AIRAG)"
DEFAULT = [{"name": "Wikipedia", "api": "wikipedia", "about": "General encyclopedia: overviews, history, science, people, places.",
            "enabled": True, "trust": 7}]


def api_url(api: str, lang: str = "en") -> str:
    """'wikipedia' -> https://<lang>.wikipedia.org/w/api.php; a domain or URL -> its api.php."""
    a = (api or "").strip()
    if a.lower() == "wikipedia":
        code = (lang or "en").split("-")[0].lower()
        code = {"nb": "no", "zh-hans": "zh"}.get(code, code)    # Bokmål Wikipedia lives at no.wikipedia.org
        return f"https://{code}.wikipedia.org/w/api.php"
    if "://" not in a:
        a = "https://" + a
    if a.endswith("api.php"):
        return a
    return a.rstrip("/") + "/api.php"


def _strip(snippet: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", snippet or "")).strip()


async def search(wiki: dict, query: str, n: int = 3, lang: str = "en", timeout: float = 12) -> List[dict]:
    """[{title, url, snippet, wiki}] from one wiki (empty on any error)."""
    from . import offline
    if offline.blocked():
        return []
    url = api_url(wiki.get("api", ""), lang)
    # the site info in the same request tells where its articles live (/wiki/Title, /w/Title, ...)
    params = {"action": "query", "list": "search", "srsearch": query, "srlimit": n, "format": "json",
              "srprop": "snippet", "utf8": 1, "meta": "siteinfo", "siprop": "general"}
    try:
        async with httpx.AsyncClient(timeout=timeout, headers={"User-Agent": UA}, follow_redirects=True) as c:
            r = await c.get(url, params=params)
            r.raise_for_status()
            q = r.json().get("query") or {}
    except Exception:
        return []
    hits = q.get("search") or []
    g = q.get("general") or {}
    server = str(g.get("server") or f"https://{urlsplit(url).netloc}")
    if server.startswith("//"):
        server = "https:" + server
    path = str(g.get("articlepath") or "/wiki/$1")
    if "$1" not in path:
        path = "/wiki/$1"
    return [{"title": h["title"], "url": server + path.replace("$1", quote(h["title"].replace(" ", "_"))),
             "snippet": _strip(h.get("snippet", "")), "wiki": wiki.get("name") or g.get("sitename") or server}
            for h in hits if h.get("title")]


async def search_all(wikis: List[dict], query: str, n: int = 3, lang: str = "en") -> List[dict]:
    on = [w for w in wikis if w.get("enabled", True) and w.get("api")]
    results = await asyncio.gather(*(search(w, query, n, lang) for w in on))
    out = []
    for w, res in zip(on, results):
        for r in res:
            out.append({**r, "trust": int(w.get("trust", 6))})
    return out


async def site_info(api: str) -> Optional[dict]:
    """Checks that an address is a working MediaWiki and returns its name and main page."""
    candidates = [api_url(api)]
    if not api.strip().endswith("api.php"):
        a = api.strip()
        a = a if "://" in a else "https://" + a
        candidates.append(a.rstrip("/") + "/w/api.php")
    async with httpx.AsyncClient(timeout=12, headers={"User-Agent": UA}, follow_redirects=True) as c:
        for url in candidates:
            try:
                r = await c.get(url, params={"action": "query", "meta": "siteinfo", "format": "json"})
                g = (r.json().get("query") or {}).get("general") or {}
                if g.get("sitename"):
                    return {"api": url, "name": g["sitename"], "main": g.get("base", ""), "lang": g.get("lang", "")}
            except Exception:
                continue
    return None
