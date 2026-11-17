"""Optional headless browser (Playwright + Chromium) for JavaScript-heavy pages.

The Playwright package is bundled with the app; the browser itself (~100-150 MB)
is downloaded on demand into LOCAL_DIR/browsers.
"""
from __future__ import annotations

import logging
import re
import shutil
import subprocess
import sys
from typing import List, Optional

from .paths import BROWSERS_DIR, FROZEN, dir_size

log = logging.getLogger("airag.browser")


def package_available() -> bool:
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


def browser_installed() -> bool:
    try:
        return any(p.is_dir() for p in BROWSERS_DIR.glob("chromium*"))
    except OSError:
        return False


def installed() -> bool:
    return package_available() and browser_installed()


def status() -> dict:
    return {"package": package_available(), "browser": browser_installed(), "ready": installed(),
            "path": str(BROWSERS_DIR), "size": dir_size(BROWSERS_DIR) if BROWSERS_DIR.exists() else 0,
            "can_install_package": not FROZEN}


def _driver_cmd() -> List[str]:
    from playwright._impl._driver import compute_driver_executable
    exe = compute_driver_executable()
    return [str(x) for x in exe] if isinstance(exe, (tuple, list)) else [str(exe)]


def _driver_env() -> dict:
    import os
    try:
        from playwright._impl._driver import get_driver_env
        env = dict(get_driver_env())
    except Exception:
        env = dict(os.environ)
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(BROWSERS_DIR)
    return env


def _run(cmd: List[str], env: Optional[dict], job=None) -> None:
    kw: dict = {}
    if sys.platform == "win32":
        kw["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
    proc = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            stdin=subprocess.DEVNULL, text=True, errors="replace", **kw)
    tail: List[str] = []
    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.strip()
        if not line:
            continue
        tail = (tail + [line])[-8:]
        if job is not None:
            if job.cancelled:
                proc.kill()
                return
            m = re.search(r"(\d{1,3})%", line)
            if m:
                job.progress = min(1.0, int(m.group(1)) / 100)
            job.detail = line[:160]
    if proc.wait() != 0:
        raise RuntimeError("\n".join(tail[-4:]) or f"exit code {proc.returncode}")


def install(job=None) -> dict:
    """Blocking install (run it in a thread). Installs the package first when running from source."""
    if not package_available():
        if FROZEN:
            raise RuntimeError("The browser component is missing from this build.")
        if job:
            job.message = "Installing the Playwright package…"
        _run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "playwright"], None, job)
        import importlib
        importlib.invalidate_caches()
    BROWSERS_DIR.mkdir(parents=True, exist_ok=True)
    if job:
        job.message, job.progress = "Downloading Chromium (about 100-150 MB)…", 0.0
    base = _driver_cmd()
    try:
        _run(base + ["install", "--only-shell", "chromium"], _driver_env(), job)
    except RuntimeError as e:
        log.info("--only-shell failed (%s), trying full chromium", e)
        _run(base + ["install", "chromium"], _driver_env(), job)
    if job:
        job.message = "Headless browser installed"
    return status()


def uninstall() -> dict:
    shutil.rmtree(BROWSERS_DIR, ignore_errors=True)
    return status()
