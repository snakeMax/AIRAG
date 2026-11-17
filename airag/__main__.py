"""AIRAG command line.

    AIRAG.exe                       start with the saved window mode (desktop window by default)
    python -m airag --mode browser  browser tab + tray icon
    python -m airag --mode server   just the server (prints the URL), e.g. for development
    --port N        fixed port (default: preferred port from settings, or a free one)
    --no-open       don't open a window/tab on start (tray/server modes)
    --install-browser               download the headless browser and exit (used by the installer)
    --version
"""
from __future__ import annotations

import argparse
import sys


def main() -> None:
    p = argparse.ArgumentParser(prog="airag", description="AIRAG research search engine")
    p.add_argument("--mode", choices=["desktop", "browser", "server"])
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int)
    p.add_argument("--no-open", "--no-browser", dest="no_open", action="store_true")
    p.add_argument("--wait-pid", type=int, help=argparse.SUPPRESS)
    p.add_argument("--pick-folder", metavar="OUTFILE", help=argparse.SUPPRESS)
    p.add_argument("--install-browser", action="store_true")
    p.add_argument("--verbose", action="store_true")
    p.add_argument("--version", action="store_true")
    args = p.parse_args()

    if args.version:
        from . import __version__
        print(__version__)
        return
    if args.pick_folder:
        from .appctl import run_folder_dialog
        run_folder_dialog(args.pick_folder)
        return
    if args.install_browser:
        from .desktop import setup_logging
        from . import browser_install
        setup_logging()
        try:
            browser_install.install()
        except Exception as e:  # never fail the installer because of this optional step
            import logging
            logging.getLogger("airag").error("browser install failed: %s", e)
            sys.exit(0)
        return

    from .desktop import launch
    launch(mode=args.mode, port=args.port, host=args.host, open_ui=not args.no_open,
           wait_pid=args.wait_pid, verbose=args.verbose)


if __name__ == "__main__":
    main()
