"""Resolve a note path inside its vault, refusing anything that could escape or confuse the file system.

Refused: absolute paths, drive letters, UNC paths, `..`, empty segments, Windows reserved names (CON, NUL,
COM1...), names ending in a dot or space, `:` (alternate data streams), control and bidi characters,
paths into `.obsidian/` or `.airag/` (unless allowed), symlinks/junctions that lead outside the vault, and
very long paths.
"""
from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path, PurePosixPath

RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
BAD_CHARS = re.compile(r'[<>:"|?*\x00-\x1f\x7f]')
BIDI = {"‪", "‫", "‬", "‭", "‮", "⁦", "⁧", "⁨", "⁩", "‎", "‏", "؜"}
PRIVATE_DIRS = {".obsidian", ".airag", ".git", ".trash"}
MAX_PATH = 400


class PathError(ValueError):
    pass


def check_name(name: str) -> str:
    """One file or folder name (no slashes)."""
    name = unicodedata.normalize("NFC", name)
    if not name or name in (".", ".."):
        raise PathError("Empty or relative name")
    if BAD_CHARS.search(name) or any(ch in BIDI for ch in name):
        raise PathError(f"Name has characters files can't use: {name!r}")
    if name != name.rstrip(". ") or name != name.lstrip(" "):
        raise PathError(f"Names can't start with a space or end with a dot or space: {name!r}")
    if name.split(".")[0].lower() in RESERVED:
        raise PathError(f"'{name}' is a reserved name on Windows")
    if len(name.encode("utf-8")) > 240:
        raise PathError("Name is too long")
    return name


def clean_rel(rel: str, allow_private: bool = False) -> str:
    """A vault-relative path with forward slashes, checked segment by segment."""
    rel = str(rel).replace("\\", "/")
    if rel.startswith("/") or re.match(r"^[A-Za-z]:", rel) or rel.startswith("//"):
        raise PathError("Absolute paths aren't allowed")
    parts = [p for p in PurePosixPath(rel).parts if p not in ("",)]
    if not parts:
        raise PathError("Empty path")
    for p in parts:
        check_name(p)
        if not allow_private and p.lower() in PRIVATE_DIRS:
            raise PathError(f"'{p}' is a private folder")
    out = "/".join(parts)
    if len(out) > MAX_PATH:
        raise PathError("Path is too long")
    return out


def resolve(root: Path, rel: str, allow_private: bool = False) -> Path:
    """The real path of `rel` inside `root`; refuses anything that ends up outside (symlinks included)."""
    rel = clean_rel(rel, allow_private)
    root_real = Path(os.path.realpath(root))
    target = Path(os.path.realpath(root_real / rel))
    try:
        target.relative_to(root_real)
    except ValueError:
        raise PathError("That path leads outside the vault") from None
    return target
