"""Search backend registry.

To add a backend: subclass SearchBackend in a new module, decorate it with
@register and import the module at the bottom of this file.
"""
from __future__ import annotations

from typing import Dict, Optional, Type

from .base import ImageResult, SearchBackend, SearchError, SearchResult

BACKENDS: Dict[str, Type[SearchBackend]] = {}


def register(cls: Type[SearchBackend]) -> Type[SearchBackend]:
    BACKENDS[cls.name] = cls
    return cls


def _make(settings: dict, name: str) -> SearchBackend:
    s = settings["search"]
    cls = BACKENDS.get(name)
    if cls is None:
        raise SearchError(f"Unknown search backend '{name}'")
    cfg = {f["key"]: f.get("default", "") for f in cls.fields}
    cfg.update(s.get("backends", {}).get(name, {}))
    return cls(cfg, {"region": s.get("region", "us-en"), "safesearch": s.get("safesearch", "moderate")})


def get_search(settings: dict) -> SearchBackend:
    return _make(settings, settings["search"].get("backend", "duckduckgo"))


def get_image_search(settings: dict) -> Optional[SearchBackend]:
    name = settings["search"].get("image_backend", "duckduckgo")
    if not name or name == "none" or name not in BACKENDS or not BACKENDS[name].supports_images:
        return None
    return _make(settings, name)


from . import duckduckgo, searxng, brave, google_cse, marginalia  # noqa: E402,F401
