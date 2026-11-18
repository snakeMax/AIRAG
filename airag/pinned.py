"""Pinned sources: web pages the user wants to keep until they unpin them.

A pinned page's text is stored locally (<data>/pinned/), so it opens instantly from the home page
(as the saved page, or as an AI-written version) and searches can reuse it without fetching it again
when it matches the question.
"""
from __future__ import annotations

import hashlib
import json
import time
from typing import List, Optional

from . import paths

DIR = paths.HISTORY_DIR.parent / "pinned"
INDEX = DIR / "index.json"
MAX_TEXT = 120_000


def _id(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]


def _load() -> List[dict]:
    try:
        data = json.loads(INDEX.read_text(encoding="utf-8"))
        return [x for x in data if isinstance(x, dict) and x.get("id")]
    except (OSError, ValueError):
        return []


def _save(items: List[dict]) -> None:
    DIR.mkdir(parents=True, exist_ok=True)
    tmp = INDEX.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(INDEX)


def listing() -> List[dict]:
    return _load()


def is_pinned(url: str) -> bool:
    return any(x["url"] == url for x in _load())


def add(url: str, title: str, text: str, meta: Optional[dict] = None) -> dict:
    if not url.startswith(("http://", "https://")):
        raise ValueError("Only web pages can be pinned")
    meta = meta or {}
    pid = _id(url)
    DIR.mkdir(parents=True, exist_ok=True)
    (DIR / f"{pid}.md").write_text(text[:MAX_TEXT], encoding="utf-8")
    item = {"id": pid, "url": url, "title": (title or url)[:300], "domain": str(meta.get("domain") or "")[:120],
            "summary": str(meta.get("summary") or "")[:600], "query": str(meta.get("query") or "")[:300],
            "trust": meta.get("trust"), "published": meta.get("published") or meta.get("date"),
            "site_name": meta.get("site_name"), "pinned_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    items = [x for x in _load() if x["id"] != pid]
    items.insert(0, item)
    _save(items)
    return item


def remove(pid: str) -> bool:
    items = _load()
    left = [x for x in items if x["id"] != pid and x["url"] != pid]
    if len(left) == len(items):
        return False
    _save(left)
    for x in items:
        if x not in left:
            try:
                (DIR / f"{x['id']}.md").unlink()
            except OSError:
                pass
    return True


def get(pid: str) -> Optional[dict]:
    for x in _load():
        if x["id"] == pid:
            try:
                text = (DIR / f"{pid}.md").read_text(encoding="utf-8")
            except OSError:
                text = ""
            return {**x, "text": text}
    return None


def matching(terms: List[str], limit: int = 4) -> List[dict]:
    """Pinned pages that share enough words with the question (cheap: no AI, no network)."""
    want = {t.lower() for t in terms if len(t) > 2}
    if not want:
        return []
    scored = []
    for x in _load():
        head = f"{x.get('title', '')} {x.get('summary', '')} {x.get('query', '')}".lower()
        try:
            body = (DIR / f"{x['id']}.md").read_text(encoding="utf-8")
        except OSError:
            body = ""
        low = body[:20000].lower()
        hits = sum(2 for t in want if t in head) + sum(1 for t in want if t in low)
        need = max(2, round(len(want) * 0.6))
        if hits >= need:
            scored.append((hits, x, body))
    scored.sort(key=lambda z: -z[0])
    return [{**x, "text": body} for _, x, body in scored[:limit]]
