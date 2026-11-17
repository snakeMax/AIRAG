"""Check & repair (Settings -> General).

Checks:
- program files against install-manifest.json written at build time (installed Windows app)
- settings.json can be read
- the library index database passes SQLite's integrity check
- saved searches (history) can be read

Repair fixes data problems in place (broken files are moved aside, never deleted) and,
when program files are missing or damaged, reinstalls the current version from GitHub.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path

from . import __version__, paths

BROKEN_DIR_NAME = "broken"


def _app_files() -> dict:
    if paths.ANDROID:
        return {"checked": False, "reason": "android"}   # Android verifies the APK itself; use Reinstall if needed
    if not paths.FROZEN:
        return {"checked": False, "reason": "source"}
    manifest = paths.APP_DIR / "install-manifest.json"
    if not manifest.exists():
        return {"checked": False, "reason": "no-manifest"}
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"checked": True, "ok": False, "missing": [], "changed": ["install-manifest.json"], "total": 0}
    missing, changed = [], []
    for rel, digest in data.get("files", {}).items():
        f = paths.APP_DIR / rel
        if not f.is_file():
            missing.append(rel)
            continue
        h = hashlib.sha256()
        with open(f, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        if h.hexdigest() != digest:
            changed.append(rel)
    return {"checked": True, "ok": not missing and not changed, "missing": missing[:50], "changed": changed[:50],
            "total": len(data.get("files", {})), "version": data.get("version")}


def _settings() -> dict:
    if not paths.SETTINGS_PATH.exists():
        return {"ok": True}
    try:
        json.loads(paths.SETTINGS_PATH.read_text(encoding="utf-8"))
        return {"ok": True}
    except (OSError, ValueError) as e:
        return {"ok": False, "error": str(e)[:200]}


def _library() -> dict:
    db = paths.LIBRARY_DB
    if not db.exists():
        return {"ok": True}
    try:
        c = sqlite3.connect(str(db), timeout=10)
        try:
            res = c.execute("PRAGMA integrity_check").fetchone()
        finally:
            c.close()
        ok = bool(res and res[0] == "ok")
        return {"ok": ok, "error": "" if ok else str(res[0])[:200]}
    except sqlite3.DatabaseError as e:
        return {"ok": False, "error": str(e)[:200]}


def _history() -> dict:
    bad = []
    for f in paths.HISTORY_DIR.glob("*.json") if paths.HISTORY_DIR.exists() else []:
        try:
            json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            bad.append(f.name)
    return {"ok": not bad, "bad": bad[:50], "bad_count": len(bad)}


def check() -> dict:
    out = {"version": __version__, "platform": paths.PLATFORM, "app": _app_files(), "settings": _settings(),
           "library": _library(), "history": _history(), "checked_at": time.time()}
    out["ok"] = all(out[k].get("ok", True) for k in ("app", "settings", "library", "history"))
    out["needs_reinstall"] = out["app"].get("checked") and not out["app"].get("ok", True)
    return out


def _move_aside(f: Path) -> None:
    dest = f.parent / BROKEN_DIR_NAME
    dest.mkdir(exist_ok=True)
    f.replace(dest / f"{f.stem}-{time.strftime('%Y%m%d-%H%M%S')}{f.suffix}")


def repair_data() -> list:
    """Fix what can be fixed without reinstalling. Returns a list of what was done."""
    done = []
    if not _settings()["ok"]:
        _move_aside(paths.SETTINGS_PATH)
        done.append("settings")      # defaults are used from now on; the old file is kept in 'broken'
    if not _library()["ok"]:
        from .library import LIBRARY
        for suffix in ("", "-wal", "-shm"):
            f = Path(str(paths.LIBRARY_DB) + suffix)
            if f.exists():
                _move_aside(f)
        LIBRARY.fts = True
        done.append("library")       # the index is rebuilt on the next library search or sync
    hist = _history()
    for name in hist.get("bad", []):
        _move_aside(paths.HISTORY_DIR / name)
    if hist.get("bad_count"):
        done.append("history")
    return done


async def repair(job, quit_app) -> dict:
    job.message = "Checking"
    report = check()
    done = repair_data()
    if report.get("needs_reinstall"):
        from . import updater
        job.message = "Reinstalling AIRAG"
        await updater.download_and_install(job, quit_app, reinstall=True)
        done.append("reinstall")
    return {"fixed": done, "report": check()}
