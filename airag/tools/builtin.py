"""The built-in tools. Each one: what the model is told, its arguments, and what it does."""
from __future__ import annotations

import datetime as dt

from . import AGENTS, Tool, register

SAFE = AGENTS                       # on by default for every agent type
NO_SUB = ("standard", "autonomous")


async def _calculator(s, expression: str = "") -> str:
    from .calc import calculate
    try:
        e, exact, approx = await calculate(expression)
    except Exception as err:
        return f"Calculator couldn't read that: {err}. Rewrite it with numbers, + - * / ** ( ), letters for unknowns, " \
               "and functions like solve(), diff(), integrate(), simplify(), sqrt(), log()."
    return f"{e} = {exact}" + (f" ≈ {approx}" if approx and approx != exact else "")


async def _datetime(s) -> str:
    now = dt.datetime.now().astimezone()
    return now.strftime("%A %d %B %Y, %H:%M (%Z, UTC%z)")


def _sources(s) -> list:
    rec = s.ctx.get("record") or {}
    return rec.get("sources") or []


async def _search_sources(s, query: str = "") -> str:
    """Looks through ALL sources AIRAG read for this search (also ones not cited in the article)."""
    from ..passages import tokenize
    terms = set(tokenize(query))
    cited = {x.get("url") for x in (s.ctx.get("record") or {}).get("article_sources") or []}
    scored = []
    for src in _sources(s):
        text = " ".join([src.get("title") or "", src.get("summary") or ""] +
                        [f.get("claim", "") for f in src.get("findings") or []])
        low = text.lower()
        hits = sum(1 for t in terms if t in low)
        if hits:
            scored.append((hits, src, text))
    scored.sort(key=lambda z: -z[0])
    if not scored:
        return "No source mentions that."
    out = []
    for _, src, _text in scored[:5]:
        n = next((a.get("n") for a in (s.ctx.get("record") or {}).get("article_sources") or [] if a.get("url") == src.get("url")), None)
        tag = f"[{n}]" if n else "(not cited in the article yet)"
        claims = "; ".join(f.get("claim", "") for f in (src.get("findings") or [])[:4])
        out.append(f"{tag} {src.get('title') or src.get('url')} - {src.get('domain')} (trust {src.get('trust', '?')}/10)\n"
                   f"  {src.get('summary') or ''}\n  Findings: {claims or '-'}\n  URL: {src.get('url')}")
    return "\n".join(out)


async def _web_search(s, query: str = "") -> str:
    from ..search import get_search
    hits = await get_search(s.ctx["settings"]).text(query[:200], n=6)
    if not hits:
        return "No results."
    return "\n".join(f"- {h.title} | {h.url}\n  {h.snippet[:220]}" for h in hits[:6])


async def _read_page(s, url: str = "", focus: str = "") -> str:
    from .. import guard
    from ..fetch import fetch_page
    from ..passages import select_passages, tokenize
    if not url.startswith(("http://", "https://")):
        return "Only web addresses (https://...) can be read."
    page = await fetch_page(url, s.ctx["settings"]["fetch"])
    if not page.ok:
        return f"Couldn't read the page: {page.error}"
    text, _ = guard.clean(page.text, s.ctx["settings"])
    terms = tokenize(focus or s.ctx.get("question", ""))
    return f"{page.title} ({url})\n" + select_passages(text, terms, 2500)


async def _client(s, action: str, **data) -> str:
    s.client_actions.append({"action": action, **data})
    return "Done (the app does this for the user)."


async def _read_aloud(s, text: str = "") -> str:
    return await _client(s, "listen", text=text)


async def _more_sources(s) -> str:
    return await _client(s, "more-sources")


async def _copy(s, text: str = "") -> str:
    return await _client(s, "copy", text=text)


async def _pin(s) -> str:
    return await _client(s, "pin")


register(Tool("calculator", "Exact maths with SymPy: arithmetic, percentages, statistics (mean, median, stdev), "
              "equations (\"2*x + 3 = 11\" or solve(x**2-4, x)), simplify(), expand(), factor(), diff(f, x), "
              "integrate(f, x), limit(). Turn words and letters into a numeric/symbolic expression first.",
              {"expression": "str"}, _calculator, ("expression",), "Calculator",
              "Exact maths, equations, algebra and statistics. Free (no AI tokens).", defaults=SAFE))
register(Tool("datetime", "The current date, time and time zone.", {}, _datetime, (), "Date and time",
              "Today's date and the time. Free.", defaults=SAFE))
register(Tool("search_sources", "Search everything in the pages read for this search, including pages the article "
              "doesn't cite yet.", {"query": "str"}, _search_sources, ("query",), "Search this article's sources",
              "Looks through the pages AIRAG already read. Free.", defaults=SAFE))
register(Tool("web_search", "Search the web (titles, links, snippets only). Use only when the article's sources "
              "don't cover a relevant question.", {"query": "str"}, _web_search, ("query",), "Web search",
              "New searches for fact-checks and follow-ups. Uses the network.", costly=True, defaults=SAFE))
register(Tool("read_page", "Read the relevant passages of one web page.", {"url": "str", "focus": "str"},
              _read_page, ("url",), "Read a web page", "Reads a page found by web search. Uses tokens.",
              costly=True, defaults=SAFE))
register(Tool("read_aloud", "Read text aloud to the user with the device's voice.", {"text": "str"}, _read_aloud,
              ("text",), "Read aloud", "Speaks text with your device's voice. Free.", client=True, defaults=SAFE))
register(Tool("locate_more_sources", "Start a background search for more sources; they are added to the article "
              "(or to the results page). Use when the sources are clearly too few or too weak.", {}, _more_sources,
              (), "Locate more sources", "Same as the button. Uses about as many tokens as a short search.",
              costly=True, client=True, defaults=NO_SUB))
register(Tool("copy", "Copy exact text (e.g. a quote) to the user's clipboard.", {"text": "str"}, _copy, ("text",),
              "Copy to clipboard", "Copies an exact quote or result for you.", client=True, defaults=("autonomous",)))
register(Tool("pin_article", "Pin this article to the top of the home page.", {}, _pin, (), "Pin article",
              "Pins the article to Home.", client=True, defaults=("autonomous",)))
