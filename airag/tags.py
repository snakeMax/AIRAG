"""Tags: short labels you give saved articles and files ("cars", "sales 2026"). Typed by you; the optional
"Suggest tags" button asks the AI for a few (tokens only when pressed). Saved in the Markdown file's
properties (`tags: [...]`, the way Obsidian reads them) and in the AIRAG copy. Library searches read files
whose tags match the question first.
"""
from __future__ import annotations

import json
import re
from typing import Iterable, List

MAX_TAGS = 12
MAX_LEN = 40
DEFAULT = "airag"                      # every article saved by AIRAG carries this one
_OK = re.compile(r"[^\w\- /]+", re.UNICODE)


def clean_one(t) -> str:
    t = _OK.sub("", str(t or "").strip().lstrip("#")).strip(" -/")
    return re.sub(r"\s+", " ", t)[:MAX_LEN].strip().lower()


def clean(tags: Iterable) -> List[str]:
    out: List[str] = []
    for t in tags or []:
        c = clean_one(t)
        if c and c not in out:
            out.append(c)
        if len(out) >= MAX_TAGS:
            break
    return out


def yaml_list(tags: Iterable[str]) -> str:
    """For the Markdown properties: [airag, "sales 2026"]."""
    items = clean([DEFAULT, *tags])
    return "[" + ", ".join(t if re.fullmatch(r"[\w\-/]+", t) else json.dumps(t, ensure_ascii=False) for t in items) + "]"


def from_front_matter(text: str) -> List[str]:
    """Tags from a Markdown file's properties block (inline list, YAML list or comma separated)."""
    if not text.startswith("---"):
        return []
    end = text.find("\n---", 3)
    if end < 0:
        return []
    block = text[3:end]
    m = re.search(r"^tags[ \t]*:[ \t]*(.*)$", block, re.M)
    if not m:
        return []
    v = m.group(1).strip()
    if v.startswith("["):
        items = [x.strip().strip("'\"") for x in v.strip("[]").split(",")]
    elif v:
        items = [x.strip().strip("'\"") for x in v.split(",")]
    else:
        items = re.findall(r"^[ \t]*-[ \t]*(.+?)[ \t]*$", block[m.end():].split("\n\n")[0], re.M)
        items = [x.strip("'\"") for x in items]
    return clean(items)


def matches(tags: Iterable[str], question: str) -> bool:
    """Does any tag appear in the question (whole words)?"""
    q = " " + re.sub(r"[^\w]+", " ", question.lower()) + " "
    return any(t != DEFAULT and (" " + re.sub(r"[^\w]+", " ", t) + " ") in q for t in tags)


# ---------------------------------------------------------------- Suggest tags (AI)
PROMPT = """Suggest 3 to 6 short tags for this article, to help find it again later. Tags are lowercase,
one to three words each, about the topic (people, places, subjects, kind of data), not about style.
Reply with only a JSON list of strings, for example ["electric cars", "norway", "sales data"]."""


async def suggest(settings: dict, rec: dict) -> List[str]:
    from .guard import Fence
    from .llm import get_llm
    from . import prompts
    fence = Fence()
    text = (rec.get("article") or "")[:6000]
    title = rec.get("title") or rec.get("query") or ""
    out = await get_llm(settings).complete(PROMPT + "\n" + prompts.UNTRUSTED + "\n" + fence.rule(),
                                           f"Title: {title}\n\nARTICLE:\n" + fence.wrap(text), max_tokens=120)
    m = re.search(r"\[.*?\]", out or "", re.S)
    try:
        items = json.loads(m.group(0)) if m else []
    except ValueError:
        items = re.findall(r'"([^"]+)"', m.group(0)) if m else []
    have = set(clean(rec.get("tags") or []))
    return [t for t in clean(items) if t not in have and t != DEFAULT][:6]
