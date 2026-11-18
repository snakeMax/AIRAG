"""Token and cost tracking.

Every AI call goes through `Metered` (see llm/__init__.get_llm), which adds the call's
input/output tokens to a per-month, per-model tally in usage.json. Providers report the
exact counts when their API gives them (`report()`); otherwise the counts are estimated
from the text length (about 4 characters per token) and marked as estimates.

Prices come from OpenRouter's free public model list (fetched at most once a day and
cached), with a small built-in table as fallback. Local models (Ollama, My PC) cost $0.
"""
from __future__ import annotations

import contextvars
import json
import logging
import re
import threading
import time
from typing import AsyncIterator, Dict, Optional

from . import paths

log = logging.getLogger("airag.usage")

USAGE_FILE = paths.CONFIG_DIR / "usage.json"
PRICES_FILE = paths.LOCAL_DIR / "prices.json"
PRICES_URL = "https://openrouter.ai/api/v1/models"
PRICES_MAX_AGE = 24 * 3600
LOCAL_PROVIDERS = {"ollama", "pc_link", "mock"}

# $ per million tokens (input, output). Used when the OpenRouter list can't be fetched.
FALLBACK_PRICES = {
    "claude-opus": (5.0, 25.0), "claude-sonnet": (3.0, 15.0), "claude-haiku": (1.0, 5.0),
    "gpt-5-nano": (0.05, 0.4), "gpt-5-mini": (0.25, 2.0), "gpt-5": (1.25, 10.0),
    "gpt-4.1-mini": (0.4, 1.6), "gpt-4.1": (2.0, 8.0), "gpt-4o-mini": (0.15, 0.6), "gpt-4o": (2.5, 10.0),
    "deepseek-chat": (0.28, 0.42), "deepseek-reasoner": (0.28, 0.42),
}

_lock = threading.Lock()
_current: contextvars.ContextVar[Optional[dict]] = contextvars.ContextVar("airag_usage", default=None)


def report(input_tokens: Optional[int] = None, output_tokens: Optional[int] = None) -> None:
    """Called by providers with the exact token counts of the call in progress."""
    d = _current.get()
    if d is None:
        return
    if input_tokens is not None:
        d["in"] = int(input_tokens)
    if output_tokens is not None:
        d["out"] = int(output_tokens)


def estimate(text) -> int:
    if isinstance(text, list):   # vision content parts
        return sum(estimate(p.get("text", "")) if isinstance(p, dict) else 0 for p in text) + 800 * sum(
            1 for p in text if isinstance(p, dict) and p.get("type") != "text")
    return max(1, len(str(text or "")) // 4)


# ---------------------------------------------------------------- storage
def _month() -> str:
    return time.strftime("%Y-%m")


def _load() -> dict:
    try:
        return json.loads(USAGE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save(data: dict) -> None:
    USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = USAGE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
    tmp.replace(USAGE_FILE)


def add(provider: str, model: str, tin: int, tout: int, estimated: bool) -> None:
    cost = price_of(provider, model, tin, tout)
    with _lock:
        data = _load()
        month = data.setdefault(_month(), {})
        key = f"{provider}|{model}"
        row = month.setdefault(key, {"provider": provider, "model": model, "calls": 0, "in": 0, "out": 0,
                                     "cost": 0.0, "estimated": 0})
        row["calls"] += 1
        row["in"] += tin
        row["out"] += tout
        row["cost"] = round(row["cost"] + (cost or 0.0), 6)
        row["estimated"] += 1 if estimated else 0
        row["priced"] = cost is not None or provider in LOCAL_PROVIDERS
        for old in sorted(data)[:-13]:        # keep about a year
            data.pop(old, None)
        _save(data)


def reset_month() -> None:
    with _lock:
        data = _load()
        data.pop(_month(), None)
        _save(data)


# ---------------------------------------------------------------- prices
_prices: Dict[str, tuple] = {}
_prices_at = 0.0          # when the list was last fetched successfully
_retry_at = 0.0           # don't try again before this (after a failure)


def _norm(model: str) -> str:
    m = model.lower().split("/")[-1].split(":")[0]
    m = re.sub(r"-\d{8}$", "", m)              # dated snapshots: claude-x-20250101
    return m.replace(".", "-")


def _load_prices() -> None:
    global _prices, _prices_at
    if _prices:
        return
    try:
        cached = json.loads(PRICES_FILE.read_text(encoding="utf-8"))
        _prices = {k: tuple(v) for k, v in cached.get("prices", {}).items()}
        _prices_at = float(cached.get("at", 0))
    except (OSError, ValueError):
        pass


async def refresh_prices(force: bool = False) -> bool:
    """Fetch OpenRouter's public price list (no key needed). Returns True when updated."""
    global _prices, _prices_at, _retry_at
    _load_prices()
    if not force and (time.time() - _prices_at < PRICES_MAX_AGE or time.time() < _retry_at):
        return False
    import httpx
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.get(PRICES_URL)
        r.raise_for_status()
        out = {}
        for m in r.json().get("data", []):
            p = m.get("pricing") or {}
            try:
                pin, pout = float(p.get("prompt") or 0) * 1e6, float(p.get("completion") or 0) * 1e6
            except (TypeError, ValueError):
                continue
            if pin < 0 or pout < 0:
                continue
            out[m["id"].lower()] = (pin, pout)
            out.setdefault(_norm(m["id"]), (pin, pout))
    except Exception as e:   # offline, blocked, changed format: keep what we have
        log.info("price list not updated: %s", e)
        _retry_at = time.time() + 3600   # try again in an hour
        return False
    _prices, _prices_at = out, time.time()
    try:
        PRICES_FILE.parent.mkdir(parents=True, exist_ok=True)
        PRICES_FILE.write_text(json.dumps({"at": _prices_at, "prices": out}), encoding="utf-8")
    except OSError:
        pass
    return True


def per_million(provider: str, model: str) -> Optional[tuple]:
    """($ per 1M input tokens, $ per 1M output tokens), or None if unknown."""
    if provider in LOCAL_PROVIDERS:
        return (0.0, 0.0)
    _load_prices()
    m = (model or "").lower()
    if m in _prices:
        return _prices[m]
    n = _norm(m)
    if n in _prices:
        return _prices[n]
    # e.g. claude-sonnet-5-5 vs OpenRouter's claude-sonnet-5.5 / anthropic/claude-sonnet-5.5
    for key, val in _prices.items():
        if "/" not in key and (key.startswith(n) or n.startswith(key)) and len(key) > 6:
            return val
    for prefix, val in sorted(FALLBACK_PRICES.items(), key=lambda kv: -len(kv[0])):
        if n.startswith(prefix):
            return val
    return None


def price_of(provider: str, model: str, tin: int, tout: int) -> Optional[float]:
    p = per_million(provider, model)
    if p is None:
        return None
    return (tin * p[0] + tout * p[1]) / 1e6


# ---------------------------------------------------------------- summary / budget
def summary(settings: Optional[dict] = None) -> dict:
    data = _load()
    month = _month()
    rows = sorted(data.get(month, {}).values(), key=lambda r: -r["cost"])
    spent = round(sum(r["cost"] for r in rows), 4)
    budget = float(((settings or {}).get("usage") or {}).get("monthly_budget") or 0)
    history = [{"month": k, "cost": round(sum(r["cost"] for r in v.values()), 4),
                "tokens": sum(r["in"] + r["out"] for r in v.values())} for k, v in sorted(data.items())]
    return {"month": month, "rows": rows, "spent": spent, "budget": budget,
            "left": round(budget - spent, 4) if budget else None,
            "tokens": sum(r["in"] + r["out"] for r in rows),
            "unpriced": [r["model"] for r in rows if not r.get("priced", True)],
            "prices_updated": (_prices_at or None) if _prices else None, "history": history}


def budget_note(settings: dict) -> str:
    """A line for the AI when the monthly budget is running low, so it plans fewer/smaller steps."""
    u = settings.get("usage") or {}
    if not u.get("tell_model", True):
        return ""
    s = summary(settings)
    if not s["budget"]:
        return ""
    share = s["spent"] / s["budget"]
    if share < 0.7:
        return ""
    left = max(0.0, s["budget"] - s["spent"])
    return (f"BUDGET: the user's monthly AI budget is nearly used (${left:.2f} of ${s['budget']:.2f} left). "
            "Prefer fewer searches and shorter outputs.")


def over_budget(settings: dict) -> bool:
    u = settings.get("usage") or {}
    s = summary(settings)
    return bool(u.get("stop_at_budget") and s["budget"] and s["spent"] >= s["budget"])


# ---------------------------------------------------------------- metering wrapper
class Metered:
    """Wraps a provider so every call is counted. Everything else passes through."""

    def __init__(self, inner):
        self._inner = inner

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def _record(self, d: dict, system, user, out_text: str) -> None:
        est = "in" not in d or "out" not in d
        tin = d.get("in", estimate(system) + estimate(user))
        tout = d.get("out", estimate(out_text))
        try:
            add(self._inner.name, self._inner.model, tin, tout, est)
        except Exception:
            log.exception("could not record usage")

    async def complete(self, system, user, max_tokens=2048, json_mode=False):
        d: dict = {}
        tok = _current.set(d)
        try:
            out = await self._inner.complete(system, user, max_tokens, json_mode)
        finally:
            _current.reset(tok)
        self._record(d, system, user, out)
        return out

    async def stream(self, system, user, max_tokens=4096) -> AsyncIterator[str]:
        d: dict = {}
        parts = []
        tok = _current.set(d)
        try:
            async for piece in self._inner.stream(system, user, max_tokens):
                parts.append(piece)
                yield piece
        finally:
            try:
                _current.reset(tok)
            except ValueError:      # generator closed from another context
                pass
            self._record(d, system, user, "".join(parts))
