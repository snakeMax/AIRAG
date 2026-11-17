"""Export and import settings and search history (Settings -> System -> Backup).

The backup is one JSON file in My library/Backups. API keys and the phone pairing code
are left out unless the user ticks "include API keys". Importing merges: settings from
the file replace the current ones (keys you didn't export stay as they are), and saved
searches are added unless a search with the same id is already there.
"""
from __future__ import annotations

import datetime as dt
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, List, Tuple

from . import __version__, config, history

FORMAT = "airag-backup"


def _secret_paths(settings: dict) -> List[Tuple[str, ...]]:
    found: List[Tuple[str, ...]] = []

    def walk(d: Any, path: Tuple[str, ...]):
        if isinstance(d, dict):
            for k, v in d.items():
                walk(v, path + (k,))
        elif isinstance(d, str) and d.startswith(config.MASK):
            found.append(path)
    walk(config.masked(settings), ())
    found.append(("app", "pclink_code"))
    return found


def _drop(d: dict, path: Tuple[str, ...]) -> None:
    for k in path[:-1]:
        d = d.get(k) if isinstance(d, dict) else None
        if d is None:
            return
    if isinstance(d, dict):
        d.pop(path[-1], None)


def export(dest_dir: Path, include_keys: bool = False) -> Path:
    s = config.load()
    data = deepcopy(s)
    if not include_keys:
        for path in _secret_paths(s):
            _drop(data, path)
    records = []
    for item in history.listing(100000):
        rec = history.get(item["id"])
        if rec:
            records.append(rec)
    out = {"format": FORMAT, "version": __version__, "exported": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
           "includes_keys": include_keys, "settings": data, "history": records}
    dest_dir.mkdir(parents=True, exist_ok=True)
    f = dest_dir / f"AIRAG backup {dt.datetime.now().strftime('%Y-%m-%d %H%M')}.json"
    f.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return f


def import_file(path: Path) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ValueError(f"That file isn't an AIRAG backup ({e}).")
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise ValueError("That file isn't an AIRAG backup.")
    settings_done = False
    if isinstance(data.get("settings"), dict):
        incoming = {k: v for k, v in data["settings"].items() if k in config.SECTIONS}
        config.save(incoming)
        settings_done = True
    added = 0
    limit = int(config.load()["app"].get("history_limit", 300))
    for rec in data.get("history") or []:
        if isinstance(rec, dict) and rec.get("id") and history.get(rec["id"]) is None and history._ID.match(rec["id"]):
            history.save(rec, max(limit, len(data["history"])))
            added += 1
    return {"imported": True, "settings": settings_done, "history": added}
