"""'Rewrite with my instructions' on selected article text.

The selection is plain page text; the article is Markdown with [n] citations. The paragraph(s) of the
Markdown that contain the selection are found by word overlap, rewritten by the AI (citations kept),
shown side by side, and only replaced when the reader chooses Replace.
"""
from __future__ import annotations

import re
import time
from typing import AsyncIterator, Optional, Tuple

from . import history, languages, prompts
from .guard import Fence
from .llm import get_llm

_WORD = re.compile(r"\w+", re.UNICODE)


def _words(text: str) -> list:
    t = re.sub(r"\[\d+(?:,\s*\d+)*\]", " ", text)
    t = re.sub(r"[*_`#>|]", " ", t)
    return [w.lower() for w in _WORD.findall(t)]


def locate(article_md: str, selection: str) -> Optional[Tuple[int, int]]:
    """(start, end) of the Markdown block(s) that best contain the selected text."""
    sel = _words(selection)
    if not sel:
        return None
    blocks, pos = [], 0
    for m in re.finditer(r"(?:[^\n]+\n?)+", article_md):
        blocks.append((m.start(), m.end(), _words(m.group())))
    best, best_score = None, 0.0
    target = set(sel)
    for i in range(len(blocks)):
        acc = set()
        for j in range(i, min(i + 4, len(blocks))):     # a selection can span a few paragraphs
            acc |= set(blocks[j][2])
            score = len(target & acc) / len(target) - 0.02 * (j - i)
            if score > best_score:
                best, best_score = (blocks[i][0], blocks[j][1]), score
    if not best or best_score < 0.6:
        return None
    s, e = best
    return s, e - (1 if article_md[s:e].endswith("\n") else 0)


SYSTEM = """Rewrite the given passage of a research article following the reader's instructions.
Keep every fact and every citation marker like [2] attached to the claim it supports; don't add facts that aren't
in the passage. Keep the Markdown formatting style (headings, lists). Reply with the rewritten passage only.
Write in {lang}."""


async def rewrite(settings: dict, rid: str, selection: str, instructions: str,
                  ui_lang: Optional[str] = None) -> AsyncIterator[dict]:
    rec = history.get(rid)
    if not rec or rec.get("outcome") != "article":
        raise ValueError("Article not found")
    md = rec.get("article") or ""
    span = locate(md, selection)
    if not span:
        raise ValueError("Couldn't find the selected text in the article. Select whole sentences and try again.")
    old = md[span[0]:span[1]]
    lang = languages.answer_language(settings, ui_lang, rec.get("query", ""))
    prompts.use(settings)
    fence = Fence()
    system = SYSTEM.format(lang=lang) + "\n" + prompts.SAFETY + "\n" + prompts.UNTRUSTED + "\n" + fence.rule()
    user = (f"Reader's instructions: {instructions[:800] or 'Make it clearer and easier to read.'}\n\n"
            f"Selected part the reader cares about most:\n{fence.wrap(selection[:2000])}\n\n"
            f"Passage to rewrite (Markdown):\n{fence.wrap(old)}")
    yield {"type": "target", "old": old}
    out = ""
    async for piece in get_llm(settings).stream(system, user, max_tokens=2000):
        out += piece
        yield {"type": "token", "text": piece}
    out = re.sub(r"<think>.*?</think>", "", out, flags=re.S).strip().strip("`")
    yield {"type": "done", "old": old, "new": out}


def apply(settings: dict, rid: str, old: str, new: str, instructions: str = "") -> str:
    problem = []

    def change(rec: dict) -> None:
        md = rec.get("article") or ""
        if rec.get("outcome") != "article":
            problem.append("Article not found")
            return
        if old not in md:
            problem.append("The article changed since the rewrite was made. Select the text and rewrite it again.")
            return
        rec["edits"] = (rec.get("edits") or [])[-19:] + [{"old": old, "new": new}]
        rec["article"] = md.replace(old, new.strip(), 1)
        # keep it in the answers thread, so the reader can see what changed and ask to elaborate on it
        rec["thread"] = (rec.get("thread") or [])[-39:] + [{
            "q": instructions.strip() or "Rewrite", "mode": "rewrite", "selection": old[:500], "a": new.strip(),
            "added": True, "at": time.strftime("%Y-%m-%dT%H:%M:%S")}]
    rec = history.update(rid, change)
    if rec is None or problem:
        raise ValueError(problem[0] if problem else "Article not found")
    return rec["article"]
