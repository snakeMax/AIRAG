"""Moving notes and folders inside a vault (drag and drop, or Move to…), keeping links working.

Links by name ([[Moose]]) keep working on their own, the way Obsidian resolves them. Links that spell out a
path ([[Topics/Moose]], [text](Topics/Moose.md)) are rewritten to the new place in every note that has them;
each changed note keeps its previous text as a version. Nothing is moved outside the vault, a folder can't
go into itself, and nothing that already exists at the destination is overwritten.
"""
from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Dict, List
from urllib.parse import quote, unquote

from . import pathguard, store

_WIKI = re.compile(r"(!?\[\[)([^\[\]|#\n]+)((?:#[^\[\]|\n]*)?(?:\|[^\[\]\n]*)?\]\])")
_MD = re.compile(r"(\]\()([^)\s]+?)((?:#[^)\s]*)?(?:\s+\"[^\"]*\")?\))")


def _remap(target: str, old: str, new: str, folder: bool) -> str:
    """The new link target, or "" when this target doesn't point at what moved."""
    t = target.strip().replace("\\", "/").lstrip("/")
    low = t.lower()
    o = old.lower()
    if folder:
        if low.startswith(o + "/"):
            return new + t[len(old):]
        return ""
    for suffix in ("", ".md"):
        if low == o + suffix:
            return new + suffix
    return ""


def rewrite_links(text: str, old: str, new: str, folder: bool) -> str:
    """old/new: vault paths without .md for a note (Topics/Moose), or folder paths (Topics)."""
    def wiki(m: re.Match) -> str:
        to = _remap(m.group(2), old, new, folder)
        return m.group(1) + to + m.group(3) if to else m.group(0)

    def md(m: re.Match) -> str:
        raw = m.group(2)
        if re.match(r"^[a-z][a-z0-9+.-]*:", raw, re.I):        # web links and other schemes stay
            return m.group(0)
        to = _remap(unquote(raw), old, new, folder)
        if not to:
            return m.group(0)
        if "%" in raw or " " not in unquote(raw):
            to = quote(to, safe="/#")
        return m.group(1) + to + m.group(3)
    return _MD.sub(md, _WIKI.sub(wiki, text))


def move(settings: dict, v: dict, rel: str, dest_folder: str, folder: bool = False) -> dict:
    if store.read_only(v):
        raise store.NotesError("This vault is set to read only in AIRAG")
    base = Path(os.path.realpath(store.vault_dir(settings, v)))
    src = pathguard.resolve(base, rel)
    if src == base:
        raise store.NotesError("Pick a note or folder inside the vault")
    if folder and not src.is_dir():
        raise store.NotesError("That folder doesn't exist")
    if not folder and not (src.is_file() and src.suffix.lower() == ".md"):
        raise store.NotesError("That note doesn't exist")
    dest_dir = base if not dest_folder.strip().strip("/") else pathguard.resolve(base, dest_folder)
    if not dest_dir.is_dir():
        raise store.NotesError("That folder doesn't exist")
    if folder and (dest_dir == src or src in dest_dir.parents):
        raise store.NotesError("A folder can't go inside itself")
    new = dest_dir / src.name
    old_rel = src.relative_to(base).as_posix()
    if new == src:
        return {"path": old_rel, "moved": False, "links": 0}
    if new.exists():
        raise store.NotesError(f"There's already something called “{src.name}” in that folder")
    with store._lock:
        shutil.move(str(src), str(new))
    new_rel = new.relative_to(base).as_posix()
    old_key = old_rel[:-3] if not folder and old_rel.lower().endswith(".md") else old_rel
    new_key = new_rel[:-3] if not folder and new_rel.lower().endswith(".md") else new_rel
    changed = 0
    for item in store.tree(settings, v, limit=50_000):
        if item["kind"] != "note":
            continue
        try:
            text = store.read_note(settings, v, item["path"])
        except (store.NotesError, OSError):
            continue
        if old_key.lower() not in text.lower() and quote(old_key, safe="/").lower() not in text.lower():
            continue
        out = rewrite_links(text, old_key, new_key, folder)
        if out != text:
            store.write_note(settings, v, item["path"], out)
            changed += 1
    return {"path": new_rel, "from": old_rel, "moved": True, "links": changed}
