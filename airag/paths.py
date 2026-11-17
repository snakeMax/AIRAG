"""Where AIRAG keeps its files.

    CONFIG_DIR  %APPDATA%\\AIRAG        settings.json, history/          small, roams with the user
    LOCAL_DIR   %LOCALAPPDATA%\\AIRAG   library.db, browsers/, logs/,    large / machine specific
                                       updates/, webview/

Overrides: env AIRAG_DATA_DIR=<dir>, or a file named `portable.txt` next to
AIRAG.exe (keeps everything in <app>/data - for USB-stick installs).
Both the installed app and `python -m airag` from source use the same folders,
so settings and history carry over between them and across updates.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

APP_NAME = "AIRAG"
FROZEN = bool(getattr(sys, "frozen", False))                # running as the packaged .exe
SOURCE_ROOT = Path(__file__).resolve().parent.parent         # repo root when running from source
BUNDLE_ROOT = Path(getattr(sys, "_MEIPASS", SOURCE_ROOT))    # where web/ and assets/ live
WEB_DIR = BUNDLE_ROOT / "web"
ASSETS_DIR = BUNDLE_ROOT / "assets"
PACKAGE_DATA = Path(__file__).resolve().parent / "data"
APP_DIR = Path(sys.executable).resolve().parent if FROZEN else SOURCE_ROOT


def is_portable() -> bool:
    return (APP_DIR / "portable.txt").exists() or os.environ.get("AIRAG_PORTABLE") == "1"


def _dirs():
    env = os.environ.get("AIRAG_DATA_DIR")
    if env:
        p = Path(env).expanduser()
        return p, p / "local"
    if is_portable():
        p = APP_DIR / "data"
        return p, p / "local"
    home = Path.home()
    if sys.platform == "win32":
        roam = Path(os.environ.get("APPDATA") or home / "AppData" / "Roaming") / APP_NAME
        local = Path(os.environ.get("LOCALAPPDATA") or home / "AppData" / "Local") / APP_NAME
    elif sys.platform == "darwin":
        roam = home / "Library" / "Application Support" / APP_NAME
        local = home / "Library" / "Caches" / APP_NAME
    else:
        roam = Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config") / "airag"
        local = Path(os.environ.get("XDG_DATA_HOME") or home / ".local" / "share") / "airag"
    return roam, local


CONFIG_DIR, LOCAL_DIR = _dirs()
SETTINGS_PATH = CONFIG_DIR / "settings.json"
HISTORY_DIR = CONFIG_DIR / "history"
PENDING_MODE_FILE = CONFIG_DIR / "pending_ui_mode.txt"   # written by the installer
LOG_DIR = LOCAL_DIR / "logs"
BROWSERS_DIR = LOCAL_DIR / "browsers"                   # Playwright's Chromium
LIBRARY_DB = LOCAL_DIR / "library.db"
UPDATES_DIR = LOCAL_DIR / "updates"
RUNTIME_FILE = LOCAL_DIR / "runtime.json"               # pid/port of the running instance
WEBVIEW_DIR = LOCAL_DIR / "webview"

# Playwright must know where its browsers live before it is imported anywhere.
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(BROWSERS_DIR))


def ensure_dirs() -> None:
    for d in (CONFIG_DIR, HISTORY_DIR, LOCAL_DIR, LOG_DIR, UPDATES_DIR):
        d.mkdir(parents=True, exist_ok=True)


def migrate_legacy() -> bool:
    """v0.1 stored data in <source folder>/data. Copy it once into the new location."""
    legacy = SOURCE_ROOT / "data"
    try:
        if SETTINGS_PATH.exists() or not (legacy / "settings.json").exists():
            return False
        if legacy.resolve() == CONFIG_DIR.resolve():
            return False
        ensure_dirs()
        shutil.copy2(legacy / "settings.json", SETTINGS_PATH)
        if (legacy / "history").is_dir():
            for f in (legacy / "history").glob("*.json"):
                if not (HISTORY_DIR / f.name).exists():
                    shutil.copy2(f, HISTORY_DIR / f.name)
        return True
    except OSError:
        return False


def dir_size(path: Path) -> int:
    total = 0
    try:
        for p in path.rglob("*"):
            try:
                if p.is_file():
                    total += p.stat().st_size
            except OSError:
                pass
    except OSError:
        pass
    return total
