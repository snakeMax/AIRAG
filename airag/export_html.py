"""Export an article (and its interactive explainer) as ONE standalone HTML file.

Everything is packed inside: text, styles, the source list, pictures (as data: URLs) and the
explainer (in a sandboxed iframe). The file opens in any browser, offline, without AIRAG, so it
can be sent to someone.

The article HTML comes from AIRAG's own page; it's cleaned again here (no scripts, no event
handlers, no outside frames) before it goes into the file.
"""
from __future__ import annotations

import base64
import datetime as dt
import html
from pathlib import Path
from typing import Optional

from . import __version__, paths

EXPORTS_SUBDIR = "Exports"
MAX_IMAGES = 16
MAX_IMAGE_BYTES = 1_500_000
ALLOWED_TAGS = {"article", "section", "div", "span", "p", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li",
                "a", "strong", "b", "em", "i", "u", "s", "blockquote", "code", "pre", "table", "thead", "tbody",
                "tr", "th", "td", "figure", "figcaption", "img", "br", "hr", "sup", "sub", "mark", "small"}
ALLOWED_ATTRS = {"class", "href", "src", "alt", "title", "id", "data-n", "colspan", "rowspan", "loading"}


def _clean(body_html: str):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(body_html or "", "html.parser")
    for el in soup.find_all(["script", "style", "iframe", "object", "embed", "form", "input", "button", "svg",
                             "noscript", "link", "meta", "template"]):
        el.decompose()
    for el in soup.find_all(True):
        if el.name not in ALLOWED_TAGS:
            el.unwrap()
            continue
        for a in list(el.attrs):
            if a not in ALLOWED_ATTRS:
                del el.attrs[a]
        if el.name == "a":
            href = str(el.get("href") or "")
            if not href.startswith(("http://", "https://", "#")):
                del el["href"]
            else:
                el["target"] = "_blank"
                el["rel"] = "noopener noreferrer"
        if el.name == "img" and not str(el.get("src") or "").startswith(("http://", "https://", "data:image/")):
            el.decompose()
    return soup


def _embed_images(soup) -> int:
    import httpx
    n = 0
    imgs = [im for im in soup.find_all("img") if str(im.get("src", "")).startswith("http")]
    with httpx.Client(timeout=15, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0 AIRAG"}) as c:
        for im in imgs[:MAX_IMAGES]:
            try:
                r = c.get(im["src"])
                ctype = r.headers.get("content-type", "").split(";")[0].strip()
                if r.status_code == 200 and ctype.startswith("image/") and ctype != "image/svg+xml" \
                        and len(r.content) <= MAX_IMAGE_BYTES:
                    im["src"] = f"data:{ctype};base64," + base64.b64encode(r.content).decode()
                    n += 1
                    continue
            except Exception:
                pass
            im.decompose()     # can't be embedded: leave it out rather than depend on the web
    for im in imgs[MAX_IMAGES:]:
        im.decompose()
    return n


def build(rec: dict, body_html: str, title: str, include_explainer: bool = True, lang: str = "en",
          summary_html: str = "", pictures: bool = True) -> str:
    soup = _clean(body_html)
    if pictures:
        _embed_images(soup)
    else:
        for el in soup.find_all(["img", "figure"]):
            el.decompose()
    summary = ""
    if summary_html.strip():
        s = _clean(summary_html)
        for a in s.find_all("a"):
            a.unwrap()
        summary = f'<aside class="x-summary"><h2>Summary</h2>{s.decode()}</aside>'
        first = soup.find(class_="a-byline") or soup.find("h1")
        if first is not None:
            from bs4 import BeautifulSoup
            first.insert_after(BeautifulSoup(summary, "html.parser"))
            summary = ""
    css = (paths.WEB_DIR / "css" / "export.css").read_text(encoding="utf-8")
    explainer = ""
    if include_explainer and rec.get("interactive_html"):
        from .interactive import safe
        frame = html.escape(safe(rec["interactive_html"]), quote=True)
        explainer = f"""
<section class="x-explainer"><h2>Interactive explainer</h2>
<iframe sandbox="allow-scripts" referrerpolicy="no-referrer" srcdoc="{frame}" title="Interactive explainer"></iframe>
</section>"""
    made = dt.date.today().isoformat()
    from .openfile import data_block
    data = data_block(rec)        # lets AIRAG open this page again exactly (plain data, never run)
    return f"""<!DOCTYPE html>
<html lang="{html.escape(lang)}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; frame-src 'self' about: data:; script-src 'unsafe-inline'">
<title>{html.escape(title)}</title>
<style>{css}</style></head>
<body>{data}<main class="x-page">
{summary}{soup.decode()}
{explainer}
<footer class="x-foot">Written by AI with AIRAG {html.escape(__version__)} from the sources listed above, exported {made}.
Check the sources before relying on it.</footer>
</main></body></html>"""


def export(rec: dict, settings: dict, body_html: str, title: str, include_explainer: bool = True,
           lang: str = "en", summary_html: str = "", pictures: bool = True) -> Path:
    from .mylibrary import _safe_name, ensure
    out_dir = ensure(settings) / EXPORTS_SUBDIR
    out_dir.mkdir(parents=True, exist_ok=True)
    day = str(rec.get("created") or dt.date.today().isoformat())[:10]
    target = out_dir / f"{day} {_safe_name(title or rec.get('query') or 'Article')}.html"
    target.write_text(build(rec, body_html, title, include_explainer, lang, summary_html, pictures), encoding="utf-8")
    return target


def find(settings: dict, name: str) -> Optional[Path]:
    from .mylibrary import ensure
    d = (ensure(settings) / EXPORTS_SUBDIR).resolve()
    p = (d / name).resolve()
    return p if p.parent == d and p.suffix == ".html" and p.is_file() else None
