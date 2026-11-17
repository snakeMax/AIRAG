"""Background jobs with progress (model downloads, browser install, library indexing, updates).

    job = start("browser-install", my_coroutine_fn)   # fn(job) -> awaitable
    GET /api/jobs/<id>  -> {status, progress, message, detail, ...}

Only one job per key runs at a time; starting it again returns the running one.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Awaitable, Callable, Dict, Optional

log = logging.getLogger("airag.jobs")


class Job:
    def __init__(self, key: str):
        self.id = uuid.uuid4().hex[:12]
        self.key = key
        self.status = "running"     # running | done | error | cancelled
        self.progress: Optional[float] = None
        self.message = ""
        self.detail = ""
        self.error = ""
        self.result = None
        self.extra: dict = {}
        self.started = time.time()
        self.finished: Optional[float] = None
        self.cancelled = False
        self.task: Optional[asyncio.Task] = None

    def public(self) -> dict:
        return {"id": self.id, "key": self.key, "status": self.status, "progress": self.progress,
                "message": self.message, "detail": self.detail, "error": self.error, "result": self.result,
                "extra": self.extra, "started": self.started, "finished": self.finished}


JOBS: Dict[str, Job] = {}


def running(key: str) -> Optional[Job]:
    for j in JOBS.values():
        if j.key == key and j.status == "running":
            return j
    return None


def start(key: str, fn: Callable[[Job], Awaitable[object]]) -> Job:
    existing = running(key)
    if existing:
        return existing
    job = Job(key)
    JOBS[job.id] = job

    async def runner():
        try:
            job.result = await fn(job)
            job.status = "cancelled" if job.cancelled else "done"
            if job.progress is not None:
                job.progress = 1.0
        except asyncio.CancelledError:
            job.status = "cancelled"
        except Exception as e:
            log.exception("job %s failed", key)
            job.status, job.error = "error", str(e) or type(e).__name__
        finally:
            job.finished = time.time()
            _prune()

    job.task = asyncio.get_running_loop().create_task(runner())
    return job


def start_thread(key: str, fn: Callable[[Job], object]) -> Job:
    """Same as start() for blocking functions (run in a worker thread)."""
    async def wrapper(job: Job):
        return await asyncio.to_thread(fn, job)
    return start(key, wrapper)


def cancel(job_id: str) -> bool:
    j = JOBS.get(job_id)
    if not j or j.status != "running":
        return False
    j.cancelled = True
    if j.task:
        j.task.cancel()
    return True


def _prune(keep: int = 50) -> None:
    done = sorted((j for j in JOBS.values() if j.status != "running"), key=lambda j: j.finished or 0)
    for j in done[:-keep]:
        JOBS.pop(j.id, None)
