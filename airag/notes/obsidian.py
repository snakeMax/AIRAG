"""Open a vault or note in the Obsidian app with an obsidian:// link.

Obsidian looks for a vault it already knows that contains the path. A folder it has never opened needs
"Open folder as vault" in Obsidian once; the page says so and offers to copy the folder's path.
The link is built only from a checked absolute path, so a page can't make AIRAG open other obsidian:// actions.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

from .. import paths


def uri_for(p: Path) -> str:
    return "obsidian://open?path=" + quote(str(p), safe="")


def open_path(p: Path) -> None:
    uri = uri_for(p)
    if paths.ANDROID:
        from ..android_bridge import open_obsidian
        if not open_obsidian(str(p)):
            raise RuntimeError("Obsidian isn't installed on this phone")
    elif sys.platform == "win32":
        try:
            os.startfile(uri)  # type: ignore[attr-defined]
        except OSError:
            raise RuntimeError("Obsidian isn't installed (or isn't set to open obsidian:// links)")
    elif sys.platform == "darwin":
        if subprocess.call(["open", uri]) != 0:
            raise RuntimeError("Obsidian isn't installed")
    else:
        try:
            subprocess.Popen(["xdg-open", uri])
        except OSError:
            raise RuntimeError("Can't open Obsidian on this computer")
