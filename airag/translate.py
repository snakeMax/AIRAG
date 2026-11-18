"""Translate an article or a results page into another language on the fly (with the AI model,
so expressions come across naturally). Article translations are kept with the search in history."""
from __future__ import annotations

from typing import AsyncIterator, List, Optional

from . import history, languages, prompts
from .llm import get_llm
from .llm.jsonutil import complete_json


def _lang_name(code: str) -> str:
    return languages.name(code) or code


async def article(settings: dict, markdown: str, lang: str, rid: Optional[str] = None) -> AsyncIterator[str]:
    rec = history.get(rid) if rid else None
    cached = ((rec or {}).get("translations") or {}).get(lang)
    if cached:
        yield cached
        return
    llm = get_llm(settings)
    out = ""
    async for piece in llm.stream(*prompts.translate(markdown[:40000], _lang_name(lang)), max_tokens=8000):
        out += piece
        yield piece
    if rec is not None and out.strip():
        def keep(r: dict) -> None:
            r.setdefault("translations", {})[lang] = out
        history.update(rec["id"], keep)


async def items(settings: dict, entries: List[dict], lang: str) -> List[dict]:
    """[{id, title, summary, findings: [..]}] -> the same with the texts translated."""
    small = [{"id": e.get("id"), "title": e.get("title", ""), "summary": e.get("summary", ""),
              "findings": [str(f.get("claim", "")) if isinstance(f, dict) else str(f)
                           for f in (e.get("findings") or [])][:8]} for e in entries[:30]]
    llm = get_llm(settings)
    data = await complete_json(llm, *prompts.translate_items(small, _lang_name(lang)), max_tokens=6000)
    if isinstance(data, dict):
        data = data.get("items") or next((v for v in data.values() if isinstance(v, list)), [])
    return [d for d in data if isinstance(d, dict)] if isinstance(data, list) else []
