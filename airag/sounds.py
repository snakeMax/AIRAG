"""Sound effects: the built-in sounds live in web/sounds/, the user's own clips in <config>/sounds/.

Custom clips are checked by extension and by their first bytes (so a renamed file of another
kind is refused) and limited in size.
"""
from __future__ import annotations

import base64
from pathlib import Path
from typing import Optional

from . import paths

NAMES = ("mic_start", "mic_stop", "search_done", "explainer_done", "task_failed")
DEFAULT_FILES = {n: n.replace("_", "-") + ".wav" for n in NAMES}
TYPES = {"mp3": "audio/mpeg", "ogg": "audio/ogg", "wav": "audio/wav", "m4a": "audio/mp4", "aac": "audio/aac",
         "opus": "audio/ogg", "flac": "audio/flac", "webm": "audio/webm"}
MAX_BYTES = 3 * 1024 * 1024
DIR = paths.CONFIG_DIR / "sounds"


def _looks_like(ext: str, data: bytes) -> bool:
    head = data[:16]
    if ext == "mp3":
        return head[:3] == b"ID3" or (len(head) > 1 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0)
    if ext in ("ogg", "opus"):
        return head[:4] == b"OggS"
    if ext == "wav":
        return head[:4] == b"RIFF" and head[8:12] == b"WAVE"
    if ext in ("m4a",):
        return head[4:8] == b"ftyp"
    if ext == "aac":
        return len(head) > 1 and head[0] == 0xFF and (head[1] & 0xF0) == 0xF0
    if ext == "flac":
        return head[:4] == b"fLaC"
    if ext == "webm":
        return head[:4] == b"\x1aE\xdf\xa3"
    return False


def custom_file(name: str) -> Optional[Path]:
    if name not in NAMES or not DIR.exists():
        return None
    for p in DIR.glob(f"{name}.*"):
        if p.suffix[1:].lower() in TYPES:
            return p
    return None


def default_file(name: str) -> Optional[Path]:
    f = paths.WEB_DIR / "sounds" / DEFAULT_FILES.get(name, "")
    return f if name in NAMES and f.is_file() else None


def save(name: str, data_b64: str, ext: str) -> str:
    """Stores a custom clip; returns its file name. Raises ValueError for anything not allowed."""
    ext = (ext or "").lower().lstrip(".")
    if name not in NAMES:
        raise ValueError("Unknown sound")
    if ext not in TYPES:
        raise ValueError("Use an MP3, OGG, WAV, M4A, AAC, OPUS, FLAC or WEBM file")
    try:
        data = base64.b64decode(data_b64.split(",", 1)[-1], validate=False)
    except ValueError:
        raise ValueError("The file couldn't be read")
    if not data:
        raise ValueError("The file is empty")
    if len(data) > MAX_BYTES:
        raise ValueError("Sound files can be at most 3 MB")
    if not _looks_like(ext, data):
        raise ValueError(f"That doesn't look like a real .{ext} file")
    remove(name)
    DIR.mkdir(parents=True, exist_ok=True)
    out = DIR / f"{name}.{ext}"
    out.write_bytes(data)
    return out.name


def remove(name: str) -> None:
    if name not in NAMES or not DIR.exists():
        return
    for p in DIR.glob(f"{name}.*"):
        try:
            p.unlink()
        except OSError:
            pass
