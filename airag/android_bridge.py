"""Glue between the Android app (Kotlin, android/) and the Python core.

The Kotlin side calls start() when the app opens and stop() when it closes;
Python calls back into Kotlin (io.github.snakemax.airag.Bridge) for things only
Android can do: the folder picker, opening files and installing app updates.
Only imported on Android.
"""
from __future__ import annotations

import os
from typing import Optional

_server = None


def _bridge():
    from java import jclass  # provided by Chaquopy
    return jclass("io.github.snakemax.airag.Bridge")


def pick_folder() -> Optional[str]:
    path = _bridge().pickFolder()  # blocks until the user picks (or cancels)
    path = str(path) if path else ""
    if path == "!permission":
        raise RuntimeError("Allow AIRAG to access your files (the settings page just opened), then pick the folder again.")
    if path == "!unsupported":
        raise RuntimeError("That location can't be read as a folder. Pick a folder on the phone's storage or SD card.")
    return path or None


def import_files(dest_dir: str, move: bool) -> list:
    """Let the user pick files and copy (or move) them into dest_dir. Returns [{path, moved}]."""
    import json
    raw = _bridge().importFiles(str(dest_dir), bool(move))   # blocks until the user picks (or cancels)
    return json.loads(str(raw)) if raw else []


def open_path(path: str, reveal: bool = False) -> None:
    _bridge().openFile(str(path))


def render_page(url: str, timeout_s: int = 20) -> str:
    """Load a page in a hidden WebView and return its HTML after scripts ran ("" on failure)."""
    html = _bridge().renderPage(str(url), int(timeout_s * 1000))
    return str(html) if html else ""


def device_info() -> dict:
    import json
    return json.loads(str(_bridge().deviceInfo()))


def clear_web_cache() -> None:
    _bridge().clearWebCache()


def install_apk(path: str) -> str:
    """'ok', or 'permission' when Android first needs the user to allow installing apps."""
    return str(_bridge().installApk(str(path)))


# ------------------------------------------------------------ background jobs
_notified: set = set()


def _jobs_changed() -> None:
    """Runs on every job start/finish: keeps the foreground service (and its notification) in step,
    and posts a notification for each job that finished or failed."""
    from . import runs
    items = runs.active()
    running = [j for j in items if j["status"] == "running"] or items

    def line(j: dict) -> str:
        what = {"explainer": "Explainer", "more": "More sources"}.get(j["kind"], "Search")
        state = "running" if j["status"] == "running" else f"queued ({j['position']} ahead)"
        return f"{what} {state}: {j['query'][:60]}"
    title = ""
    if running:
        j = running[0]
        title = {"explainer": "Building explainer: ", "more": "Finding more sources: "}.get(j["kind"], "Researching: ") + j["query"][:80]
    b = _bridge()
    # the expanded notification lists every job, running or waiting
    b.jobsChanged(len(items), title, "\n".join(line(j) for j in items[:8]))
    for j in runs.recent():
        if j["id"] in _notified or j["status"] == "cancelled":
            continue
        _notified.add(j["id"])
        if len(_notified) > 500:         # only recent jobs matter; don't grow for ever in a long-running app
            for old in list(_notified)[:250]:
                _notified.discard(old)
        explainer = j["kind"] == "explainer"
        hashpart = f"#/view/{j['ref']}" + ("?explainer" if explainer else "")
        b.jobDone(j["query"][:80], j["status"] + ("|explainer" if explainer else ""), hashpart,
                  (j.get("message") or "")[:200])


def cancel_all() -> None:
    """The notification's Cancel button."""
    from . import runs
    runs.cancel_all_threadsafe()


def start(data_dir: str, time_zone: str = "") -> int:
    """Start the local server; returns the port the WebView should load.
    time_zone is the phone's zone (e.g. Europe/Oslo): Python doesn't pick it up by itself on Android."""
    global _server
    os.environ["AIRAG_DATA_DIR"] = data_dir
    os.environ["AIRAG_PLATFORM"] = "android"
    if time_zone:
        os.environ["TZ"] = time_zone
        import time
        if hasattr(time, "tzset"):
            time.tzset()
    if _server is not None and _server.is_alive():
        from . import appctl
        return appctl.port
    from . import appctl, config, desktop, paths
    desktop.setup_logging()
    paths.ensure_dirs()
    from . import runs
    runs.on_change(_jobs_changed)
    port = desktop.choose_port(int(config.load()["app"].get("port") or 0) or 18765)  # stable port keeps WebView storage
    _server = desktop.ServerThread(port)
    _server.start()
    _server.wait_ready(90)
    appctl.mode, appctl.port, appctl.url = "android", port, f"http://127.0.0.1:{port}/"
    appctl.pick_folder_hook = pick_folder
    return port


def stop() -> None:
    global _server
    if _server is not None:
        _server.stop()
        _server = None
