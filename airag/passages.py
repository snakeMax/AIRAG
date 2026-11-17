"""Pick the parts of a long page that matter for the query, so a small context
window still sees the one sentence where the answer is buried. Unicode-aware
(works for Norwegian, German, Japanese, Chinese, ...)."""
from __future__ import annotations

import re
from typing import Iterable, List

STOP = set("""a an the of to in on for and or is are was were be been by with as at from that this these those it its
what how why when which who whom does do did can could should would about into than then there their they them
you your i me my we our not no vs versus much many any some all more most also just get
og i på av til for en et ei er var som med det den de at har om fra kan ikke hva hvor hvordan
och på av till för en ett är var som med det den att har om från kan inte vad hur
und der die das ein eine ist war mit für von zu den dem nicht was wie wo
le la les un une des est et en du de pour que qui dans pas
el la los las un una es y en de del para que por con no""".split())

_WORD = re.compile(r"\w+", re.UNICODE)
_CJK = re.compile(r"[぀-ヿ㐀-䶿一-鿿가-힯]")


def stem(w: str) -> str:
    for suf in ("ing", "ies", "es", "s", "ed", "en", "er", "et", "ene", "ar"):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def tokenize(text: str) -> List[str]:
    out: List[str] = []
    for w in _WORD.findall((text or "").lower()):
        if _CJK.search(w):  # no spaces in CJK: use character bigrams
            chars = [c for c in w if not c.isspace()]
            out += ["".join(chars[i:i + 2]) for i in range(max(1, len(chars) - 1))]
        elif w not in STOP and len(w) > 1:
            out.append(stem(w))
    return out


def _chunks(text: str, size: int) -> List[str]:
    paras = [p.strip() for p in re.split(r"\n\s*\n|\n", text) if p.strip()]
    out, cur = [], ""
    for p in paras:
        if len(p) > size * 1.5:
            for s in re.split(r"(?<=[.!?。！？])\s*", p):
                if len(cur) + len(s) > size and cur:
                    out.append(cur)
                    cur = ""
                cur = (cur + " " + s).strip()
            continue
        if len(cur) + len(p) > size and cur:
            out.append(cur)
            cur = ""
        cur = (cur + "\n" + p).strip()
    if cur:
        out.append(cur)
    return out


def select_passages(text: str, terms: Iterable[str], max_chars: int = 3500, window: int = 600) -> str:
    text = text or ""
    if len(text) <= max_chars:
        return text
    term_set = {t for t in terms if t}
    chunks = _chunks(text, window)
    scored = []
    for i, c in enumerate(chunks):
        toks = tokenize(c)
        hits = [t for t in toks if t in term_set]
        distinct = len(set(hits))
        score = distinct * 2 + min(len(hits), 12) * 0.3
        if distinct and re.search(r"\d", c):
            score += 1.0  # numbers next to topic words are often the buried facts
        scored.append((score, i, c))
    keep = {0}
    used = min(len(chunks[0]), 500)
    for score, i, c in sorted(scored, key=lambda x: -x[0]):
        if score <= 0 or used >= max_chars:
            break
        if i in keep:
            continue
        keep.add(i)
        used += len(c)
    parts, prev = [], -2
    for i in sorted(keep):
        c = chunks[i] if i else chunks[0][:500]
        if i != prev + 1 and parts:
            parts.append("[…]")
        parts.append(c)
        prev = i
    return "\n".join(parts)[: max_chars + 600]
