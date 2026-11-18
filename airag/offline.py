"""Offline mode: nothing is searched or read on the web. Answers come only from your own files (My library and
library folders), pinned pages and earlier articles in History.

Who writes the answer is your choice when you turn it on:
- "local": a model on your own device: Ollama on the computer, Ollama on the computer through the PC link
  (phone), or any OpenAI-compatible server on this device (for example llama.cpp's server on the phone).
  Then nothing leaves your devices.
- "current": the model you normally use writes, but its sources are only your own files. The question and
  the passages used are still sent to that AI service (said plainly in the app).

Every web path asks `blocked()` first: search backends, page fetching, wikis, YouTube, pictures for saved
or exported articles, price-list and update checks. AI providers are not web reading and stay allowed.
"""
from __future__ import annotations

import re
from typing import List, Optional
from urllib.parse import urlparse

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "[::1]"}
MESSAGE = "Offline mode is on: nothing is searched or read on the web."


class Offline(RuntimeError):
    pass


def _settings(settings: Optional[dict]) -> dict:
    if settings is not None:
        return settings
    from . import config
    return config.load(with_env=False)


def on(settings: Optional[dict] = None) -> bool:
    try:
        return bool(_settings(settings).get("library", {}).get("offline"))
    except Exception:
        return False


def blocked(settings: Optional[dict] = None) -> bool:
    """True when web access must not happen now."""
    return on(settings)


def check(settings: Optional[dict] = None) -> None:
    if blocked(settings):
        raise Offline(MESSAGE)


# ---------------------------------------------------------------- the local writer
def _is_local_url(url: str) -> bool:
    host = (urlparse(url or "").hostname or "").lower()
    return host in LOCAL_HOSTS or host.endswith(".localhost")


def local_choices(settings: dict) -> List[dict]:
    """Local models AIRAG could write with, from what's set up (nothing is started or contacted here)."""
    from . import ollama_manager
    llm = settings["llm"]
    prov = llm.get("providers", {})
    out = []
    o = prov.get("ollama", {})
    o_url = o.get("base_url") or "http://localhost:11434"
    if ollama_manager.is_local(o_url) and (ollama_manager.find_executable() or llm.get("provider") == "ollama"):
        out.append({"provider": "ollama", "model": o.get("model") or "llama3.1:8b", "label": "Ollama on this computer"})
    pc = prov.get("pc_link", {})
    if pc.get("base_url") and pc.get("api_key"):
        out.append({"provider": "pc_link", "model": pc.get("model") or "", "label": "Ollama on your computer (PC link)"})
    oc = prov.get("openai_compatible", {})
    if oc.get("base_url") and oc.get("model") and _is_local_url(oc["base_url"]):   # set up (the URL alone is a default)
        out.append({"provider": "openai_compatible", "model": oc.get("model") or "",
                    "label": "Local server on this device (" + (urlparse(oc["base_url"]).netloc or "localhost") + ")"})
    return out


def writer_override(settings: dict) -> Optional[dict]:
    """{"provider", "model"} to use instead of the normal model, or None."""
    lib = settings.get("library", {})
    if not lib.get("offline") or lib.get("offline_writer") != "local":
        return None
    want = lib.get("offline_provider") or ""
    for c in local_choices(settings):
        if c["provider"] == want:
            model = lib.get("offline_model") or c["model"]
            return {"provider": c["provider"], "model": model}
    return None


# ---------------------------------------------------------------- History as a source
def history_matches(terms: List[str], limit: int = 3, skip_id: str = "") -> List[dict]:
    """Earlier articles that share enough words with the question (no AI, no network)."""
    from . import history
    want = {t.lower() for t in terms if len(t) > 2}
    if not want:
        return []
    scored = []
    for item in history.listing(200):
        if item.get("id") == skip_id or item.get("outcome") not in (None, "article"):
            continue
        rec = history.get(item["id"])
        if not rec or not rec.get("article"):
            continue
        head = f"{rec.get('title', '')} {rec.get('query', '')} {' '.join(rec.get('tags') or [])}".lower()
        low = rec["article"][:20000].lower()
        hits = sum(2 for t in want if t in head) + sum(1 for t in want if re.search(r"\b" + re.escape(t), low))
        if hits >= max(2, round(len(want) * 0.6)):
            scored.append((hits, rec))
    scored.sort(key=lambda z: -z[0])
    return [r for _, r in scored[:limit]]
