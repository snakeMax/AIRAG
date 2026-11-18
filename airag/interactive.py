"""Interactive explainers: a small generated HTML/JS simulation for an article.

The page runs in a sandboxed iframe (no same-origin, strict CSP), so even a
misbehaving generated page can't reach AIRAG's API, the network or the disk.
"""
from __future__ import annotations

import re
from typing import Optional

from . import history, languages, prompts
from .llm import get_llm
from .llm.jsonutil import complete_json

CSP = ("<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; script-src 'unsafe-inline'; "
       "style-src 'unsafe-inline'; img-src data: blob:; font-src data:\">")


async def check(llm, query: str, article_md: str) -> dict:
    try:
        d = await complete_json(llm, *prompts.interactive_check(query, article_md), max_tokens=400)
        return {"suitable": bool(d.get("suitable")), "idea": str(d.get("idea") or "")[:300],
                "reason": str(d.get("reason") or "")[:160]}
    except Exception as e:
        return {"suitable": False, "idea": "", "reason": f"check failed: {e}"[:160]}


def clean_html(text: str) -> str:
    t = re.sub(r"^```(?:html)?\s*|```\s*$", "", text.strip(), flags=re.I | re.M).strip()
    start = re.search(r"<!doctype html|<html", t, re.I)
    if start:
        t = t[start.start():]
    end = t.lower().rfind("</html>")
    if end != -1:
        t = t[: end + 7]
    if "<html" not in t.lower():
        t = f"<!DOCTYPE html><html><head><meta charset='utf-8'></head><body>{t}</body></html>"
    # enforce the CSP inside the document as well as on the iframe
    t = re.sub(r"<head([^>]*)>", lambda m: f"<head{m.group(1)}>{CSP}", t, count=1, flags=re.I) if re.search(r"<head", t, re.I) \
        else t.replace("<html>", f"<html><head>{CSP}</head>", 1)
    return t


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
        return {"html": rec["interactive_html"], "cached": True}
    llm = get_llm(settings)
    info = rec.get("interactive")
    if info is None:
        # the search ran without the explainer check (to save tokens): check now, when the reader asks
        info = await check(llm, rec["query"], rec.get("article", ""))
        rec["interactive"] = info
        history.save(rec, int(settings["app"].get("history_limit", 300)))
    if not info.get("suitable") and not force:
        raise ValueError(f"An interactive explainer wouldn't help with this article. {info.get('reason', '')}".strip())
    lang = languages.answer_language(settings, ui_lang, rec["query"])
    level = str(settings.get("prompts", {}).get("explainer_level") or "medium")
    examples = ""
    if settings.get("research", {}).get("explainer_examples", True) and info.get("idea"):
        examples = await code_examples(settings, info["idea"])
    raw = await llm.complete(*prompts.interactive(rec["query"], info.get("idea", ""), rec.get("article", ""), lang, level,
                                                  examples, source_figures(rec)),
                             max_tokens=prompts.explainer_level(level)[1])
    html = clean_html(raw)
    rec["interactive_html"] = html
    history.save(rec, int(settings["app"].get("history_limit", 300)))
    return {"html": html, "cached": False, "interactive": info}
