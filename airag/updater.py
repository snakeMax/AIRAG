"""Update check against GitHub Releases, and self-update for the installed Windows app.

A release is expected to contain an asset named  AIRAG-Setup-<version>.exe  and
(optionally) AIRAG-Setup-<version>.exe.sha256 . The GitHub Actions workflow in
.github/workflows/release.yml produces both when a tag like v0.3.0 is pushed.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import subprocess
import sys
import time
from typing import Optional, Tuple

import httpx

from . import __repo__, __version__
from .paths import ANDROID, FROZEN, LOCAL_DIR, UPDATES_DIR, is_portable

log = logging.getLogger("airag.update")
CACHE = LOCAL_DIR / "update_check.json"
CACHE_SECONDS = 3 * 3600


def parse_version(v: str) -> Tuple[int, ...]:
    nums = re.findall(r"\d+", (v or "").split("-")[0].split("+")[0])
    return tuple(int(n) for n in nums[:4]) or (0,)


def can_self_update() -> bool:
    return ANDROID or (FROZEN and sys.platform == "win32" and not is_portable())


def _wanted(name: str) -> bool:
    n = name.lower()
    if ANDROID:
        return n.startswith("airag") and n.endswith(".apk")
    return n.startswith("airag-setup") and n.endswith(".exe")


def _read_cache() -> Optional[dict]:
    try:
        d = json.loads(CACHE.read_text(encoding="utf-8"))
        if time.time() - d.get("checked", 0) < CACHE_SECONDS and d.get("current") == __version__:
            return d
    except (OSError, ValueError):
        pass
    return None


async def _release(tag: Optional[str] = None) -> dict:
    """A release from GitHub: the latest one, or a specific tag (e.g. v0.3.0)."""
    path = f"tags/{tag}" if tag else "latest"
    async with httpx.AsyncClient(timeout=10, follow_redirects=True) as c:
        r = await c.get(f"https://api.github.com/repos/{__repo__}/releases/{path}",
                        headers={"Accept": "application/vnd.github+json", "User-Agent": f"AIRAG/{__version__}"})
    if r.status_code == 404:
        raise LookupError("No release found" + (f" for {tag}" if tag else ""))
    r.raise_for_status()
    return r.json()


def _assets(rel: dict) -> Tuple[Optional[dict], Optional[str]]:
    setup = sha = None
    for a in rel.get("assets") or []:
        n = a.get("name", "")
        if _wanted(n):
            setup = {"name": n, "url": a.get("browser_download_url"), "size": a.get("size", 0)}
    if setup:
        for a in rel.get("assets") or []:
            if a.get("name") == setup["name"] + ".sha256":
                sha = a.get("browser_download_url")
    return setup, sha


async def check(force: bool = False) -> dict:
    if not force:
        cached = _read_cache()
        if cached:
            return cached
    from . import build_info
    info = {"current": __version__, "channel": build_info()["channel"], "latest": None, "newer": False, "checked": time.time(),
            "can_self_update": can_self_update(), "repo": __repo__}
    try:
        rel = await _release()
    except LookupError:
        info["error"] = "No releases published yet"
        return info
    except Exception as e:
        info["error"] = f"Update check failed: {e}"[:200]
        return info
    latest = str(rel.get("tag_name") or "").lstrip("vV")
    setup, sha = _assets(rel)
    info.update({"latest": latest, "newer": parse_version(latest) > parse_version(__version__),
                 "notes": (rel.get("body") or "")[:5000], "url": rel.get("html_url"),
                 "published": rel.get("published_at"), "asset": setup, "sha256_url": sha})
    try:
        LOCAL_DIR.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(info), encoding="utf-8")
    except OSError:
        pass
    return info


async def download_and_install(job, quit_app, reinstall: bool = False) -> dict:
    """Download the new installer, verify it, start it silently and quit AIRAG.
    The installer closes/replaces the app and starts the new version afterwards.
    reinstall=True installs the version you already have again (repair)."""
    if reinstall:
        try:
            rel = await _release(f"v{__version__}")
        except LookupError:
            raise RuntimeError(f"AIRAG {__version__} isn't on GitHub, so it can't be reinstalled automatically.")
        setup, sha = _assets(rel)
        info = {"latest": __version__, "asset": setup, "sha256_url": sha, "newer": True}
    else:
        info = await check(force=True)
    if not info.get("newer"):
        raise RuntimeError("You already have the latest version.")
    if not can_self_update():
        raise RuntimeError("Automatic updates only work for the installed app. Download the new version from GitHub.")
    asset = info.get("asset")
    if not asset:
        raise RuntimeError("That release has no installer for this device attached.")
    UPDATES_DIR.mkdir(parents=True, exist_ok=True)
    for old in list(UPDATES_DIR.glob("AIRAG-Setup-*.exe")) + list(UPDATES_DIR.glob("AIRAG-*.apk")):
        try:
            old.unlink()
        except OSError:
            pass
    dest = UPDATES_DIR / asset["name"]
    job.message, job.progress = f"Downloading AIRAG {info['latest']}", 0.0
    h = hashlib.sha256()
    async with httpx.AsyncClient(timeout=httpx.Timeout(60, connect=15), follow_redirects=True) as c:
        async with c.stream("GET", asset["url"]) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length") or asset.get("size") or 0)
            done = 0
            with open(dest, "wb") as f:
                async for chunk in r.aiter_bytes(1 << 16):
                    if job.cancelled:
                        raise RuntimeError("Cancelled")
                    f.write(chunk)
                    h.update(chunk)
                    done += len(chunk)
                    if total:
                        job.progress = done / total
        if info.get("sha256_url"):
            job.message = "Verifying download"
            r = await c.get(info["sha256_url"])
            expected = (r.text.strip().split() or [""])[0].lower()
            if expected and expected != h.hexdigest():
                dest.unlink(missing_ok=True)
                raise RuntimeError("Downloaded file is corrupted (checksum mismatch). Please try again.")
    if ANDROID:
        from .android_bridge import install_apk
        if install_apk(str(dest)) == "permission":
            # Android's settings page is open; the install continues by itself once the user allows it,
            # and asks again (with a "Give permission" button) if they come back without allowing it.
            job.message = "Allow AIRAG to install apps, then come back"
            return {"version": info["latest"], "needs_permission": True}
        job.message = "Opening the installer"
        return {"version": info["latest"]}
    job.message = "Installing - AIRAG will restart"
    flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    subprocess.Popen([str(dest), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/AIRAGUPDATE"],
                     creationflags=flags, close_fds=True)
    quit_app(delay=1.0)
    return {"version": info["latest"], "restarting": True}
