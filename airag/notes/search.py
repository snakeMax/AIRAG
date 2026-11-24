"""Built-in search: lists EVERY match, grouped by note, with every matching section. No AI, no tokens.

Query syntax
    words              all words must appear (any order); the last word also matches as a prefix
    "exact phrase"     the phrase
    -word / -"phrase"  leave out notes with it
    a OR b             either
    tag:status/draft   type:claim   path:Notes/   prop:year>1800   prop:status=done
    linksto:"Note"     linkedfrom:"Note"   has:image   has:link   modified:>2026-11-01   created:<2026-01-01
    regex:pattern      (checked: length-limited, no nested repeats)   case:yes (case-sensitive words)
Every value from the query reaches SQLite as a bound parameter; FTS terms are quoted.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from . import index, store

FILTER_KEYS = {"tag", "type", "path", "prop", "linksto", "linkedfrom", "has", "modified", "created", "regex", "case"}
TOKEN = re.compile(r'(-?)(?:(\w+):)?("([^"]*)"|\S+)')
MAX_RESULTS = 5000
SNIPPET = 160


class QueryError(ValueError):
    pass


@dataclass
class Query:
    words: List[List[str]] = field(default_factory=list)    # OR-groups of AND words/phrases: [[a, b], [c]] = (a AND b) OR c
    exclude: List[str] = field(default_factory=list)
    filters: List[Tuple[str, str, bool]] = field(default_factory=list)   # (key, value, negated)
    case: bool = False
    regex: Optional[re.Pattern] = None


def safe_regex(pattern: str, case: bool) -> re.Pattern:
    if len(pattern) > 200:
        raise QueryError("That regular expression is too long")
    # nested repeats such as (a+)+ or (.*)* can take forever on some text
    if re.search(r"\((?:[^()\\]|\\.)*[+*}](?:[^()\\]|\\.)*\)\s*[+*{?]", pattern) or re.search(r"\\[1-9]", pattern):
        raise QueryError("That regular expression could be very slow (nested repeats or back-references)")
    try:
        return re.compile(pattern, 0 if case else re.I)
    except re.error as e:
        raise QueryError(f"Regular expression: {e}") from None


def parse_query(q: str) -> Query:
    out = Query()
    group: List[str] = []
    for m in TOKEN.finditer(q.strip()[:500]):
        neg, key, raw, quoted = m.group(1), (m.group(2) or "").lower(), m.group(3), m.group(4)
        val = quoted if quoted is not None else raw
        if key in FILTER_KEYS:
            if key == "case":
                out.case = val.lower() in ("yes", "true", "1", "on")
            elif key == "regex":
                out.regex = safe_regex(val, out.case)
            else:
                out.filters.append((key, val, bool(neg)))
            continue
        if key:                       # unknown "word:..." is just text
            val = f"{key}:{val}"
        if not neg and raw == "OR" and quoted is None:
            if group:
                out.words.append(group)
                group = []
            continue
        if neg:
            out.exclude.append(val)
        elif val.strip():
            group.append(val)
    if group:
        out.words.append(group)
    return out


def _fts_term(w: str, prefix: bool) -> str:
    w = w.replace('"', '""')
    return f'"{w}"' + ("*" if prefix and " " not in w and len(w) >= 2 else "")


def _fts_expr(qq: Query) -> str:
    groups = []
    for g in qq.words:
        terms = [_fts_term(w, i == len(g) - 1) for i, w in enumerate(g)]
        groups.append("(" + " AND ".join(terms) + ")")
    expr = " OR ".join(groups)
    for x in qq.exclude:
        expr = f"({expr}) NOT {_fts_term(x, False)}"
    return expr


def _num(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _date(s: str) -> Optional[float]:
    try:
        return time.mktime(time.strptime(s[:10], "%Y-%m-%d"))
    except ValueError:
        return None


def _prop_ok(props: dict, spec: str) -> bool:
    m = re.match(r"^([^=<>!]+?)\s*(>=|<=|!=|=|>|<)\s*(.*)$", spec)
    if not m:
        return spec.strip() in props        # prop:key = has the property
    key, op, want = m.group(1).strip(), m.group(2), m.group(3).strip().strip('"')
    have = props.get(key)
    vals = have if isinstance(have, list) else [have]
    for hv in vals:
        a, b = _num(hv), _num(want)
        if a is not None and b is not None:
            ok = {"=": a == b, "!=": a != b, ">": a > b, "<": a < b, ">=": a >= b, "<=": a <= b}[op]
        else:
            s, w = str(hv if hv is not None else "").lower(), want.lower()
            ok = {"=": s == w, "!=": s != w, ">": s > w, "<": s < w, ">=": s >= w, "<=": s <= w}[op]
        if ok:
            return True
    return False


def _note_ok(c, row, flt: List[Tuple[str, str, bool]]) -> bool:
    props = json.loads(row["props"] or "{}")
    tags = [t.lower() for t in json.loads(row["tags"] or "[]")]
    for key, val, neg in flt:
        v = val.lower()
        if key == "tag":
            ok = any(t == v.lstrip("#") or t.startswith(v.lstrip("#") + "/") for t in tags)
        elif key == "type":
            ok = (row["type"] or "").lower() == v
        elif key == "path":
            ok = row["path"].lower().startswith(v.strip("/")) or ("/" + v.strip("/") + "/") in ("/" + row["path"].lower())
        elif key == "prop":
            ok = _prop_ok(props, val)
        elif key == "linksto":
            ok = any((index.resolve_target(c, l["target"]) or {"path": None})["path"] == (index.resolve_target(c, val) or {"path": "\0"})["path"]
                     for l in c.execute("SELECT target FROM links WHERE src = ? AND kind != 'url'", (row["id"],)))
        elif key == "linkedfrom":
            src = index.resolve_target(c, val)
            ok = bool(src) and any((index.resolve_target(c, l["target"]) or {"id": None})["id"] == row["id"]
                                   for l in c.execute("SELECT target FROM links WHERE src = ? AND kind != 'url'", (src["id"],)))
        elif key == "has":
            if v == "image":
                ok = bool(c.execute("SELECT 1 FROM links WHERE src = ? AND embed = 1 LIMIT 1", (row["id"],)).fetchone())
            elif v == "link":
                ok = bool(c.execute("SELECT 1 FROM links WHERE src = ? LIMIT 1", (row["id"],)).fetchone())
            elif v in ("tag", "tags"):
                ok = bool(tags)
            else:
                ok = v in props
        elif key in ("modified", "created"):
            m = re.match(r"^(>=|<=|>|<|=)?(.*)$", val)
            op, d = m.group(1) or "=", _date(m.group(2))
            t = row["mtime"] if key == "modified" else _num(props.get("created")) or row["mtime"]
            if d is None or t is None:
                ok = False
            else:
                day = d + 86400
                ok = {">": t >= day, ">=": t >= d, "<": t < d, "<=": t < day, "=": d <= t < day}[op]
        else:
            ok = True
        if ok == neg:
            return False
    return True


def _marks(text: str, qq: Query) -> List[Tuple[int, int]]:
    spans = []
    flags = 0 if qq.case else re.I
    for g in qq.words:
        for w in g:
            for m in re.finditer(re.escape(w), text, flags):
                spans.append((m.start(), m.end()))
                if len(spans) > 200:
                    break
    if qq.regex:
        for m in qq.regex.finditer(text):
            if m.end() > m.start():
                spans.append((m.start(), m.end()))
            if len(spans) > 200:
                break
    spans.sort()
    merged: List[Tuple[int, int]] = []
    for s, e in spans:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(e, merged[-1][1]))
        else:
            merged.append((s, e))
    return merged


def _snippet(text: str, marks: List[Tuple[int, int]]) -> dict:
    flat = re.sub(r"\s+", " ", text)
    if not marks:
        return {"text": flat[:SNIPPET], "marks": []}
    # recompute marks on the flattened text around the first hit
    first = marks[0][0]
    pre = re.sub(r"\s+", " ", text[:first])
    start = max(0, len(pre) - SNIPPET // 3)
    piece = flat[start:start + SNIPPET]
    out = []
    shift = len(pre) - first
    for s, e in marks:
        s2, e2 = s + shift - start, e + shift - start
        if 0 <= s2 < len(piece):
            out.append([s2, min(e2, len(piece))])
    return {"text": ("…" if start else "") + piece + ("…" if start + SNIPPET < len(flat) else ""),
            "marks": [[a + (1 if start else 0), b + (1 if start else 0)] for a, b in out]}


def run(settings: dict, v: dict, q: str, sort: str = "relevance", limit: int = MAX_RESULTS) -> dict:
    qq = parse_query(q)
    c = index.connect(settings, v)
    try:
        hits = {}      # note_id -> {"score": float, "sections": {ord: section row}}
        if qq.words:
            if index.has_fts(c):
                rows = c.execute("SELECT note_id, ord, bm25(fts, 8.0, 3.0, 1.0) AS score FROM fts WHERE fts MATCH ? "
                                 "ORDER BY score LIMIT ?", (_fts_expr(qq), limit * 3)).fetchall()
                for r in rows:
                    h = hits.setdefault(r["note_id"], {"score": 0.0, "ords": []})
                    h["score"] += -float(r["score"])
                    h["ords"].append(r["ord"])
            else:
                for g in qq.words:
                    sql, params = "SELECT note_id, ord FROM sections WHERE 1 = 1", []
                    for w in g:
                        sql += " AND text LIKE ? ESCAPE '\\'"
                        params.append("%" + index._like(w) + "%")
                    for r in c.execute(sql + " LIMIT ?", (*params, limit * 3)):
                        h = hits.setdefault(r["note_id"], {"score": 1.0, "ords": []})
                        h["ords"].append(r["ord"])
        else:
            for r in c.execute("SELECT id FROM notes LIMIT ?", (limit,)):
                hits[r["id"]] = {"score": 0.0, "ords": []}
        groups = []
        for nid, h in hits.items():
            row = c.execute("SELECT * FROM notes WHERE id = ?", (nid,)).fetchone()
            if not row or not _note_ok(c, row, qq.filters):
                continue
            secs = c.execute("SELECT * FROM sections WHERE note_id = ? ORDER BY ord", (nid,)).fetchall()
            if qq.exclude and not index.has_fts(c):
                full = " ".join(s["text"] for s in secs).lower()
                if any(x.lower() in full for x in qq.exclude):
                    continue
            if qq.case and qq.words:
                full = " ".join(s["text"] for s in secs) + " " + row["title"]
                if not any(all(w in full for w in g) for g in qq.words):
                    continue
            wanted = set(h["ords"])
            out_secs = []
            for s in secs:
                if qq.regex:
                    if not qq.regex.search(s["text"]):
                        continue
                elif qq.words and s["ord"] not in wanted:
                    continue
                elif not qq.words and s["ord"] != 0:
                    continue
                marks = _marks(s["text"], qq)
                out_secs.append({"ord": s["ord"], "heading": s["heading"], **_snippet(s["text"], marks), "hits": len(marks)})
            if qq.regex and not out_secs:
                continue
            title_hit = qq.words and any(all(w.lower() in row["title"].lower() for w in g) for g in qq.words)
            groups.append({"path": row["path"], "title": row["title"], "type": row["type"], "mtime": row["mtime"],
                           "tags": json.loads(row["tags"] or "[]")[:8], "gist": row["gist"],
                           "score": h["score"] + (5.0 if title_hit else 0.0), "sections": out_secs,
                           "matches": sum(x["hits"] for x in out_secs) or len(out_secs)})
        key = {"relevance": lambda g: -g["score"], "modified": lambda g: -g["mtime"],
               "name": lambda g: g["title"].lower(), "path": lambda g: g["path"].lower()}.get(sort, lambda g: -g["score"])
        groups.sort(key=key)
        groups = groups[:limit]
        return {"query": q, "notes": len(groups), "sections": sum(len(g["sections"]) for g in groups), "groups": groups}
    finally:
        c.close()
