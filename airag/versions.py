"""Version history of an article: every generation, regeneration, rewrite, added answer or extension.

Kept in its own small file per article (History/versions/<id>.json), so History lists stay fast. The list only
ever grows (the oldest drop off after MAX); Undo and Restore move the "current" marker and put that version's
text back in the article, without deleting anything. A new change after an Undo is added at the end.
"""
from __future__ import annotations

import datetime as dt
import json
import threading
from typing import List, Optional

from .paths import HISTORY_DIR, atomic_write_text

MAX = 20
DIR = HISTORY_DIR / "versions"
_lock = threading.RLock()


def _path(rid: str):
    from .history import _ID
    if not _ID.match(rid or ""):
        raise ValueError("bad id")
    return DIR / f"{rid}.json"


def _load(rid: str) -> dict:
    try:
        d = json.loads(_path(rid).read_text(encoding="utf-8"))
        if isinstance(d, dict) and isinstance(d.get("items"), list):
            return d
    except (OSError, ValueError):
        pass
    return {"items": [], "pos": 0}


def _save(rid: str, d: dict) -> None:
    atomic_write_text(_path(rid), json.dumps(d, ensure_ascii=False, separators=(",", ":")))


def _now() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def note_change(rec: dict, old_article: str, kind: str, note: str = "", old_sources: Optional[list] = None) -> None:
    """Call after a feature changed rec["article"] (inside history.update). The first time, the text from
    before the change becomes version 1."""
    rid = rec.get("id") or ""
    if not rid or (rec.get("article") or "") == (old_article or ""):
        return
    with _lock:
        d = _load(rid)
        if not d["items"]:
            d["items"].append({"n": 1, "at": rec.get("created") or _now(), "kind": "first", "note": "",
                               "article": old_article or "", "sources": old_sources or rec.get("article_sources") or []})
        n = d["items"][-1]["n"] + 1
        d["items"].append({"n": n, "at": _now(), "kind": kind, "note": (note or "")[:200],
                           "article": rec.get("article") or "", "sources": rec.get("article_sources") or []})
        d["items"] = d["items"][-MAX:]
        d["pos"] = n
        _save(rid, d)


def listing(rid: str) -> dict:
    d = _load(rid)
    items = [{"n": v["n"], "at": v["at"], "kind": v["kind"], "note": v.get("note", ""),
              "words": len((v.get("article") or "").split())} for v in reversed(d["items"])]
    return {"items": items, "pos": d.get("pos") or (d["items"][-1]["n"] if d["items"] else 0)}


def get(rid: str, n: int) -> Optional[dict]:
    return next((v for v in _load(rid)["items"] if v["n"] == n), None)


def _go_to(rid: str, n: int) -> Optional[dict]:
    """Puts version n's text back in the article. Locks are always taken History first, then versions (as in
    note_change, which runs inside history.update), so two changes at once can't wait on each other."""
    from . import history
    found = []

    def put(rec: dict) -> None:
        with _lock:
            d = _load(rid)
            v = next((x for x in d["items"] if x["n"] == n), None)
            if v is None:
                return
            rec["article"] = v["article"]
            if v.get("sources"):
                rec["article_sources"] = v["sources"]
            d["pos"] = n
            _save(rid, d)
            found.append(n)
    rec = history.update(rid, put)
    return rec if rec is not None and found else None


def restore(rid: str, n: int) -> Optional[dict]:
    return _go_to(rid, n)


def undo(rid: str) -> Optional[dict]:
    """Back one step from the current version."""
    d = _load(rid)
    ns = [v["n"] for v in d["items"]]
    pos = d.get("pos") or (ns[-1] if ns else 0)
    earlier = [n for n in ns if n < pos]
    return _go_to(rid, earlier[-1]) if earlier else None


def forget(rid: str) -> None:
    """The article left History: its versions go too."""
    try:
        _path(rid).unlink()
    except (OSError, ValueError):
        pass


def forget_all() -> None:
    for f in DIR.glob("*.json") if DIR.exists() else []:
        try:
            f.unlink()
        except OSError:
            pass
