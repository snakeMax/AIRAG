"""Web addresses the user gave directly (typed into a search or shared to AIRAG).

A search whose question contains links reads those pages first, through the normal
fetcher and its checks (offline mode, blocked sites, bot-check detection, size caps).
Later the same entry point takes pages added with "Add source" from Web tabs.
"""
from __future__ import annotations

import re
from typing import List
from urllib.parse import urlsplit

MAX_URLS = 3
MAX_LEN = 2000
_URL = re.compile(r"https?://[^\s<>\"'`]+", re.I)
_TRAIL = ".,;:!?)]}»”’"


def clean(url: str) -> str:
    """A safe http(s) address, or "" (no credentials, control characters or odd hosts)."""
    url = (url or "").strip().rstrip(_TRAIL)
    if not url or len(url) > MAX_LEN or any(ord(c) < 32 or ord(c) == 127 for c in url):
        return ""
    try:
        parts = urlsplit(url)
    except ValueError:
        return ""
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        return ""
    if parts.username or parts.password:
        return ""
    host = parts.hostname
    if host.startswith(".") or ".." in host:
        return ""
    return url


def urls_in(text: str, limit: int = MAX_URLS) -> List[str]:
    out: List[str] = []
    for m in _URL.finditer(text or ""):
        u = clean(m.group(0))
        if u and u not in out:
            out.append(u)
        if len(out) >= limit:
            break
    return out


def only_links(text: str) -> bool:
    """True when the text is nothing but one or more links (a shared link, not a question)."""
    rest = _URL.sub("", text or "")
    return bool(urls_in(text)) and not rest.strip(" \n\t,;")
