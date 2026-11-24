"""Live resource graphs (Settings -> System, off by default): processor, memory and AI tokens per minute.

Only measures; nothing here changes anything. Works without psutil (Android): process memory then comes
from /proc/self/status, the processor and whole-device memory are left out, and the phone page shows
battery and temperature from the Android bridge instead.
"""
import os
import threading
import time
from collections import deque
from typing import Optional

try:
    import psutil  # desktop only (not bundled on Android)
except Exception:  # pragma: no cover - depends on the platform
    psutil = None

_lock = threading.Lock()
_tokens: deque = deque(maxlen=5000)   # (time, tokens) for the last ~10 minutes
WINDOW = 600
_proc = None


def note_tokens(n: int) -> None:
    """Called for every AI call (usage.add)."""
    if n <= 0:
        return
    now = time.time()
    with _lock:
        _tokens.append((now, int(n)))
        while _tokens and _tokens[0][0] < now - WINDOW:
            _tokens.popleft()


def tokens_per_minute(minutes: int = 10) -> list:
    """Tokens in each of the last `minutes` minutes, oldest first (the last one is the current minute)."""
    now = time.time()
    out = [0] * minutes
    with _lock:
        for t, n in _tokens:
            age = int((now - t) // 60)
            if 0 <= age < minutes:
                out[minutes - 1 - age] += n
    return out


def _rss_mb() -> Optional[float]:
    global _proc
    if psutil:
        try:
            _proc = _proc or psutil.Process(os.getpid())
            return round(_proc.memory_info().rss / 1048576, 1)
        except Exception:
            pass
    try:
        with open("/proc/self/status", encoding="ascii", errors="ignore") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return round(int(line.split()[1]) / 1024, 1)
    except OSError:
        pass
    return None


def snapshot() -> dict:
    cpu = mem_pct = None
    if psutil:
        try:
            cpu = psutil.cpu_percent(interval=None)       # since the previous call (first call: 0)
            mem_pct = psutil.virtual_memory().percent
        except Exception:
            pass
    from . import runs
    try:
        tasks = len(runs.active())
    except Exception:
        tasks = 0
    tpm = tokens_per_minute()
    return {"cpu": cpu, "app_mem_mb": _rss_mb(), "mem_pct": mem_pct, "tokens_per_min": tpm,
            "tokens_now": tpm[-1], "tasks": tasks, "at": time.time()}
