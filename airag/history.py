"""Saved research runs (data/history/<id>.json)."""
from __future__ import annotations

import json
import re
import threading
from typing import Callable, List, Optional, Union

from .paths import HISTORY_DIR, atomic_write_text

# one lock per record (from a fixed pool, so it never grows): a change made by one feature (a follow-up, a
# rewrite, an explainer, "locate more sources") can't overwrite a change another feature made at the same time
_LOCKS = [threading.RLock() for _ in range(64)]
_PINS_LOCK = threading.Lock()


def _lock(rid: str) -> threading.RLock:
    return _LOCKS[hash(rid) % len(_LOCKS)]


def _limit(limit: Optional[int]) -> int:
    """The reader's History limit from Settings (never the built-in default when they chose a bigger one)."""
    if limit is not None:
        return int(limit)
    try:
        from . import config
        return int(config.load()["app"].get("history_limit", 300))
    except Exception:
        return 300

_ID = re.compile(r"^[\w\-]+$", re.UNICODE)
PINS = HISTORY_DIR.parent / "pins.json"     # pinned searches: shown first on Home, never pruned


def pins() -> List[str]:
    try:
        return [x for x in json.loads(PINS.read_text(encoding="utf-8")) if isinstance(x, str)]
    except (OSError, ValueError, TypeError):
        return []


def set_pin(rid: str, pinned: bool) -> bool:
    if not _ID.match(rid or "") or not (HISTORY_DIR / f"{rid}.json").exists():
        raise KeyError(rid)
    with _PINS_LOCK:
        cur = [x for x in pins() if x != rid]
        if pinned:
            cur.insert(0, rid)
        atomic_write_text(PINS, json.dumps(cur))
    return pinned


def _write(record: dict) -> None:
    if not _ID.match(str(record.get("id") or "")):
        raise ValueError("bad id")
    data = {k: v for k, v in record.items() if k != "pinned"}     # pinned lives in pins.json only
    atomic_write_text(HISTORY_DIR / f"{record['id']}.json", json.dumps(data, ensure_ascii=False, separators=(",", ":")))


def save(record: dict, limit: Optional[int] = None) -> None:
    """Saves a whole record (a new search, or one that replaces the old one on purpose)."""
    with _lock(record["id"]):
        _write(record)
    prune(_limit(limit))


def update(rid: str, change: Union[dict, Callable[[dict], None]], limit: Optional[int] = None) -> Optional[dict]:
    """Changes only some fields of a saved record, on the copy that's on disk right now (so changes other
    features made in the meantime are kept). `change` is a dict of fields, or a function that edits the record.
    Returns the saved record, or None if it no longer exists (e.g. deleted while an explainer was being made)."""
    with _lock(rid):
        cur = get(rid)
        if cur is None:
            return None
        if callable(change):
            change(cur)
        else:
            cur.update(change)
        _write(cur)
    prune(_limit(limit))
    return cur


def prune(limit: int) -> int:
    """Keep only the newest `limit` saved searches."""
    keep = set(pins())
    files = [f for f in sorted(HISTORY_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)
             if f.stem not in keep or limit == 0]
    n = 0
    for f in files[max(1, limit):]:
        try:
            f.unlink()
            n += 1
        except OSError:
            pass
    return n


def clear() -> int:
    return prune(0) + _unlink_all()


def _unlink_all() -> int:
    n = 0
    for f in HISTORY_DIR.glob("*.json"):
        try:
            f.unlink()
            n += 1
        except OSError:
            pass
    return n


def get(rid: str) -> Optional[dict]:
    if not _ID.match(rid or ""):
        return None
    p = HISTORY_DIR / f"{rid}.json"
    try:
        r = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if rid in pins():
        r["pinned"] = True
    return r


def delete(rid: str) -> bool:
    if not _ID.match(rid or ""):
        return False
    p = HISTORY_DIR / f"{rid}.json"
    if p.exists():
        p.unlink()
        return True
    return False


def listing(limit: int = 200) -> List[dict]:
    if not HISTORY_DIR.exists():
        return []
    out = []
    pinned = set(pins())
    for p in sorted(HISTORY_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:limit]:
        try:
            r = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        out.append({"id": r.get("id"), "query": r.get("query"), "outcome": r.get("outcome"),
                    "created": r.get("created"), "title": r.get("title") or r.get("query"),
                    "pinned": r.get("id") in pinned})
    return out
