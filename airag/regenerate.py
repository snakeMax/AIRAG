"""Regenerate article: writes the article again from the same sources, following the reader's instructions
(or, with none, a default "make it clearer" pass). The old text stays in the version history.

Keep my edits (on by default): paragraphs the reader rewrote and answers they added are passed to the writer as
text to keep word for word; an added answer that's missing afterwards is put back at the end.
"""
from __future__ import annotations

import re
from typing import AsyncIterator, Optional

from . import history, languages, prompts, versions
from .llm import get_llm
from .prompts import Fence

DEFAULT = ("Write a better version of this article: make the key points clearer and easier to find, explain "
           "anything that could confuse a reader, keep a steady, neutral tone, and keep every fact and citation.")
LENGTH = {"same": "Keep it about the same length as the current version.",
          "shorter": "Make it clearly shorter than the current version (about two thirds), keeping the key facts.",
          "longer": "Make it longer than the current version, with more detail and explanation from the sources."}


def _kept(rec: dict) -> tuple:
    """(rewritten passages, added answer sections) the reader made."""
    article = rec.get("article") or ""
    edits = [e["new"].strip() for e in rec.get("edits") or [] if e.get("new") and e["new"].strip() in article]
    added = []
    for t in rec.get("thread") or []:
        if t.get("added") and t.get("mode") != "rewrite" and t.get("a"):
            heading = f"## {str(t.get('q', ''))[:120]}"
            if heading in article:
                start = article.index(heading)
                nxt = article.find("\n## ", start + len(heading))
                added.append(article[start: nxt if nxt != -1 else len(article)].strip())
    return edits[-8:], added[-6:]


async def regenerate(settings: dict, rid: str, instructions: str = "", keep_edits: bool = True,
                     length: str = "same", ui_lang: Optional[str] = None) -> AsyncIterator[dict]:
    rec = history.get(rid)
    if not rec or rec.get("outcome") != "article" or not rec.get("article"):
        raise ValueError("Article not found")
    sources = [s for s in rec.get("article_sources") or [] if s.get("n")]
    if not sources:
        raise ValueError("This article has no sources to write from. Use Search again instead.")
    for s in sources:
        s.setdefault("domain", "")
        s.setdefault("url", s.get("path") or "")
    lang = languages.answer_language(settings, ui_lang, rec.get("query", ""))
    wanted = " ".join((instructions or "").split())[:1500]
    edits, added = _kept(rec) if keep_edits else ([], [])
    fence = Fence()
    system, user = prompts.article(rec.get("query", ""), rec.get("intent") or rec.get("query", ""),
                                   rec.get("answer_type", ""), sources, lang)
    keep_txt = ""
    if edits or added:
        keep_txt = ("\nKeep these passages word for word, in a fitting place (the reader wrote or chose them):\n"
                    + fence.wrap("\n\n---\n\n".join(edits + added)) + "\n")
    user += f"""

THIS IS A NEW VERSION of an article the reader already has (current version below, for reference only - write
the whole article again, don't describe changes).
What the reader wants different: {wanted or DEFAULT}
{LENGTH.get(length, LENGTH["same"])}
Use the same source numbers. Never add facts the sources don't support.{keep_txt}
Current version:
{fence.wrap((rec.get("article") or "")[:14000])}"""
    system = system + "\n" + fence.rule()
    llm = get_llm(settings)
    yield {"type": "article_start", "sources": sources}
    md = ""
    async for piece in llm.stream(system, user, max_tokens=int(settings["research"].get("article_max_tokens", 8192))):
        md += piece
        yield {"type": "token", "text": piece}
    clean = re.sub(r"<think>.*?</think>", "", md, flags=re.S).strip()
    if len(clean.split()) < 30:
        raise ValueError("The new version came out empty or too short, so the article wasn't changed.")
    for sec in added:                      # an answer the reader added must not get lost
        if sec.split("\n", 1)[0] not in clean:
            clean = clean.rstrip() + "\n\n" + sec + "\n"
    title = re.search(r"^#\s+(.+)$", clean, re.M)

    def put(cur: dict) -> None:
        before, before_src = cur.get("article") or "", cur.get("article_sources")
        cur["article"] = clean
        if title:
            cur["title"] = title.group(1).strip()
        cur.pop("translations", None)      # translations were of the old text
        versions.note_change(cur, before, "regenerated", wanted or "Improved", before_src)
    saved = history.update(rid, put)
    if saved is None:
        raise ValueError("The article was deleted while it was being regenerated.")
    yield {"type": "done", "id": rid}
