"""Background jobs (searches, explainers, later autonomous research) that keep going when you leave the page.

Each search runs on the server as a background task. Its events are kept in memory,
so the page can leave and come back (or the app can be reopened) and replay what
happened so far before following along live. Searches started while another one is
running wait in a queue and start when it finishes. A search can be cancelled at any
time, whether it's running or still queued.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Callable, Dict, List, Optional

log = logging.getLogger("airag.runs")

MAX_PARALLEL = 1          # default jobs at a time per kind: keeps the AI provider's rate limits and the phone's battery happy
LIMITS = {"search": 1, "explainer": 1}
KEEP_FINISHED = 600       # seconds a finished search stays here (after that it's only in history)


class Run:
    def __init__(self, rid: str, query: str, mode: str, factory: Callable, kind: str = "search", ref: str = ""):
        self.id, self.query, self.mode = rid, query, mode
        self.kind = kind                 # search | explainer | ...
        self.ref = ref or rid            # the history record it belongs to
        self.factory = factory           # async fn(emit) that runs the research
        self.status = "queued"           # queued -> running -> done | error | cancelled
        self.events: List[dict] = []
        self.listeners: List[asyncio.Queue] = []
        self.task: Optional[asyncio.Task] = None
        self.created = time.time()
        self.finished_at: Optional[float] = None

    async def emit(self, ev: dict) -> None:
        self.events.append(ev)
        for q in list(self.listeners):
            q.put_nowait(ev)

    def end(self, status: str) -> None:
        self.status = status
        self.finished_at = time.time()
        for q in list(self.listeners):
            q.put_nowait(None)
        _changed()

    @property
    def finished(self) -> bool:
        return self.status in ("done", "error", "cancelled")

    def public(self, position: int = 0) -> dict:
        return {"id": self.id, "query": self.query, "mode": self.mode, "status": self.status, "kind": self.kind,
                "ref": self.ref, "created": self.created, "finished": self.finished_at, "position": position}


RUNS: Dict[str, Run] = {}
_order: List[str] = []
_hooks: List[Callable[[], None]] = []
_loop: Optional[asyncio.AbstractEventLoop] = None


def on_change(fn: Callable[[], None]) -> None:
    """Call fn whenever a job starts, finishes or is cancelled (used for the Android notification)."""
    _hooks.append(fn)


def _changed() -> None:
    for fn in list(_hooks):
        try:
            fn()
        except Exception:
            log.exception("job change hook failed")


def _cleanup() -> None:
    now = time.time()
    for rid in [r for r, run in RUNS.items() if run.finished and now - (run.finished_at or now) > KEEP_FINISHED]:
        RUNS.pop(rid, None)
        if rid in _order:
            _order.remove(rid)


def _limit(kind: str) -> int:
    return LIMITS.get(kind, MAX_PARALLEL)


def _schedule() -> None:
    running: Dict[str, int] = {}
    for r in RUNS.values():
        if r.status == "running":
            running[r.kind] = running.get(r.kind, 0) + 1
    started = False
    for rid in list(_order):
        run = RUNS.get(rid)
        if run and run.status == "queued" and running.get(run.kind, 0) < _limit(run.kind):
            run.status = "running"
            run.task = asyncio.create_task(_execute(run))
            running[run.kind] = running.get(run.kind, 0) + 1
            started = True
    if started:
        _changed()


async def _execute(run: Run) -> None:
    status = "done"
    try:
        await run.factory(run.emit)
        if any(e.get("type") == "error" for e in run.events[-1:]):
            status = "error"
    except asyncio.CancelledError:
        status = "cancelled"
        await run.emit({"type": "cancelled"})
    except Exception as e:
        log.exception("search failed")
        status = "error"
        await run.emit({"type": "error", "message": str(e) or type(e).__name__})
    finally:
        run.end(status)
        if run.id in _order:
            _order.remove(run.id)
        _schedule()


def start(rid: str, query: str, mode: str, factory: Callable, kind: str = "search", ref: str = "") -> Run:
    global _loop
    _loop = asyncio.get_running_loop()
    _cleanup()
    old = RUNS.get(rid)
    if old and old.finished:          # same id again (e.g. rebuilding an explainer): replace the old job
        RUNS.pop(rid)
        if rid in _order:
            _order.remove(rid)
    run = Run(rid, query, mode, factory, kind, ref)
    RUNS[rid] = run
    _order.append(rid)
    position = sum(1 for r in RUNS.values() if not r.finished and r.kind == kind) - 1
    base = {"id": rid, "query": query, "mode": mode}
    run.events.append({"type": "queued", "position": position, **base} if position else {"type": "accepted", **base})
    _schedule()
    _changed()
    return run


def cancel(rid: str) -> bool:
    run = RUNS.get(rid)
    if not run or run.finished:
        return False
    if run.status == "queued":
        ev = {"type": "cancelled"}
        run.events.append(ev)
        for q in list(run.listeners):
            q.put_nowait(ev)
        run.end("cancelled")
        if rid in _order:
            _order.remove(rid)
        return True
    if run.task:
        run.task.cancel()
    return True


def active() -> List[dict]:
    _cleanup()
    out = []
    queued: Dict[str, int] = {}
    for rid in _order:
        run = RUNS.get(rid)
        if run and not run.finished:
            out.append(run.public(queued.get(run.kind, 0) + 1 if run.status == "queued" else 0))
            if run.status == "queued":
                queued[run.kind] = queued.get(run.kind, 0) + 1
    return out


def recent() -> List[dict]:
    """Jobs that finished in the last few minutes (for the "something finished" dot)."""
    return [r.public() for r in sorted(RUNS.values(), key=lambda r: r.finished_at or 0) if r.finished]


def find(kind: str, ref: str) -> Optional[Run]:
    """The newest job of this kind for this record, running or recently finished."""
    hits = [r for r in RUNS.values() if r.kind == kind and r.ref == ref]
    return max(hits, key=lambda r: r.created) if hits else None


def cancel_all_threadsafe() -> None:
    """Cancel everything from another thread (the Android notification's Cancel button)."""
    if _loop is None:
        return
    def go():
        for rid in list(_order):
            cancel(rid)
    _loop.call_soon_threadsafe(go)


async def follow(run: Run):
    """Everything that happened so far, then new events until the search ends.
    Leaving (closing the stream) doesn't stop the search."""
    q: asyncio.Queue = asyncio.Queue()
    run.listeners.append(q)          # register first, then take the snapshot: nothing is missed or sent twice
    seen = len(run.events)
    finished = run.finished
    try:
        for ev in run.events[:seen]:
            yield ev
        if finished:
            return
        while True:
            ev = await q.get()
            if ev is None:
                return
            yield ev
    finally:
        if q in run.listeners:
            run.listeners.remove(q)
