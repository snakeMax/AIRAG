"""Parse one Markdown note: properties (front matter), sections per heading, links, embeds, tags and a gist.

Pure Python, no YAML library: the properties block is read with a small safe subset (key: value,
inline lists, "- item" lists, quoted strings, numbers, booleans). Anything else stays a plain string.
Sizes are capped so a huge or hostile file can't stall the indexer.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

MAX_NOTE_CHARS = 2_000_000
MAX_PROPS = 100
MAX_SECTIONS = 2000

LINK = re.compile(r"(!?)\[\[([^\[\]\n|#^]*)(?:#([^\[\]\n|]*))?(?:\|([^\[\]\n]*))?\]\]")
MD_LINK = re.compile(r"(!?)\[([^\]\n]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
TAG = re.compile(r"(?<![\w/&#])#([A-Za-zÀ-￿_][\w\-/À-￿]*)")
HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t#]*$")
FENCE = re.compile(r"^(```|~~~)")
NUMBER = re.compile(r"^-?\d+(\.\d+)?$")


@dataclass
class Link:
    target: str          # note name or path as written (no .md)
    heading: str = ""
    alias: str = ""
    embed: bool = False
    kind: str = "wiki"   # "wiki" | "md" | "url"


@dataclass
class Section:
    ord: int
    heading: str          # "" for the text before the first heading
    level: int
    start: int            # character range in the note body (after the properties block)
    end: int
    text: str
    hash: str = ""


@dataclass
class Note:
    title: str
    props: Dict[str, object] = field(default_factory=dict)
    body: str = ""
    sections: List[Section] = field(default_factory=list)
    links: List[Link] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    gist: str = ""
    hash: str = ""


def _scalar(v: str):
    v = v.strip()
    if not v:
        return ""
    if (v[0] == v[-1]) and v[0] in "\"'" and len(v) >= 2:
        return v[1:-1]
    low = v.lower()
    if low in ("true", "yes"):
        return True
    if low in ("false", "no"):
        return False
    if low in ("null", "~"):
        return None
    if NUMBER.match(v):
        try:
            return float(v) if "." in v else int(v)
        except ValueError:
            return v
    return v


def _inline_list(v: str) -> List[object]:
    inner = v.strip()[1:-1]
    out, buf, quote = [], "", ""
    for ch in inner:
        if quote:
            buf += ch
            if ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
            buf += ch
        elif ch == ",":
            out.append(_scalar(buf))
            buf = ""
        else:
            buf += ch
    if buf.strip():
        out.append(_scalar(buf))
    return out[:200]


def split_front_matter(text: str) -> Tuple[Dict[str, object], str, str]:
    """(properties, body, raw block). A note without a valid block has no properties."""
    if not text.startswith("---"):
        return {}, text, ""
    m = re.match(r"---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(\r?\n|$)", text, re.S)
    if not m:
        return {}, text, ""
    raw = m.group(1)
    props: Dict[str, object] = {}
    key: Optional[str] = None
    for line in raw.splitlines()[:2000]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        item = re.match(r"^[ \t]+-[ \t]*(.*)$", line) or re.match(r"^-[ \t]+(.*)$", line)
        if item and key is not None:
            cur = props.get(key)
            if not isinstance(cur, list):
                cur = [] if cur in ("", None) else [cur]
            if len(cur) < 200:
                cur.append(_scalar(item.group(1)))
            props[key] = cur
            continue
        kv = re.match(r"^([A-Za-z0-9_\-À-￿][\w\-À-￿ ]{0,60})[ \t]*:[ \t]*(.*)$", line)
        if kv and len(props) < MAX_PROPS:
            key = kv.group(1).strip()
            v = kv.group(2).strip()
            props[key] = _inline_list(v) if v.startswith("[") and v.endswith("]") else _scalar(v[:2000])
        # anything else (nested maps, anchors, tags like !!python) is ignored: never evaluated
    return props, text[m.end():], raw


def _strip_code(text: str) -> str:
    """Blank out fenced and inline code so links/tags inside code don't count (keeps offsets)."""
    out, fence = [], None
    for line in text.split("\n"):
        m = FENCE.match(line.lstrip())
        if fence:
            out.append(" " * len(line))
            if m and line.lstrip().startswith(fence):
                fence = None
            continue
        if m:
            fence = m.group(1)
            out.append(" " * len(line))
            continue
        out.append(re.sub(r"`[^`\n]*`", lambda x: " " * len(x.group(0)), line))
    return "\n".join(out)


def sections_of(body: str) -> List[Section]:
    code = _strip_code(body)
    heads = []
    pos = 0
    for line, cline in zip(body.split("\n"), code.split("\n")):
        m = HEADING.match(cline)
        if m and cline.strip():
            heads.append((pos, len(m.group(1)), line.lstrip("#").strip().rstrip("#").strip()))
        pos += len(line) + 1
    out: List[Section] = []
    starts = [(0, 0, "")] + heads if (not heads or heads[0][0] > 0) else heads
    for i, (start, level, title) in enumerate(starts):
        end = starts[i + 1][0] if i + 1 < len(starts) else len(body)
        text = body[start:end]
        if not text.strip() and not title:
            continue
        out.append(Section(len(out), title, level, start, end, text,
                           hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()[:16]))
        if len(out) >= MAX_SECTIONS:
            break
    return out


def links_of(body: str) -> List[Link]:
    code = _strip_code(body)
    out: List[Link] = []
    for m in LINK.finditer(code):
        target = body[m.start(2):m.end(2)].strip()
        if not target and not m.group(3):
            continue
        out.append(Link(target=re.sub(r"\.md$", "", target, flags=re.I), heading=(m.group(3) or "").strip(),
                        alias=(m.group(4) or "").strip(), embed=bool(m.group(1))))
    for m in MD_LINK.finditer(code):
        href = m.group(3)
        if re.match(r"^[a-z][a-z0-9+.\-]*:", href, re.I):
            out.append(Link(target=href, alias=m.group(2), embed=bool(m.group(1)), kind="url"))
        elif not href.startswith("#"):
            from urllib.parse import unquote
            t = unquote(href.split("#")[0])
            out.append(Link(target=re.sub(r"\.md$", "", t, flags=re.I), heading=unquote(href.split("#")[1]) if "#" in href else "",
                            alias=m.group(2), embed=bool(m.group(1)), kind="md"))
        if len(out) > 5000:
            break
    return out


def tags_of(body: str, props: Dict[str, object]) -> List[str]:
    tags = []
    p = props.get("tags", props.get("tag"))
    if isinstance(p, list):
        tags += [str(x) for x in p if x not in (None, "")]
    elif isinstance(p, str) and p:
        tags += [x.strip() for x in re.split(r"[,\s]+", p) if x.strip()]
    tags += TAG.findall(_strip_code(body))
    seen, out = set(), []
    for t in tags:
        t = t.lstrip("#").strip()
        if t and t.lower() not in seen and not t.isdigit():
            seen.add(t.lower())
            out.append(t[:80])
    return out[:200]


def gist_of(body: str, limit: int = 220) -> str:
    """The first real sentence(s): no headings, properties, list markers or code."""
    text = _strip_code(body)
    lines = [l.strip() for l in text.split("\n") if l.strip() and not l.strip().startswith(("#", ">", "|", "---", "![["))]
    s = " ".join(re.sub(r"^([-*+]|\d+\.)\s+", "", l) for l in lines[:6])
    s = LINK.sub(lambda m: m.group(4) or m.group(2), s)
    s = re.sub(r"[*_`~]+", "", s).strip()
    if len(s) <= limit:
        return s
    cut = s[:limit]
    dot = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    return (cut[:dot + 1] if dot > 60 else cut.rsplit(" ", 1)[0] + "…").strip()


def parse(text: str, name: str) -> Note:
    text = text[:MAX_NOTE_CHARS].replace("\r\n", "\n")
    props, body, _ = split_front_matter(text)
    title = str(props.get("title") or "").strip() or name
    return Note(title=title, props=props, body=body, sections=sections_of(body), links=links_of(body),
                tags=tags_of(body, props), gist=gist_of(body),
                hash=hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()[:20])
