"""Per-vault index (.airag/index.db): notes, sections, links, tags, properties and full-text search.

Built-in indexing costs no AI tokens: titles, headings, properties, tags, links, first sentences and every
section's text. It updates incrementally (only notes whose size/mtime/hash changed) and drops deleted notes.
All SQL text is fixed here; every value is a bound parameter. If the phone's SQLite has no FTS5, searches
fall back to LIKE over the same sections.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

from . import parser, store

VERSION = 1
_locks: Dict[str, threading.Lock] = {}

SCHEMA = [
    "CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT)",
    "CREATE TABLE IF NOT EXISTS notes (id INTEGER PRIMARY KEY, path TEXT UNIQUE, name TEXT, title TEXT, "
    "mtime REAL, size INTEGER, hash TEXT, props TEXT, type TEXT, tags TEXT, gist TEXT, aliases TEXT, indexed REAL)",
    "CREATE TABLE IF NOT EXISTS sections (note_id INTEGER, ord INTEGER, heading TEXT, level INTEGER, start INTEGER, "
    "end_ INTEGER, text TEXT, hash TEXT, PRIMARY KEY (note_id, ord))",
    "CREATE TABLE IF NOT EXISTS links (src INTEGER, target TEXT, heading TEXT, alias TEXT, embed INTEGER, kind TEXT)",
    "CREATE INDEX IF NOT EXISTS links_src ON links (src)",
    "CREATE INDEX IF NOT EXISTS links_target ON links (target COLLATE NOCASE)",
    "CREATE INDEX IF NOT EXISTS notes_name ON notes (name COLLATE NOCASE)",
]
FTS = ("CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5(title, heading, body, note_id UNINDEXED, ord UNINDEXED, "
       "tokenize = 'unicode61 remove_diacritics 2')")


def _db_path(settings: dict, v: dict) -> Path:
    d = store.private_dir(settings, v)
    d.mkdir(parents=True, exist_ok=True)
    return d / "index.db"


def connect(settings: dict, v: dict) -> sqlite3.Connection:
    c = sqlite3.connect(str(_db_path(settings, v)), timeout=10)
    c.row_factory = sqlite3.Row
    for q in SCHEMA:
        c.execute(q)
    try:
        c.execute(FTS)
        has = "1"
    except sqlite3.OperationalError:
        has = "0"
    c.execute("INSERT OR REPLACE INTO meta (k, v) VALUES ('fts', ?)", (has,))
    c.commit()
    return c


def has_fts(c: sqlite3.Connection) -> bool:
    row = c.execute("SELECT v FROM meta WHERE k = 'fts'").fetchone()
    return bool(row and row[0] == "1")


def _lock_for(v: dict) -> threading.Lock:
    return _locks.setdefault(v["id"], threading.Lock())


def _aliases(props: dict) -> List[str]:
    a = props.get("aliases", props.get("alias"))
    if isinstance(a, list):
        return [str(x) for x in a if x not in (None, "")][:50]
    return [a] if isinstance(a, str) and a else []


def index_note(c: sqlite3.Connection, rel: str, text: str, mtime: float, size: int) -> int:
    name = Path(rel).stem
    n = parser.parse(text, name)
    row = c.execute("SELECT id FROM notes WHERE path = ?", (rel,)).fetchone()
    vals = (rel, name, n.title, mtime, size, n.hash, json.dumps(n.props, ensure_ascii=False, default=str)[:200_000],
            str(n.props.get("type") or ""), json.dumps(n.tags, ensure_ascii=False), n.gist,
            json.dumps(_aliases(n.props), ensure_ascii=False), time.time())
    if row:
        nid = row["id"]
        c.execute("UPDATE notes SET path=?, name=?, title=?, mtime=?, size=?, hash=?, props=?, type=?, tags=?, gist=?, "
                  "aliases=?, indexed=? WHERE id=?", (*vals, nid))
        c.execute("DELETE FROM sections WHERE note_id = ?", (nid,))
        c.execute("DELETE FROM links WHERE src = ?", (nid,))
        if has_fts(c):
            c.execute("DELETE FROM fts WHERE note_id = ?", (nid,))
    else:
        cur = c.execute("INSERT INTO notes (path, name, title, mtime, size, hash, props, type, tags, gist, aliases, indexed) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", vals)
        nid = cur.lastrowid
    fts = has_fts(c)
    for s in n.sections:
        c.execute("INSERT INTO sections (note_id, ord, heading, level, start, end_, text, hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                  (nid, s.ord, s.heading, s.level, s.start, s.end, s.text, s.hash))
        if fts:
            c.execute("INSERT INTO fts (title, heading, body, note_id, ord) VALUES (?, ?, ?, ?, ?)",
                      (n.title if s.ord == 0 else "", s.heading, s.text, nid, s.ord))
    if fts and not n.sections:
        c.execute("INSERT INTO fts (title, heading, body, note_id, ord) VALUES (?, '', '', ?, 0)", (n.title, nid))
    for l in n.links:
        c.execute("INSERT INTO links (src, target, heading, alias, embed, kind) VALUES (?, ?, ?, ?, ?, ?)",
                  (nid, l.target, l.heading, l.alias, int(l.embed), l.kind))
    return nid


def update(settings: dict, v: dict, max_notes: int = 50_000) -> dict:
    """Bring the index up to date with the files. Returns counts."""
    base = store.vault_dir(settings, v)
    if not base.is_dir():
        raise store.NotesError("The vault's folder is missing")
    with _lock_for(v):
        c = connect(settings, v)
        try:
            known = {r["path"]: (r["mtime"], r["size"]) for r in c.execute("SELECT path, mtime, size FROM notes")}
            seen, added, changed = set(), 0, 0
            for item in store.tree(settings, v, limit=max_notes * 2):
                if item["kind"] != "note":
                    continue
                rel = item["path"]
                seen.add(rel)
                old = known.get(rel)
                if old and abs(old[0] - item["mtime"]) < 1e-6 and old[1] == item["size"]:
                    continue
                try:
                    text = store.read_note(settings, v, rel)
                except (OSError, store.NotesError, ValueError):
                    continue
                index_note(c, rel, text, item["mtime"], item["size"])
                if old:
                    changed += 1
                else:
                    added += 1
            gone = [p for p in known if p not in seen]
            for p in gone:
                remove(c, p)
            c.execute("INSERT OR REPLACE INTO meta (k, v) VALUES ('updated', ?)", (str(time.time()),))
            c.commit()
            total = c.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
            return {"notes": total, "added": added, "changed": changed, "removed": len(gone)}
        finally:
            c.close()


def remove(c: sqlite3.Connection, rel: str) -> None:
    row = c.execute("SELECT id FROM notes WHERE path = ?", (rel,)).fetchone()
    if not row:
        return
    nid = row["id"]
    c.execute("DELETE FROM notes WHERE id = ?", (nid,))
    c.execute("DELETE FROM sections WHERE note_id = ?", (nid,))
    c.execute("DELETE FROM links WHERE src = ?", (nid,))
    if has_fts(c):
        c.execute("DELETE FROM fts WHERE note_id = ?", (nid,))


def reindex_one(settings: dict, v: dict, rel: str) -> None:
    """After AIRAG saves a note: update just that note."""
    p = store.vault_dir(settings, v) / rel
    with _lock_for(v):
        c = connect(settings, v)
        try:
            st = p.stat()
            index_note(c, rel, store.read_note(settings, v, rel), st.st_mtime, st.st_size)
            c.commit()
        finally:
            c.close()


# ---------------------------------------------------------------- links
def resolve_target(c: sqlite3.Connection, target: str) -> Optional[sqlite3.Row]:
    """Obsidian-style: a path (with or without .md) or a bare name; aliases count too."""
    t = target.strip()
    if not t:
        return None
    row = c.execute("SELECT * FROM notes WHERE path = ? COLLATE NOCASE OR path = ? COLLATE NOCASE LIMIT 1", (t, t + ".md")).fetchone()
    if row:
        return row
    row = c.execute("SELECT * FROM notes WHERE name = ? COLLATE NOCASE ORDER BY length(path) LIMIT 1", (t.split("/")[-1],)).fetchone()
    if row:
        return row
    for r in c.execute("SELECT * FROM notes WHERE aliases LIKE ? ESCAPE '\\'", ("%" + _like(t) + "%",)):
        if t.lower() in (a.lower() for a in json.loads(r["aliases"] or "[]")):
            return r
    return None


def _like(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def backlinks(settings: dict, v: dict, rel: str) -> dict:
    c = connect(settings, v)
    try:
        me = c.execute("SELECT * FROM notes WHERE path = ?", (rel,)).fetchone()
        if not me:
            return {"linked": [], "unlinked": []}
        names = {me["name"].lower(), rel.lower(), rel[:-3].lower() if rel.lower().endswith(".md") else rel.lower()}
        names |= {a.lower() for a in json.loads(me["aliases"] or "[]")}
        linked = []
        for r in c.execute("SELECT DISTINCT n.path, n.title, l.target FROM links l JOIN notes n ON n.id = l.src "
                           "WHERE l.kind != 'url' AND n.id != ?", (me["id"],)):
            if r["target"].lower() in names or r["target"].split("/")[-1].lower() == me["name"].lower():
                if not any(x["path"] == r["path"] for x in linked):
                    linked.append({"path": r["path"], "title": r["title"]})
        unlinked = []
        if has_fts(c) and len(me["title"]) >= 3:
            q = '"' + me["title"].replace('"', '""') + '"'
            for r in c.execute("SELECT DISTINCT n.path, n.title FROM fts JOIN notes n ON n.id = fts.note_id "
                               "WHERE fts MATCH ? AND n.id != ? LIMIT 50", ("body:" + q, me["id"])):
                if not any(x["path"] == r["path"] for x in linked):
                    unlinked.append({"path": r["path"], "title": r["title"]})
        return {"linked": linked, "unlinked": unlinked[:20]}
    finally:
        c.close()


def outgoing(settings: dict, v: dict, rel: str) -> List[dict]:
    c = connect(settings, v)
    try:
        me = c.execute("SELECT id FROM notes WHERE path = ?", (rel,)).fetchone()
        if not me:
            return []
        out = []
        for l in c.execute("SELECT * FROM links WHERE src = ?", (me["id"],)):
            if l["kind"] == "url":
                out.append({"target": l["target"], "kind": "url", "exists": True})
                continue
            hit = resolve_target(c, l["target"])
            out.append({"target": l["target"], "heading": l["heading"], "kind": l["kind"], "embed": bool(l["embed"]),
                        "exists": bool(hit), "path": hit["path"] if hit else None})
        return out
    finally:
        c.close()


def stats(settings: dict, v: dict) -> dict:
    c = connect(settings, v)
    try:
        notes = c.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
        links = c.execute("SELECT COUNT(*) FROM links WHERE kind != 'url'").fetchone()[0]
        linked_to = set()
        broken = 0
        for l in c.execute("SELECT target FROM links WHERE kind != 'url'").fetchall():
            hit = resolve_target(c, l["target"])
            if hit:
                linked_to.add(hit["id"])
            else:
                broken += 1
        with_out = {r[0] for r in c.execute("SELECT DISTINCT src FROM links WHERE kind != 'url'")}
        all_ids = {r[0] for r in c.execute("SELECT id FROM notes")}
        orphans = len(all_ids - linked_to - with_out)
        return {"notes": notes, "links": links, "broken": broken, "orphans": orphans, "fts": has_fts(c)}
    finally:
        c.close()


def all_tags(settings: dict, v: dict) -> List[dict]:
    """Every tag in the vault with how many notes use it (nested tags also count for their parents)."""
    c = connect(settings, v)
    try:
        counts: Dict[str, int] = {}
        shown: Dict[str, str] = {}
        for r in c.execute("SELECT tags FROM notes"):
            seen = set()
            for t in json.loads(r["tags"] or "[]"):
                parts = str(t).split("/")
                for i in range(1, len(parts) + 1):
                    key = "/".join(parts[:i])
                    low = key.lower()
                    if low in seen:
                        continue
                    seen.add(low)
                    counts[low] = counts.get(low, 0) + 1
                    shown.setdefault(low, key)
        return sorted(({"tag": shown[k], "count": n} for k, n in counts.items()), key=lambda x: (-x["count"], x["tag"].lower()))
    finally:
        c.close()
