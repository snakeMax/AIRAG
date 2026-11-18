"""Saved research runs (data/history/<id>.json)."""
from __future__ import annotations

import json
import re
from typing import List, Optional

from .paths import HISTORY_DIR

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
    cur = [x for x in pins() if x != rid]
    if pinned:
        cur.insert(0, rid)
    PINS.parent.mkdir(parents=True, exist_ok=True)
    PINS.write_text(json.dumps(cur), encoding="utf-8")
    return pinned


def save(record: dict, limit: int = 300) -> None:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    (HISTORY_DIR / f"{record['id']}.json").write_text(json.dumps(record, ensure_ascii=False, separators=(",", ":")),
                                                       encoding="utf-8")
    prune(limit)


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
