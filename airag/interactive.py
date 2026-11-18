"""Interactive explainers: a small generated HTML/JS simulation for an article.

The page runs in a sandboxed iframe (no same-origin, strict CSP), so even a
misbehaving generated page can't reach AIRAG's API, the network or the disk.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from . import history, languages, prompts
from .llm import get_llm
from .llm.jsonutil import complete_json

CSP = ("<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; script-src 'unsafe-inline'; "
       "style-src 'unsafe-inline'; img-src data: blob:; font-src data:; media-src data: blob:; form-action 'none'; "
       "base-uri 'none'; frame-src 'none'; worker-src 'none'; manifest-src 'none'\">")
# runs before anything the AI wrote: links and window.open can't take the explainer to a web page
GUARD = ("<script>(function(){var stop=function(e){var a=e.target&&e.target.closest&&e.target.closest('a[href]');"
         "if(a&&!/^#/.test(a.getAttribute('href')||'')){e.preventDefault();}};"
         "document.addEventListener('click',stop,true);document.addEventListener('auxclick',stop,true);"
         "try{window.open=function(){return null};}catch(e){}})();</script>")
# things that could load from or go to the internet without a script, or replace the rules above
_STRIP = [
    re.compile(r"<meta\b[^>]*http-equiv\s*=\s*[\"']?\s*(refresh|content-security-policy|set-cookie)[^>]*>", re.I),
    re.compile(r"<base\b[^>]*>", re.I),
    re.compile(r"<link\b[^>]*>", re.I),
    re.compile(r"<(iframe|frame|frameset|object|embed|portal|applet)\b[^>]*>.*?</\1\s*>", re.I | re.S),
    re.compile(r"<(iframe|frame|frameset|object|embed|portal|applet)\b[^>]*/?>", re.I),
]


async def check(llm, query: str, article_md: str) -> dict:
    try:
        d = await complete_json(llm, *prompts.interactive_check(query, article_md), max_tokens=400)
        return {"suitable": bool(d.get("suitable")), "idea": str(d.get("idea") or "")[:300],
                "reason": str(d.get("reason") or "")[:160]}
    except Exception as e:
        return {"suitable": False, "idea": "", "reason": f"check failed: {e}"[:160]}


SAFE_MARK = "<meta name='airag-safe' content='2'>"


def safe(html: str) -> str:
    """For showing or exporting a stored explainer: ones made before the current safety rules are cleaned now."""
    return html if not html or SAFE_MARK in html[:4000] else clean_html(html)


def clean_html(text: str) -> str:
    """The generated page, made safe to show: only the HTML document; no auto-redirects, <base>, <link> or
    embedded frames; and the no-network rules (CSP) plus a link guard placed FIRST, before anything the AI wrote,
    so no script of its own runs before the rules apply."""
    t = re.sub(r"^```(?:html)?\s*|```\s*$", "", text.strip(), flags=re.I | re.M).strip()
    start = re.search(r"<!doctype html|<html", t, re.I)
    if start:
        t = t[start.start():]
    end = t.lower().rfind("</html>")
    if end != -1:
        t = t[: end + 7]
    for pat in _STRIP:
        t = pat.sub("", t)
    from .jsguard import PRELUDE, guard_html
    t = guard_html(t)                      # endless loops can't freeze the app
    safe_head = f"<meta charset='utf-8'>{SAFE_MARK}{CSP}{GUARD}{PRELUDE}"
    m = re.search(r"<html\b[^>]*>", t, re.I)
    if m:      # right after <html ...>: the browser puts it at the very start of <head>
        t = t[: m.end()] + safe_head + t[m.end():]
    else:
        t = f"<!DOCTYPE html><html>{safe_head}<body>{t}</body></html>"
    return t


# web code lookups only when the search itself is about programming (code from the web can carry prompt
# injection or subtle bugs, so it's never fetched just to "learn" for a normal explainer)
_CODE_TOPIC = re.compile(r"\b(code|coding|program(ming)?|javascript|typescript|python|java|c\+\+|c#|html|css|"
                         r"algorithm|api|sql|regex|function|library|framework|canvas|webgl|d3\.js|chart\.js)\b", re.I)


def code_related(query: str) -> bool:
    return bool(_CODE_TOPIC.search(query or ""))


def local_examples(settings: dict, idea: str, limit: int = 2500) -> str:
    """JavaScript from the reader's own My library files that matches the explainer idea (no web access).
    Only code-looking lines from script/web files are passed on, as untrusted reference."""
    from .library import LIBRARY
    try:
        hits = LIBRARY.search([idea[:200] + " javascript function canvas"], limit=6, per_file_chars=4000)
    except Exception:
        return ""
    out, size = [], 0
    for hit in hits:
        path = str(hit.get("path") or "")
        if not re.search(r"\.(js|mjs|ts|html?|md|txt)$", path, re.I):
            continue
        lines = [ln for ln in str(hit.get("excerpt") or "").splitlines()
                 if re.search(r"[;{}()=]|=>|function |const |let ", ln)]
        code = "\n".join(lines)[:1500]
        if len(code) > 200:
            out.append(f"From your file {Path(path).name}:\n{code}")
            size += len(code)
            if size > limit:
                break
    return "\n\n".join(out)


async def code_examples(settings: dict, idea: str, pages: int = 2) -> str:
    """Looks up a couple of code examples for similar browser simulations (code blocks only, small).
    Any failure just means no examples."""
    import re
    from .fetch import _fetch_http
    from .search import get_search
    try:
        hits = await get_search(settings).text(f"{idea[:120]} javascript canvas simulation example code", n=5)
    except Exception:
        return ""
    out = []
    for hit in hits[:4]:
        if len(out) >= pages:
            break
        try:
            page = await _fetch_http(hit.url, settings["fetch"])
        except Exception:
            continue
        if not page.ok:
            continue
        # _fetch_http keeps readable text only; code shows up as indented / symbol-heavy lines
        lines = [ln for ln in page.text.splitlines() if re.search(r"[;{}()=]|=>|function |const |let ", ln)]
        code = "\n".join(lines)[:2500]
        if len(code) > 300:
            out.append(f"From {hit.url}:\n{code}")
    return "\n\n".join(out)


_NUM = re.compile(r"\d[\d.,]*\s*(%|percent|USD|EUR|NOK|\$|€|£|kr|million|billion|bn|m\b|k\b|kg|km|°|years?)?", re.I)


def source_figures(rec: dict, limit: int = 3500) -> str:
    """Lines from the sources' notes that hold several numbers (prices, stock values, measurements),
    so the explainer can chart data the article only mentions in passing."""
    out, size = [], 0
    for s in rec.get("sources") or []:
        if (s.get("relevance") or 0) < 4 or not s.get("n"):
            continue
        parts = [s.get("summary") or ""] + [str(f) for f in (s.get("findings") or [])]
        for line in re.split(r"(?<=[.;])\s+|\n", " ".join(parts)):
            if len(_NUM.findall(line)) >= 2 and 20 < len(line) < 400:
                item = f"[{s['n']}] {line.strip()}"
                out.append(item)
                size += len(item)
                if size > limit:
                    return "\n".join(out)
    return "\n".join(out)


async def generate(settings: dict, rid: str, ui_lang: Optional[str], force: bool = False) -> dict:
    rec = history.get(rid)
    if not rec or rec.get("outcome") != "article":
        raise ValueError("Article not found")
    if rec.get("interactive_html") and not force:
        return {"html": safe(rec["interactive_html"]), "cached": True}
    llm = get_llm(settings)
    info = rec.get("interactive")
    if info is None:
        # the search ran without the explainer check (to save tokens): check now, when the reader asks
        info = await check(llm, rec["query"], rec.get("article", ""))
        rec["interactive"] = info
        history.update(rid, {"interactive": info})
    if not info.get("suitable") and not force:
        raise ValueError(f"An interactive explainer wouldn't help with this article. {info.get('reason', '')}".strip())
    lang = languages.answer_language(settings, ui_lang, rec["query"])
    level = str(settings.get("prompts", {}).get("explainer_level") or "medium")
    examples = ""
    research = settings.get("research", {})
    if info.get("idea") and research.get("explainer_local_examples", True):
        examples = local_examples(settings, info["idea"])
    if (info.get("idea") and research.get("explainer_web_examples", False) and code_related(rec.get("query", ""))
            and not examples):
        examples = await code_examples(settings, info["idea"])
    raw = await llm.complete(*prompts.interactive(rec["query"], info.get("idea", ""), rec.get("article", ""), lang, level,
                                                  examples, source_figures(rec)),
                             max_tokens=prompts.explainer_level(level)[1])
    html = clean_html(raw)
    rec["interactive_html"] = html
    history.update(rid, {"interactive_html": html})
    return {"html": html, "cached": False, "interactive": info}
