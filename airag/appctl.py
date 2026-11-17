"""Hooks between the web server and the window/tray launcher (desktop.py).

The launcher fills these in; the API calls them. When AIRAG runs as a plain
server (python -m airag --mode server) they fall back to harmless defaults.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
from typing import Callable, Optional

from .paths import FROZEN

log = logging.getLogger("airag.app")

mode: str = "server"      # desktop | browser | server
port: int = 0
url: str = ""
show_hook: Optional[Callable[[], None]] = None
quit_hook: Optional[Callable[[], None]] = None
pick_folder_hook: Optional[Callable[[], Optional[str]]] = None


def show() -> None:
    if show_hook:
        show_hook()


def quit_app(delay: float = 0.4) -> None:
    def later():
        log.info("quitting")
        if quit_hook:
            quit_hook()
        else:
            os._exit(0)
    threading.Timer(delay, later).start()


def self_command() -> list:
    """Command line that starts this same program again."""
    if FROZEN:
        return [sys.executable]
    return [sys.executable, "-m", "airag"]


def restart(new_mode: Optional[str] = None) -> None:
    args = self_command() + ["--wait-pid", str(os.getpid())]
    if new_mode:
        args += ["--mode", new_mode]
    kw: dict = {"close_fds": True, "stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if sys.platform == "win32":
        kw["creationflags"] = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    else:
        kw["start_new_session"] = True
    subprocess.Popen(args, **kw)
    quit_app(0.6)


def pick_folder() -> Optional[str]:
    """Native folder picker. Uses the desktop window's dialog when available,
    otherwise a tiny helper process with a Tk dialog (works from browser mode)."""
    from .paths import ANDROID
    if ANDROID:
        return pick_folder_hook() if pick_folder_hook else None
    if pick_folder_hook:
        try:
            return pick_folder_hook()
        except Exception:
            log.exception("window folder dialog failed")
    import tempfile
    from pathlib import Path
    out = Path(tempfile.gettempdir()) / f"airag-pick-{os.getpid()}.txt"
    out.unlink(missing_ok=True)
    kw: dict = {}
    if sys.platform == "win32":
        kw["creationflags"] = 0x08000000
    try:
        subprocess.run(self_command() + ["--pick-folder", str(out)], timeout=600, **kw)
        path = out.read_text(encoding="utf-8").strip() if out.exists() else ""
    except Exception:
        log.exception("folder picker failed")
        path = ""
    finally:
        out.unlink(missing_ok=True)
    return path or None


def run_folder_dialog(outfile: str) -> None:
    """Entry point for `--pick-folder <file>` (runs in its own process)."""
    path = ""
    try:
        import tkinter
        from tkinter import filedialog
        root = tkinter.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        path = filedialog.askdirectory(title="Choose a folder for your AIRAG library") or ""
        root.destroy()
    except Exception:
        path = ""
    with open(outfile, "w", encoding="utf-8") as f:
        f.write(path)
