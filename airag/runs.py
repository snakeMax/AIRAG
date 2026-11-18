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
LIMITS = {"search": 1, "explainer": 1, "tool": 2}
# AI tools on an article (follow-ups, rewrites, summaries, translations, image analysis, calculations):
# queued in their own group, two at a time; they show in the activity bar like searches
TOOL_KINDS = ("followup", "rewrite", "image", "translate", "summary", "calc")
MAX_WAITING = 30          # running + waiting jobs at most, so a stuck button can't queue up paid work
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
        last = self.events[-1] if self.events else None
        if (ev.get("type") == "token" and last is not None and last.get("type") == "token" and len(ev) == 2
                and len(last) == 2 and len(last.get("text", "")) < 4000):
            # streamed text: stored as one growing piece (the page only appends it), sent live word by word
            self.events[-1] = {"type": "token", "text": last["text"] + ev.get("text", "")}
        else:
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
        out = {"id": self.id, "query": self.query, "mode": self.mode, "status": self.status, "kind": self.kind,
               "ref": self.ref, "created": self.created, "finished": self.finished_at, "position": position}
        if self.status == "error":
            out["message"] = next((e.get("message", "") for e in reversed(self.events) if e.get("type") == "error"), "")
        return out


class TooManyJobs(RuntimeError):
    pass


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


GROUPS = {"more": "search", "regenerate": "search", **{k: "tool" for k in TOOL_KINDS}}
# "Locate more sources" and "Regenerate" write the article like a search does: they wait in the search queue


def _group(kind: str) -> str:
    return GROUPS.get(kind, kind)


def _limit(kind: str) -> int:
    return LIMITS.get(_group(kind), MAX_PARALLEL)


def _schedule() -> None:
    running: Dict[str, int] = {}
    for r in RUNS.values():
        if r.status == "running":
            running[_group(r.kind)] = running.get(_group(r.kind), 0) + 1
    started = False
    for rid in list(_order):
        run = RUNS.get(rid)
        if run and run.status == "queued" and running.get(_group(run.kind), 0) < _limit(run.kind):
            run.status = "running"
            run.task = asyncio.create_task(_execute(run))
            running[_group(run.kind)] = running.get(_group(run.kind), 0) + 1
            started = True
    if started:
        _changed()


async def _execute(run: Run) -> None:
    status = "done"
    try:
        from . import usage
        usage.check_budget()                # checked when the job starts (not while it waits in the queue)...
        usage.let_running_work_finish()     # ...then it may finish even if it crosses the budget
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
    if old and not old.finished:      # pressed twice: the job is already running or waiting, don't do it twice
        return old
    if old and old.finished:          # same id again (e.g. rebuilding an explainer): replace the old job
        RUNS.pop(rid)
        if rid in _order:
            _order.remove(rid)
    if sum(1 for r in RUNS.values() if not r.finished) >= MAX_WAITING:
        raise TooManyJobs("There are already many tasks waiting. Let some finish (or cancel them) first.")
    run = Run(rid, query, mode, factory, kind, ref)
    RUNS[rid] = run
    _order.append(rid)
    position = sum(1 for r in RUNS.values() if not r.finished and _group(r.kind) == _group(kind)) - 1
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
            g = _group(run.kind)
            out.append(run.public(queued.get(g, 0) + 1 if run.status == "queued" else 0))
            if run.status == "queued":
                queued[g] = queued.get(g, 0) + 1
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
