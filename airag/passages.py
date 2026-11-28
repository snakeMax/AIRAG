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


# ---------------------------------------------------------------- long pages, section by section
# Pages read as Markdown (the web reader and the Wikipedia API keep headings) are split into sections. Reference
# lists, link lists and the like are skipped; the rest is scored by the search's key words (headings count
# extra) and the best sections fill the per-page budget. A very long section is itself trimmed to its best
# passages. The AI only ever sees this excerpt, so a 300-page document costs the same as a short page.
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$", re.M)
SKIP_SECTIONS = {
    # en
    "references", "external links", "see also", "notes", "further reading", "bibliography", "sources", "citations",
    "footnotes", "works cited", "notes and references", "references and notes", "literature", "gallery", "navigation menu",
    # nb / da / sv
    "referanser", "kilder", "eksterne lenker", "se også", "litteratur", "noter", "fotnoter", "henvisninger",
    "eksterne henvisninger", "referenser", "källor", "externa länkar", "se även", "vidare läsning",
    # de / fr / es
    "einzelnachweise", "weblinks", "siehe auch", "quellen", "anmerkungen", "références", "liens externes", "voir aussi",
    "bibliographie", "notes et références", "referencias", "enlaces externos", "véase también", "bibliografía", "notas",
    # ja / zh
    "脚注", "参考文献", "外部リンク", "関連項目", "出典", "注釈", "参考资料", "外部链接", "参见", "参考文献", "注释",
}


def split_sections(text: str) -> List[dict]:
    """[{heading, level, body}] in page order; the part before the first heading is the lead (heading "")."""
    out: List[dict] = []
    marks = list(_HEADING.finditer(text or ""))
    if not marks:
        return [{"heading": "", "level": 0, "body": (text or "").strip()}]
    lead = text[:marks[0].start()].strip()
    if lead:
        out.append({"heading": "", "level": 0, "body": lead})
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        out.append({"heading": m.group(2).strip().strip("*_ "), "level": len(m.group(1)), "body": text[m.end():end].strip()})
    return out


def _skip(heading: str) -> bool:
    return heading.lower().strip(" :.") in SKIP_SECTIONS


def section_score(sec: dict, terms: set) -> float:
    head = set(tokenize(sec["heading"]))
    toks = tokenize(sec["body"][:20000])
    hits = [t for t in toks if t in terms]
    distinct = len(set(hits))
    s = len(head & terms) * 3 + distinct * 2 + min(len(hits), 20) * 0.25
    if distinct and re.search(r"\d", sec["body"][:20000]):
        s += 1.0
    return s


def select_sections(text: str, terms: Iterable[str], max_chars: int = 3500, pick: List[str] = None) -> tuple:
    """(excerpt, info) for a page. info: chars, sections (counted, without skipped ones), read, skipped, best
    (the best section's score: low means the key words barely appear). `pick`: headings chosen by the AI
    for pages where the key words don't match; they go first."""
    text = text or ""
    term_set = {t for t in terms if t}
    secs = split_sections(text)
    info = {"chars": len(text), "sections": 0, "read": 0, "skipped": 0, "best": 0.0}
    if len(secs) <= 1 or len(text) <= max_chars:
        if len(secs) > 1:
            info["sections"] = info["read"] = sum(1 for s in secs if not _skip(s["heading"]))
        return select_passages(text, term_set, max_chars), info
    keep = [s for s in secs if not _skip(s["heading"]) and s["body"]]
    info["skipped"] = len(secs) - len(keep)
    info["sections"] = len(keep)
    for i, s in enumerate(keep):
        s["i"] = i
        s["score"] = section_score(s, term_set)
    info["best"] = max((s["score"] for s in keep), default=0.0)
    chosen: List[dict] = []
    used = 0
    lead = keep[0] if keep and keep[0]["heading"] == "" else None
    if lead:                                                     # the lead usually sums the page up
        lead = dict(lead, body=lead["body"][:700])
        chosen.append(lead)
        used += len(lead["body"])
    wanted = {p.lower() for p in (pick or [])}
    order = sorted((s for s in keep if s is not keep[0] or not lead),
                   key=lambda s: (s["heading"].lower() not in wanted, -s["score"]))
    for s in order:
        if used >= max_chars or (s["score"] <= 0 and s["heading"].lower() not in wanted):
            break
        room = max_chars - used
        body = s["body"] if len(s["body"]) <= room else select_passages(s["body"], term_set, max(500, room - 100))
        chosen.append(dict(s, body=body))
        used += len(body) + len(s["heading"]) + 4
    chosen.sort(key=lambda s: s.get("i", -1))
    info["read"] = len(chosen)
    parts = []
    for s in chosen:
        parts.append((f"## {s['heading']}\n" if s["heading"] else "") + s["body"])
    return "\n[…]\n".join(parts)[: max_chars + 800], info


def outline(text: str, max_sections: int = 60) -> List[tuple]:
    """[(heading, first words)] for an AI to choose from when the key words don't match."""
    out = []
    for s in split_sections(text):
        if not s["heading"] or _skip(s["heading"]):
            continue
        out.append((s["heading"], re.sub(r"\s+", " ", s["body"][:110]).strip()))
        if len(out) >= max_sections:
            break
    return out
