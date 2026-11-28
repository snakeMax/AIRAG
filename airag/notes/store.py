"""The Notes root folder, its vault list (notes-index.json), vault templates, and reading/writing notes.

Layout
    <Notes root>/
      notes-index.json          vault list: name, folder, purpose, template, linked, created, format
      Scripts/                  shared scripts (later)
      <Vault>/                  Obsidian-compatible: plain .md files and folders
        .airag/                 AIRAG's own data: index.db, versions/, scripts (never synced into notes)
Linked vaults (an existing Obsidian vault elsewhere) are listed by path. They're writable like AIRAG's own
vaults (user, 28 Nov: an Obsidian vault can be the main notes vault and must be usable straight away), unless
the user sets one to read only (`access: "read"`); then changes need `approved=True`. Every write still
checks the note's hash, so a newer copy edited in Obsidian is never overwritten. `.obsidian/` is never written.
The main vault (settings notes.main) is the one Notes opens with and Add to notes offers first.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

from .. import paths
from . import pathguard

FORMAT = 1
INDEX_FILE = "notes-index.json"
_lock = threading.RLock()

# folders made for each vault template; "worldbuilding" and "empty" start empty (user, 24 Nov)
TEMPLATES: Dict[str, List[str]] = {
    "research": ["Inbox", "Sources", "Notes", "Topics", "Outputs", "Attachments"],
    "writing": ["Inbox", "Manuscript", "Characters", "Research", "Drafts", "Attachments"],
    "worldbuilding": [],
    "personal": ["Inbox", "Projects", "Areas", "Resources", "Archive", "Journal"],
    "empty": [],
}
NOTE_TYPES = {
    "research": ["source", "claim", "topic", "question", "output"],
    "writing": ["chapter", "scene", "character", "research", "draft"],
    "worldbuilding": ["person", "place", "faction", "item", "event", "lore"],
    "personal": ["project", "area", "resource", "journal"],
    "empty": [],
}
MAX_NOTE_BYTES = 5_000_000
KEEP_VERSIONS = 20


class NotesError(Exception):
    pass


def default_root() -> Path:
    """Documents/AIRAG Notes on the system drive (C: on Windows). Changeable in Settings and at first start."""
    if paths.ANDROID:
        return Path("/storage/emulated/0/Documents/AIRAG Notes")
    return Path.home() / "Documents" / "AIRAG Notes"


def status(settings: dict) -> dict:
    r = root(settings)
    custom = bool(str((settings.get("notes") or {}).get("root") or "").strip())
    return {"path": str(r), "default": str(default_root()), "custom": custom, "exists": r.is_dir(),
            "vaults": len(load_index(settings)["vaults"]) if r.is_dir() else 0}


def root(settings: dict) -> Path:
    custom = str((settings.get("notes") or {}).get("root") or "").strip()
    return Path(custom).expanduser() if custom else default_root()


# ---------------------------------------------------------------- vault list
def _index_path(settings: dict) -> Path:
    return root(settings) / INDEX_FILE


def load_index(settings: dict) -> dict:
    p = _index_path(settings)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("vaults"), list):
            return data
    except (OSError, ValueError):
        pass
    return {"format": FORMAT, "vaults": []}


def _save_index(settings: dict, data: dict) -> None:
    root(settings).mkdir(parents=True, exist_ok=True)
    paths.atomic_write_text(_index_path(settings), json.dumps(data, indent=1, ensure_ascii=False))


def main_id(settings: dict) -> str:
    return str((settings.get("notes") or {}).get("main") or "")


def read_only(v: dict) -> bool:
    return bool(v.get("linked")) and v.get("access", "write") == "read"


def vaults(settings: dict) -> List[dict]:
    out = []
    mid = main_id(settings)
    for v in load_index(settings)["vaults"]:
        d = dict(v)
        d["exists"] = vault_dir(settings, v).is_dir()
        d["dir"] = str(vault_dir(settings, v))
        d["main"] = v.get("id") == mid
        d["read_only"] = read_only(v)
        out.append(d)
    return out


def set_access(settings: dict, vid: str, write: bool) -> dict:
    with _lock:
        data = load_index(settings)
        for v in data["vaults"]:
            if v.get("id") == vid:
                if v.get("linked"):
                    v["access"] = "write" if write else "read"
                _save_index(settings, data)
                return v
    raise NotesError("That vault isn't in AIRAG's list")


def vault_dir(settings: dict, v: dict) -> Path:
    return Path(v["path"]) if v.get("linked") else root(settings) / v["folder"]


def get_vault(settings: dict, vid: str) -> dict:
    for v in load_index(settings)["vaults"]:
        if v.get("id") == vid:
            return v
    raise NotesError("That vault isn't in AIRAG's list")


def create_vault(settings: dict, name: str, template: str = "research", purpose: str = "") -> dict:
    if template not in TEMPLATES:
        raise NotesError("Unknown vault template")
    folder = pathguard.check_name(name.strip()[:80])
    with _lock:
        data = load_index(settings)
        if any(v.get("folder", "").lower() == folder.lower() and not v.get("linked") for v in data["vaults"]):
            raise NotesError("A vault with that name already exists")
        d = root(settings) / folder
        if d.exists() and any(d.iterdir()):
            raise NotesError("A folder with that name already exists in the Notes folder")
        for sub in TEMPLATES[template]:
            (d / sub).mkdir(parents=True, exist_ok=True)
        (d / ".airag").mkdir(parents=True, exist_ok=True)
        v = {"id": secrets.token_hex(6), "name": folder, "folder": folder, "template": template,
             "purpose": purpose.strip()[:300], "linked": False, "created": time.time()}
        data["vaults"].append(v)
        _save_index(settings, data)
        return v


def link_vault(settings: dict, folder: str, name: str = "", write: bool = True) -> dict:
    """Add an existing (e.g. Obsidian) vault by its folder. Writable unless `write=False` (read only)."""
    p = Path(folder).expanduser()
    if not p.is_dir():
        raise NotesError("That folder doesn't exist")
    p = Path(os.path.realpath(p))
    with _lock:
        data = load_index(settings)
        if any(v.get("linked") and os.path.realpath(v["path"]) == str(p) for v in data["vaults"]):
            raise NotesError("That vault is already linked")
        v = {"id": secrets.token_hex(6), "name": (name or p.name)[:80], "path": str(p), "template": "empty",
             "purpose": "", "linked": True, "access": "write" if write else "read", "created": time.time()}
        data["vaults"].append(v)
        _save_index(settings, data)
        return v


def forget_vault(settings: dict, vid: str) -> None:
    """Remove a vault from AIRAG's list. Never deletes its files."""
    with _lock:
        data = load_index(settings)
        data["vaults"] = [v for v in data["vaults"] if v.get("id") != vid]
        _save_index(settings, data)


# ---------------------------------------------------------------- files
def private_dir(settings: dict, v: dict) -> Path:
    """AIRAG's own data for a vault. Linked vaults keep it in AIRAG's data folder, not in the user's vault."""
    if v.get("linked"):
        return paths.LOCAL_DIR / "notes" / v["id"]
    return vault_dir(settings, v) / ".airag"


def tree(settings: dict, v: dict, limit: int = 20000) -> List[dict]:
    """Every folder and Markdown note in the vault (private folders and other files skipped)."""
    base = vault_dir(settings, v)
    out: List[dict] = []
    for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if d.lower() not in pathguard.PRIVATE_DIRS and not d.startswith("."))
        rel_dir = Path(dirpath).relative_to(base).as_posix()
        if rel_dir != ".":
            out.append({"path": rel_dir, "kind": "folder"})
        for f in sorted(filenames):
            if f.lower().endswith(".md") and not f.startswith("."):
                full = Path(dirpath) / f
                if full.is_symlink():
                    continue
                rel = f if rel_dir == "." else f"{rel_dir}/{f}"
                try:
                    st = full.stat()
                except OSError:
                    continue
                out.append({"path": rel, "kind": "note", "mtime": st.st_mtime, "size": st.st_size})
            if len(out) >= limit:
                return out
    return out


def read_note(settings: dict, v: dict, rel: str) -> str:
    p = pathguard.resolve(vault_dir(settings, v), rel)
    if p.suffix.lower() != ".md":
        raise NotesError("Only Markdown notes can be opened here")
    if p.stat().st_size > MAX_NOTE_BYTES:
        raise NotesError("That note is too large to open")
    return p.read_text(encoding="utf-8", errors="replace")


def _keep_version(settings: dict, v: dict, rel: str, old: str) -> None:
    vd = private_dir(settings, v) / "versions" / re.sub(r"[^\w\-]+", "_", rel)[:120]
    vd.mkdir(parents=True, exist_ok=True)
    paths.atomic_write_text(vd / f"{time.time():.3f}.md", old)
    old_ones = sorted(vd.glob("*.md"))
    for f in old_ones[:-KEEP_VERSIONS]:
        try:
            f.unlink()
        except OSError:
            pass


def write_note(settings: dict, v: dict, rel: str, text: str, expected_hash: Optional[str] = None,
               approved: bool = False) -> dict:
    """Save a note (atomic). The previous text is kept as a version. `expected_hash` stops overwriting
    a newer copy (e.g. edited in Obsidian meanwhile). Linked vaults need `approved=True`."""
    if read_only(v) and not approved:
        raise NotesError("This vault is set to read only in AIRAG (Settings → Library & storage → Notes vaults)")
    if len(text.encode("utf-8")) > MAX_NOTE_BYTES:
        raise NotesError("That note is too large")
    rel = pathguard.clean_rel(rel)
    if not rel.lower().endswith(".md"):
        rel += ".md"
    p = pathguard.resolve(vault_dir(settings, v), rel)
    from .parser import parse
    with _lock:
        old = p.read_text(encoding="utf-8", errors="replace") if p.exists() else None
        if old is not None and expected_hash and parse(old, p.stem).hash != expected_hash:
            raise NotesError("This note changed since you opened it (maybe in another app). Reload it first.")
        if old is not None and old != text:
            _keep_version(settings, v, rel, old)
        p.parent.mkdir(parents=True, exist_ok=True)
        paths.atomic_write_text(p, text)
    return {"path": rel, "hash": parse(text, p.stem).hash}


TRASH = ".trash"          # Obsidian's own "move to trash" folder, so both apps see the same removed notes


def trash(settings: dict, v: dict, rel: str, folder: bool = False) -> dict:
    """Move a note (or a whole folder) into the vault's .trash folder. Nothing is deleted for good;
    restore() puts it back. Returns {"path", "trashed"} (both vault-relative)."""
    import shutil
    if read_only(v):
        raise NotesError("This vault is set to read only in AIRAG")
    base = Path(os.path.realpath(vault_dir(settings, v)))
    src = pathguard.resolve(base, rel)
    if src == base:
        raise NotesError("Pick a note or folder inside the vault")
    if folder and not src.is_dir():
        raise NotesError("That folder doesn't exist")
    if not folder and not (src.is_file() and src.suffix.lower() == ".md"):
        raise NotesError("That note doesn't exist")
    rel = src.relative_to(base).as_posix()
    with _lock:
        dest = base / TRASH / rel
        n = 2
        while dest.exists():
            stem = Path(rel).stem if not folder else Path(rel).name
            dest = (base / TRASH / rel).with_name(f"{stem} ({n})" + ("" if folder else src.suffix))
            n += 1
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest))
    return {"path": rel, "trashed": dest.relative_to(base).as_posix()}


def restore(settings: dict, v: dict, trashed: str, rel: str) -> dict:
    """Undo trash(): move it back to where it was, if that place is still free."""
    import shutil
    if read_only(v):
        raise NotesError("This vault is set to read only in AIRAG")
    base = Path(os.path.realpath(vault_dir(settings, v)))
    src = pathguard.resolve(base, trashed, allow_private=True)
    if not str(pathguard.clean_rel(trashed, allow_private=True)).lower().startswith(TRASH + "/") or not src.exists():
        raise NotesError("That isn't in the vault's trash any more")
    dest = pathguard.resolve(base, rel)
    if dest.exists():
        raise NotesError("Something with that name is back in its place; restore it by hand from the .trash folder")
    with _lock:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest))
        trash_root = base / TRASH
        parent = src.parent
        while parent != trash_root and trash_root in parent.parents:   # tidy folders the restore left empty
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent
    return {"path": dest.relative_to(base).as_posix()}


def safe_title(title: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f#^\[\]]+', " ", title).strip().strip(".")
    name = re.sub(r"\s+", " ", name)[:120] or "Untitled"
    if name.split(".")[0].lower() in pathguard.RESERVED:
        name = "_" + name
    return name


def free_path(settings: dict, v: dict, folder: str, title: str) -> str:
    base = vault_dir(settings, v)
    folder = pathguard.clean_rel(folder) if folder else ""
    stem = safe_title(title)
    for n in range(1, 500):
        name = f"{stem}.md" if n == 1 else f"{stem} {n}.md"
        rel = f"{folder}/{name}" if folder else name
        if not pathguard.resolve(base, rel).exists():
            return rel
    raise NotesError("Too many notes with that name")


def create_note(settings: dict, v: dict, folder: str, title: str, body: str = "", props: Optional[dict] = None,
                approved: bool = False) -> dict:
    rel = free_path(settings, v, folder, title)
    props = dict(props or {})
    props.setdefault("id", secrets.token_hex(6))       # stable hidden id for notes AIRAG makes
    head = "---\n" + "".join(f"{k}: {_yaml_value(val)}\n" for k, val in props.items()) + "---\n"
    return write_note(settings, v, rel, head + body, approved=approved)


def _yaml_value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_yaml_value(x) for x in v) + "]"
    s = str(v).replace("\n", " ")
    return s if re.fullmatch(r"[\w\-/. ]+", s) and s.strip() == s and s.lower() not in ("true", "false", "null", "yes", "no") else json.dumps(s, ensure_ascii=False)
