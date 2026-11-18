"""Searches that keep going when you leave the page.

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

MAX_PARALLEL = 1          # one search at a time keeps the AI provider's rate limits and the phone's battery happy
KEEP_FINISHED = 600       # seconds a finished search stays here (after that it's only in history)


class Run:
    def __init__(self, rid: str, query: str, mode: str, factory: Callable):
        self.id, self.query, self.mode = rid, query, mode
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

    @property
    def finished(self) -> bool:
        return self.status in ("done", "error", "cancelled")

    def public(self, position: int = 0) -> dict:
        return {"id": self.id, "query": self.query, "mode": self.mode, "status": self.status,
                "created": self.created, "position": position}


RUNS: Dict[str, Run] = {}
_order: List[str] = []


def _cleanup() -> None:
    now = time.time()
    for rid in [r for r, run in RUNS.items() if run.finished and now - (run.finished_at or now) > KEEP_FINISHED]:
        RUNS.pop(rid, None)
        if rid in _order:
            _order.remove(rid)


def _schedule() -> None:
    running = sum(1 for r in RUNS.values() if r.status == "running")
    for rid in list(_order):
        if running >= MAX_PARALLEL:
            break
        run = RUNS.get(rid)
        if run and run.status == "queued":
            run.status = "running"
            run.task = asyncio.create_task(_execute(run))
            running += 1


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


def start(rid: str, query: str, mode: str, factory: Callable) -> Run:
    _cleanup()
    run = Run(rid, query, mode, factory)
    RUNS[rid] = run
    _order.append(rid)
    position = sum(1 for r in RUNS.values() if not r.finished) - 1
    base = {"id": rid, "query": query, "mode": mode}
    run.events.append({"type": "queued", "position": position, **base} if position else {"type": "accepted", **base})
    _schedule()
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
    queued = 0
    for rid in _order:
        run = RUNS.get(rid)
        if run and not run.finished:
            out.append(run.public(queued if run.status == "queued" else 0))
            if run.status == "queued":
                queued += 1
    return out


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
