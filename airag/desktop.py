"""Launcher: starts the local server and shows AIRAG as either
  - a desktop window (pywebview, uses Microsoft Edge WebView2 on Windows), or
  - a browser tab + system-tray icon (pystray).
Also handles: single instance, free-port selection, restart, logging.
"""
from __future__ import annotations

import json
import logging
import logging.handlers
import os
import socket
import sys
import threading
import time
import webbrowser
from typing import Optional

import httpx

from . import __version__, appctl, config, paths

log = logging.getLogger("airag.launcher")
MUTEX_NAME = "AIRAGRunningMutex"   # the installer checks this to see if AIRAG is running
_mutex = None


# setup
def setup_logging(verbose: bool = False) -> None:
    paths.ensure_dirs()
    if sys.stdout is None:          # windowed exe: no console
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    fh = logging.handlers.RotatingFileHandler(paths.LOG_DIR / "airag.log", maxBytes=1_000_000, backupCount=2,
                                              encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.addHandler(fh)
    if not paths.FROZEN:
        sh = logging.StreamHandler()
        sh.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        root.addHandler(sh)
    for noisy in ("httpx", "httpcore", "trafilatura", "urllib3", "primp"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def apply_pending_mode() -> None:
    """The installer writes the user's window-mode choice to a file; apply it once."""
    try:
        mode = paths.PENDING_MODE_FILE.read_text(encoding="utf-8").strip().lower()
    except OSError:
        return
    if mode in ("desktop", "browser"):
        config.save({"app": {"ui_mode": mode}})
    try:
        paths.PENDING_MODE_FILE.unlink()
    except OSError:
        pass


def choose_port(preferred: int) -> int:
    for port in ([preferred] if preferred else []) + [0]:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return s.getsockname()[1]
            except OSError:
                continue
    raise RuntimeError("No free port")


# single instance
def _acquire_mutex() -> None:
    global _mutex
    if sys.platform == "win32":
        try:
            import ctypes
            _mutex = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
        except Exception:
            pass


def read_running() -> Optional[dict]:
    try:
        info = json.loads(paths.RUNTIME_FILE.read_text(encoding="utf-8"))
        r = httpx.get(f"http://127.0.0.1:{info['port']}/api/app/ping", timeout=1.5)
        if r.status_code == 200 and r.json().get("app") == "airag":
            return info
    except Exception:
        pass
    return None


def write_runtime(port: int, mode: str) -> None:
    try:
        paths.RUNTIME_FILE.write_text(json.dumps({"pid": os.getpid(), "port": port, "mode": mode,
                                                  "version": __version__}), encoding="utf-8")
    except OSError:
        pass


def clear_runtime() -> None:
    try:
        info = json.loads(paths.RUNTIME_FILE.read_text(encoding="utf-8"))
        if info.get("pid") == os.getpid():
            paths.RUNTIME_FILE.unlink()
    except (OSError, ValueError):
        pass


def wait_for_pid(pid: int, timeout: float = 20) -> None:
    end = time.time() + timeout
    while time.time() < end:
        if not _pid_alive(pid):
            return
        time.sleep(0.25)


def _pid_alive(pid: int) -> bool:
    if sys.platform == "win32":
        import ctypes
        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(h)
        return code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


# server
class ServerThread(threading.Thread):
    def __init__(self, port: int, host: str = "127.0.0.1"):
        super().__init__(daemon=True, name="airag-server")
        import uvicorn
        from .main import app
        app.state.loopback_only = host in ("127.0.0.1", "localhost", "::1")
        self.server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_config=None,
                                                    log_level="warning", lifespan="on"))

    def run(self) -> None:
        self.server.run()

    def wait_ready(self, timeout: float = 20) -> None:
        end = time.time() + timeout
        while time.time() < end and not self.server.started:
            if not self.is_alive():
                raise RuntimeError("Server failed to start (see log)")
            time.sleep(0.05)

    def stop(self) -> None:
        self.server.should_exit = True


# UI modes
def _tray_labels() -> dict:
    labels = {"open": "Open AIRAG", "settings": "Settings", "quit": "Quit AIRAG"}
    try:
        from . import languages
        s = config.load()
        lang = languages.normalize(s["app"].get("language")) if s["app"].get("language") != "auto" else None
        if not lang:
            import locale
            lang = languages.normalize((locale.getlocale()[0] or "en")[:5])
        data = json.loads((paths.WEB_DIR / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))
        for k in labels:
            labels[k] = data.get(f"tray.{k}", labels[k])
    except Exception:
        pass
    return labels


def run_tray(url: str, open_ui: bool) -> None:
    try:
        import pystray
        from PIL import Image
    except Exception as e:
        log.warning("tray unavailable (%s); running without tray", e)
        if open_ui:
            webbrowser.open(url)
        _block_until_quit()
        return
    labels = _tray_labels()
    img = Image.open(paths.ASSETS_DIR / "tray.png")
    icon = pystray.Icon("AIRAG", img, f"AIRAG {__version__}", menu=pystray.Menu(
        pystray.MenuItem(labels["open"], lambda: webbrowser.open(url), default=True),
        pystray.MenuItem(labels["settings"], lambda: webbrowser.open(url + "#/settings")),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(labels["quit"], lambda: icon.stop()),
    ))
    appctl.show_hook = lambda: webbrowser.open(url)
    appctl.quit_hook = icon.stop
    if open_ui:
        threading.Timer(0.3, lambda: webbrowser.open(url)).start()
    icon.run()


_quit_event = threading.Event()


def _block_until_quit() -> None:
    appctl.quit_hook = _quit_event.set
    try:
        while not _quit_event.wait(0.5):
            pass
    except KeyboardInterrupt:
        pass


def run_desktop(url: str, minimized: bool = False) -> bool:
    """Returns False if the window could not be created (caller falls back to browser mode)."""
    try:
        import webview
    except Exception as e:
        log.warning("pywebview unavailable: %s", e)
        return False
    s = config.load()
    bg = "#0f0f11" if s["app"].get("theme_hint") == "dark" else "#f4f4f5"
    win = webview.create_window("AIRAG", url, width=1320, height=880, min_size=(760, 560),
                                background_color=bg, text_select=True, minimized=minimized)

    def show():
        try:
            win.restore()
            win.show()
            win.on_top = True
            win.on_top = False
        except Exception:
            pass

    def pick_folder():
        res = win.create_file_dialog(webview.FOLDER_DIALOG)
        return res[0] if res else None

    def pick_files():
        return list(win.create_file_dialog(webview.OPEN_DIALOG, allow_multiple=True) or [])

    appctl.show_hook = show
    appctl.quit_hook = win.destroy
    appctl.pick_folder_hook = pick_folder
    appctl.pick_files_hook = pick_files
    try:
        paths.WEBVIEW_DIR.mkdir(parents=True, exist_ok=True)
        webview.start(private_mode=False, storage_path=str(paths.WEBVIEW_DIR))
        return True
    except Exception as e:
        log.exception("desktop window failed: %s", e)
        appctl.pick_folder_hook = appctl.pick_files_hook = None
        return False


# main entry
def launch(mode: Optional[str] = None, port: Optional[int] = None, host: str = "127.0.0.1",
           open_ui: bool = True, wait_pid: Optional[int] = None, verbose: bool = False) -> None:
    setup_logging(verbose)
    if wait_pid:
        wait_for_pid(wait_pid)
    if paths.migrate_legacy():
        log.info("imported settings/history from the old data folder")
    apply_pending_mode()
    settings = config.load()
    mode = mode or settings["app"].get("ui_mode") or "desktop"

    existing = read_running()
    if existing:
        log.info("AIRAG already running on port %s - showing it", existing["port"])
        try:
            httpx.post(f"http://127.0.0.1:{existing['port']}/api/app/show", timeout=3)
        except Exception:
            webbrowser.open(f"http://localhost:{existing['port']}/")
        return

    _acquire_mutex()
    port = port if port is not None else choose_port(int(settings["app"].get("port") or 0))
    server = ServerThread(port, host)
    server.start()
    server.wait_ready()
    url = f"http://localhost:{port}/"
    appctl.mode, appctl.port, appctl.url = mode, port, url
    write_runtime(port, mode)
    log.info("AIRAG %s running at %s (%s mode)", __version__, url, mode)
    try:
        if mode == "desktop":
            if not run_desktop(url, minimized=not open_ui):
                appctl.mode = "browser"
                run_tray(url, open_ui)
        elif mode == "browser":
            run_tray(url, open_ui)
        else:
            print(f"\n  AIRAG {__version__} running at {url}  (Ctrl+C to stop)\n")
            if open_ui:
                webbrowser.open(url)
            _block_until_quit()
    finally:
        server.stop()
        clear_runtime()
        server.join(timeout=5)
