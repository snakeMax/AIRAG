"""'Summarize' button: short, query-focused summaries of an article, a result
list, a single web source or a library file. Streams text chunks."""
from __future__ import annotations

from typing import AsyncIterator, Optional

from . import languages, prompts
from .fetch import fetch_page
from .library import LIBRARY
from .llm import get_llm
from .passages import select_passages, tokenize


async def summarize(settings: dict, kind: str, query: str, payload: dict, ui_lang: Optional[str]) -> AsyncIterator[str]:
    llm = get_llm(settings)
    lang = languages.answer_language(settings, ui_lang)
    terms = tokenize(query)
    if kind == "article":
        what, text = "article", str(payload.get("markdown", ""))[:24000]
    elif kind == "results":
        lines = []
        for i, s in enumerate(payload.get("items") or [], 1):
            findings = "; ".join(f.get("claim", "") for f in (s.get("findings") or [])[:5])
            lines.append(f"[{i}] {s.get('title', '')} ({s.get('domain', '')}, reliability {s.get('trust', '?')}/10): "
                         f"{s.get('summary') or s.get('snippet') or ''} {('Findings: ' + findings) if findings else ''}")
        what, text = "list of search results (numbers refer to results)", "\n".join(lines)[:20000]
    elif kind == "source":
        url = str(payload.get("url", ""))
        if url.startswith("/api/library/file/"):
            f = LIBRARY.get_file(int(url.rsplit("/", 1)[-1]))
            if not f:
                raise ValueError("File not found in your library")
            from .library import extract
            from pathlib import Path
            raw = extract(Path(f["path"]))
            what, text = f"file from the reader's library ({f['title']})", select_passages(raw, terms, 12000)
        else:
            page = await fetch_page(url, settings["fetch"])
            if not page.ok:
                raise ValueError(f"Couldn't read the page: {page.error}")
            what = f"web page ({page.title or url})"
            text = select_passages(page.text, terms, 12000)
    else:
        what, text = "text", str(payload.get("text", ""))[:20000]
    async for piece in llm.stream(*prompts.summary(query, what, text, lang), max_tokens=700):
        yield piece
