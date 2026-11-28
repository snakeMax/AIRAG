"""Reading Wikipedia (and other Wikimedia sites) through their official API instead of the web page.

Why: since mid-2025 Wikimedia blocks traffic that doesn't follow its User-Agent policy (a program must say
who it is, with a contact URL). AIRAG's page reader sends a browser's User-Agent, which from a program
(no browser fingerprint) looks like a disguised bot, so many Wikipedia pages came back as 403/429 and
were marked unreadable - and one refusal also marked the whole site as "blocked" for 6 hours.

Here the article comes from the TextExtracts API as plain text with its section headings kept (rewritten
as Markdown "## Heading" lines so passage selection can work section by section), with an honest
User-Agent, at most 2 requests at a time, and one polite retry after a 429 (rate limit).
"""
from __future__ import annotations

import asyncio
import re
from typing import Optional
from urllib.parse import unquote, urlsplit

import httpx

from . import __version__

UA = f"AIRAG/{__version__} (https://github.com/snakeMax/AIRAG; open-source research assistant)"
HOSTS = ("wikipedia.org", "wiktionary.org", "wikivoyage.org", "wikibooks.org", "wikinews.org",
         "wikiquote.org", "wikisource.org", "wikiversity.org", "wikimedia.org", "mediawiki.org")
MAX_CHARS = 1_000_000
_sem = asyncio.Semaphore(2)
_HEAD = re.compile(r"^(={2,6})\s*(.+?)\s*\1\s*$", re.M)


def article(url: str) -> Optional[tuple]:
    """(api_url, title) for a Wikimedia article address, else None. Handles /wiki/Title, mobile (en.m.)
    hosts and ?title= addresses; special pages, files, talk pages and edit links are left to the normal reader."""
    try:
        u = urlsplit(url)
    except ValueError:
        return None
    host = (u.hostname or "").lower()
    if u.scheme not in ("http", "https") or not any(host == h or host.endswith("." + h) for h in HOSTS):
        return None
    if host in ("commons.wikimedia.org", "upload.wikimedia.org") or host.startswith("upload."):
        return None
    title = ""
    if u.path.startswith("/wiki/"):
        title = unquote(u.path[6:])
    elif u.path in ("/w/index.php", "/index.php") and "title=" in (u.query or ""):
        if re.search(r"(^|&)(action|oldid|diff)=", u.query or ""):
            return None
        m = re.search(r"(?:^|&)title=([^&]+)", u.query)
        title = unquote(m.group(1)) if m else ""
    title = title.replace("_", " ").strip()
    if not title or ":" in title.split("/")[0] and title.split(":")[0].lower() in {
            "special", "file", "image", "talk", "user", "user talk", "category", "help", "template", "portal",
            "wikipedia", "mediawiki", "module", "draft", "spesial", "fil", "kategori", "datei", "spezial"}:
        return None
    api_host = host.replace(".m.", ".")
    return (f"https://{api_host}/w/api.php", title)


def _markdown_headings(text: str) -> str:
    """"== History ==" -> "## History", so the passage picker sees the sections."""
    return _HEAD.sub(lambda m: "#" * len(m.group(1)) + " " + m.group(2), text)


async def read(url: str, timeout: float = 15):
    """A fetch.Page with the article's plain text, or None when this isn't a Wikimedia article."""
    from .fetch import Page
    from . import offline
    hit = article(url)
    if not hit:
        return None
    if offline.blocked():
        return Page(url, error=offline.MESSAGE)
    api, title = hit
    params = {"action": "query", "prop": "extracts|description|pageimages|info", "explaintext": 1,
              "exsectionformat": "wiki", "redirects": 1, "titles": title, "format": "json", "formatversion": 2,
              "piprop": "original", "inprop": "url", "utf8": 1}
    async with _sem:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=10), follow_redirects=True,
                                         headers={"User-Agent": UA, "Api-User-Agent": UA}) as c:
                for attempt in range(2):
                    r = await c.get(api, params=params)
                    if r.status_code == 429 and attempt == 0:      # rate limited: wait as asked (at most 5 s), once
                        try:
                            wait = min(5.0, float(r.headers.get("retry-after") or 2))
                        except ValueError:
                            wait = 2.0
                        await asyncio.sleep(wait)
                        continue
                    break
        except httpx.TimeoutException:
            return Page(url, error="Timed out", via="wikipedia-api")
        except httpx.HTTPError as e:
            return Page(url, error=type(e).__name__, via="wikipedia-api")
    if r.status_code >= 400:
        # a refusal here is about the rate, not a bot wall: don't mark the whole site as blocked
        return Page(url, error=f"HTTP {r.status_code} from the Wikipedia API", via="wikipedia-api")
    try:
        pages = (r.json().get("query") or {}).get("pages") or []
    except ValueError:
        return Page(url, error="The Wikipedia API sent something unexpected", via="wikipedia-api")
    p = pages[0] if pages else {}
    if not p or p.get("missing") or p.get("invalid"):
        return Page(url, error="No such article", via="wikipedia-api")
    text = _markdown_headings(str(p.get("extract") or "")).strip()
    host = urlsplit(api).hostname or ""
    page = Page(url, final_url=str(p.get("fullurl") or url), ok=bool(text), via="wikipedia-api",
                title=str(p.get("title") or title), text=text[:MAX_CHARS], description=str(p.get("description") or ""),
                site_name="Wikipedia" if host.endswith("wikipedia.org") else host,
                og_image=str((p.get("original") or {}).get("source") or ""))
    if not page.ok:
        page.error = "No readable text"
    return page
