"""Page reading: fast HTTP + readability extraction, optional headless browser
(Playwright) for JavaScript-heavy pages, and PDF text extraction."""
from __future__ import annotations

import asyncio
import io
import re
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import List, Optional
from urllib.parse import urljoin

import httpx

from .config import DEFAULT_UA
from .paths import ANDROID

MAX_BYTES = 8_000_000
MAX_TEXT = 200_000
_cache: "OrderedDict[str, Page]" = OrderedDict()
_CACHE_CHARS = 25_000_000      # memory budget for cached page text (~50 MB)
_cache_chars = 0

_BAD_IMG = ("logo", "icon", "sprite", "avatar", "pixel", "badge", "/ads/", "advert", "tracking",
            ".svg", "emoji", "spacer", "blank.", "placeholder", "gravatar", "share", "button")


@dataclass
class Page:
    url: str
    final_url: str = ""
    ok: bool = False
    error: str = ""
    title: str = ""
    text: str = ""
    description: str = ""
    site_name: str = ""
    author: str = ""
    published: str = ""
    og_image: str = ""
    scholarly: bool = False
    images: List[dict] = field(default_factory=list)
    via: str = "http"
    binary: bool = False


# public API
async def fetch_page(url: str, cfg: dict) -> Page:
    global _cache_chars
    if url in _cache:
        _cache.move_to_end(url)
        return _cache[url]
    mode = cfg.get("fetcher", "auto")
    page: Optional[Page] = None
    if cfg.get("youtube", True):
        from . import youtube
        if youtube.video_id(url):     # videos: description + captions instead of the (empty) web page
            page = await youtube.read(url, cfg, int(cfg.get("youtube_retries", 1)))
            if page.ok:
                _cache[url] = page
                _cache_chars += len(page.text)
            return page
    if mode in ("auto", "http"):
        page = await _fetch_http(url, cfg)
    want_browser = mode == "browser" or (
        mode == "auto" and page is not None and not page.binary
        and (not page.ok or len(page.text) < 500) and browser_available())
    if want_browser:
        bp = await _fetch_browser(url, cfg)
        if page is None or (bp.ok and len(bp.text) > len(page.text)):
            page = bp
    elif ANDROID and page is not None and not page.binary and (not page.ok or len(page.text) < 500):
        wp = await _fetch_webview(url, cfg)   # pages that block plain requests or need JavaScript
        if wp.ok and len(wp.text) > len(page.text):
            page = wp
    assert page is not None
    _cache[url] = page
    _cache_chars += len(page.text)
    while _cache_chars > _CACHE_CHARS and len(_cache) > 1:
        _, old = _cache.popitem(last=False)
        _cache_chars -= len(old.text)
    return page


def browser_available() -> bool:
    from .browser_install import installed
    return installed()


# HTTP
async def _fetch_http(url: str, cfg: dict) -> Page:
    headers = {
        "User-Agent": cfg.get("user_agent") or DEFAULT_UA,
        "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8",
        "Accept-Language": cfg.get("accept_language") or "en-US,en;q=0.9",
    }
    t = float(cfg.get("timeout") or 15)
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=httpx.Timeout(t, connect=10),
                                     headers=headers, max_redirects=8) as c:
            async with c.stream("GET", url) as r:
                if r.status_code >= 400:
                    return Page(url, error=f"HTTP {r.status_code}")
                ctype = r.headers.get("content-type", "").lower()
                final = str(r.url)
                if any(x in ctype for x in ("image/", "video/", "audio/", "zip", "octet-stream")):
                    return Page(url, final_url=final, error=f"Unsupported content ({ctype.split(';')[0]})", binary=True)
                buf = bytearray()
                async for chunk in r.aiter_bytes():
                    buf += chunk
                    if len(buf) > MAX_BYTES:
                        break
                encoding = r.charset_encoding or "utf-8"
    except httpx.TimeoutException:
        return Page(url, error="Timed out")
    except httpx.HTTPError as e:
        return Page(url, error=type(e).__name__)
    data = bytes(buf)
    if "pdf" in ctype or data[:5] == b"%PDF-":
        return await asyncio.to_thread(_parse_pdf, url, final, data)
    text = data.decode(encoding, errors="replace")
    if "text/plain" in ctype:
        return Page(url, final_url=final, ok=True, text=text[:MAX_TEXT], title=final.rsplit("/", 1)[-1])
    return await asyncio.to_thread(parse_html, url, final, text, "http")


def _parse_pdf(url: str, final: str, data: bytes) -> Page:
    try:
        from pypdf import PdfReader
    except ImportError:
        return Page(url, final_url=final, error="PDF (pip install pypdf to read PDFs)", binary=True)
    try:
        reader = PdfReader(io.BytesIO(data))
        parts = [(p.extract_text() or "") for p in reader.pages[:60]]
        meta = reader.metadata
        title = (meta.title if meta and meta.title else "") or final.rsplit("/", 1)[-1]
        text = re.sub(r"[ \t]+", " ", "\n".join(parts))
        return Page(url, final_url=final, ok=bool(text.strip()), text=text[:MAX_TEXT], title=str(title),
                    via="pdf", scholarly=True, binary=True, error="" if text.strip() else "PDF has no text layer")
    except Exception as e:
        return Page(url, final_url=final, error=f"PDF error: {e}"[:200], binary=True)


# HTML parsing
def _int(v) -> int:
    try:
        return int(str(v).replace("px", "").strip())
    except (TypeError, ValueError):
        return 0


def parse_html(url: str, final: str, html: str, via: str = "http") -> Page:
    from bs4 import BeautifulSoup
    try:
        import trafilatura  # better extraction; not available on Android
    except ImportError:
        trafilatura = None

    p = Page(url, final_url=final, via=via)
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:  # lxml missing (Android) or broken markup
        soup = BeautifulSoup(html, "html.parser")

    def meta(*names: str) -> str:
        for n in names:
            tag = soup.find("meta", attrs={"property": n}) or soup.find("meta", attrs={"name": n})
            if tag and tag.get("content"):
                return str(tag["content"]).strip()
        return ""

    title_tag = soup.title.get_text(strip=True) if soup.title else ""
    p.title = meta("og:title", "twitter:title", "citation_title") or title_tag
    p.description = meta("og:description", "description", "twitter:description")
    p.site_name = meta("og:site_name", "application-name", "citation_journal_title")
    p.author = meta("author", "article:author", "citation_author")
    p.published = meta("article:published_time", "citation_publication_date", "citation_date",
                       "date", "dc.date", "DC.date.issued", "pubdate")
    p.scholarly = bool(meta("citation_doi", "citation_journal_title", "citation_pmid"))
    og = meta("og:image", "og:image:url", "twitter:image", "twitter:image:src")
    p.og_image = urljoin(final, og) if og else ""

    # Images inside the main content
    scope = soup.find("article") or soup.find("main") or soup.body
    seen = set()
    for im in (scope.find_all("img") if scope else []):
        src = im.get("data-src") or im.get("data-original") or im.get("data-lazy-src") or im.get("src") or ""
        if (not src or src.startswith("data:")) and im.get("srcset"):
            src = im["srcset"].split(",")[-1].strip().split(" ")[0]
        if not src or src.startswith("data:"):
            continue
        src = urljoin(final, src)
        low = src.lower()
        if any(b in low for b in _BAD_IMG) or src in seen:
            continue
        w, h = _int(im.get("width")), _int(im.get("height"))
        if (w and w < 160) or (h and h < 120):
            continue
        fig = im.find_parent("figure")
        cap = fig.figcaption.get_text(" ", strip=True) if fig is not None and fig.figcaption else ""
        seen.add(src)
        p.images.append({"src": src, "alt": (im.get("alt") or im.get("title") or "").strip()[:200], "caption": cap[:300]})
        if len(p.images) >= 12:
            break

    # Main text
    text = ""
    if trafilatura is not None:
        try:
            text = trafilatura.extract(html, url=final, include_comments=False, include_tables=True,
                                       favor_recall=True, deduplicate=True) or ""
        except Exception:
            text = ""
    if len(text) < 300:
        for t in soup(["script", "style", "noscript", "nav", "footer", "header", "form", "svg", "aside"]):
            t.decompose()
        body = soup.find("article") or soup.find("main") or soup.body or soup
        fallback = re.sub(r"\n{3,}", "\n\n", body.get_text("\n", strip=True))
        if len(fallback) > len(text):
            text = fallback
    p.text = text[:MAX_TEXT]
    p.ok = len(p.text.strip()) > 0
    if not p.ok:
        p.error = "No readable text"
    return p


# headless browser
_pw = None
_browser = None
_lock = asyncio.Lock()


async def _get_browser():
    global _pw, _browser
    async with _lock:
        if _browser is None:
            from playwright.async_api import async_playwright
            _pw = await async_playwright().start()
            _browser = await _pw.chromium.launch(headless=True)
    return _browser


_webview_lock = asyncio.Lock()


async def _fetch_webview(url: str, cfg: dict) -> Page:
    """Android: render the page in a hidden WebView (one at a time, to spare the battery)."""
    from . import android_bridge
    async with _webview_lock:
        try:
            html = await asyncio.to_thread(android_bridge.render_page, url, int(cfg.get("timeout") or 15) + 5)
        except Exception as e:
            return Page(url, error=f"WebView: {e}"[:200], via="webview")
    if not html:
        return Page(url, error="Page didn't load", via="webview")
    return parse_html(url, url, html, via="webview")


async def _fetch_browser(url: str, cfg: dict) -> Page:
    if not browser_available():
        return Page(url, error="Headless browser not installed (Settings → Page reading)", via="browser")
    t = float(cfg.get("timeout") or 15)
    try:
        b = await _get_browser()
        ctx = await b.new_context(user_agent=cfg.get("user_agent") or DEFAULT_UA)
        try:
            pg = await ctx.new_page()

            async def block(route):
                if route.request.resource_type in ("media", "font"):
                    await route.abort()
                else:
                    await route.continue_()
            await pg.route("**/*", block)
            await pg.goto(url, timeout=t * 1000, wait_until="domcontentloaded")
            try:
                await pg.wait_for_load_state("networkidle", timeout=6000)
            except Exception:
                pass
            html, final = await pg.content(), pg.url
        finally:
            await ctx.close()
        return await asyncio.to_thread(parse_html, url, final, html, "browser")
    except Exception as e:
        return Page(url, error=f"Browser: {e}"[:200], via="browser")


async def shutdown() -> None:
    global _pw, _browser
    try:
        if _browser is not None:
            await _browser.close()
        if _pw is not None:
            await _pw.stop()
    except Exception:
        pass
    _browser = _pw = None
