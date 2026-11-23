"""Background jobs for long calculations (fast-forward, scenario studies).

The server runs every session on ONE asyncio event loop with no locking
(see app/sessions.py), so jobs are COOPERATIVE: a job is a generator that
does a small step of work per ``next()`` and yields ``(progress, message)``.
The runner executes steps for at most ``SLICE_S`` of wall time, then yields
to the event loop so the simulation loop, the API and other jobs keep
running. Jobs therefore never race the simulation and need no locks.

States: pending -> running -> completed | failed | cancelled. Cancelling
closes the generator; the work function decides (and reports) what is kept.
One active job per session.
"""

from __future__ import annotations

import asyncio
import itertools
import time
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime

SLICE_S = 0.03
BROADCAST_EVERY_S = 0.5
KEEP_PER_SESSION = 20

Step = tuple[float, str]
_seq = itertools.count(1)


class JobRejected(RuntimeError):
    pass


class JobAborted(RuntimeError):
    """Raised by a work generator when the job can no longer continue."""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass
class Job:
    session_id: str
    kind: str
    label: str
    params: dict
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    #: Submission order (timestamps have 1 s resolution, so they cannot order jobs).
    seq: int = field(default_factory=lambda: next(_seq))
    state: str = "pending"
    progress: float = 0.0
    message: str = "queued"
    created_at: str = field(default_factory=_now)
    started_at: str | None = None
    finished_at: str | None = None
    result: dict | None = None
    error: str | None = None
    cancel_requested: bool = False
    wall_s: float = 0.0

    @property
    def active(self) -> bool:
        return self.state in ("pending", "running")

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in ("id", "session_id", "kind", "label", "params", "state", "progress", "message",
                                               "created_at", "started_at", "finished_at", "result", "error", "wall_s")}


#: kind -> factory(session, params) -> (label, generator). The factory validates
#: the request (raising JobRejected) BEFORE anything is queued.
Factory = Callable[[object, dict], tuple[str, Iterator[Step]]]


class JobManager:
    def __init__(self) -> None:
        self.jobs: dict[str, Job] = {}
        self.kinds: dict[str, Factory] = {}
        self._tasks: dict[str, asyncio.Task] = {}

    def register(self, kind: str, factory: Factory) -> None:
        self.kinds[kind] = factory

    def for_session(self, sid: str) -> list[Job]:
        return sorted((j for j in self.jobs.values() if j.session_id == sid), key=lambda j: j.seq, reverse=True)

    def get(self, jid: str) -> Job:
        try:
            return self.jobs[jid]
        except KeyError:
            raise KeyError(f"job {jid} not found") from None

    def submit(self, session, kind: str, params: dict, is_alive: Callable[[], bool] | None = None) -> Job:
        if kind not in self.kinds:
            raise JobRejected(f"unknown job kind '{kind}' (available: {', '.join(sorted(self.kinds))})")
        sid = session.id
        if any(j.active for j in self.for_session(sid)):
            raise JobRejected("another job is already running for this session - wait for it or cancel it")
        label, gen = self.kinds[kind](session, params)
        job = Job(session_id=sid, kind=kind, label=label, params=params)
        self.jobs[job.id] = job
        self._prune(sid)
        self._tasks[job.id] = asyncio.get_running_loop().create_task(self._run(job, gen, session, is_alive))
        return job

    def cancel(self, jid: str) -> Job:
        job = self.get(jid)
        if job.active:
            job.cancel_requested = True
            job.message = "cancelling"
        return job

    def cancel_session(self, sid: str) -> None:
        for j in self.for_session(sid):
            if j.active:
                j.cancel_requested = True

    def _prune(self, sid: str) -> None:
        done = [j for j in self.for_session(sid) if not j.active]
        for j in done[KEEP_PER_SESSION:]:
            self.jobs.pop(j.id, None)

    async def _run(self, job: Job, gen: Iterator[Step], session, is_alive) -> None:
        job.state, job.started_at, job.message = "running", _now(), "started"
        t_start = time.perf_counter()
        last_push = t_start
        try:
            while True:
                if job.cancel_requested or (is_alive is not None and not is_alive()):
                    gen.close()  # the work function reports what is kept (GeneratorExit)
                    job.state = "cancelled"
                    job.message = ("cancelled by the user" if job.cancel_requested else "cancelled: the session ended") + \
                        (f" at {job.progress * 100:.0f} %" if job.progress else "")
                    break
                t0 = time.perf_counter()
                try:
                    while time.perf_counter() - t0 < SLICE_S:
                        job.progress, job.message = next(gen)
                except StopIteration as stop:
                    job.state, job.progress = "completed", 1.0
                    job.result = stop.value if isinstance(stop.value, dict) else None
                    job.message = (job.result or {}).get("message", "completed")
                    break
                now = time.perf_counter()
                if now - last_push >= BROADCAST_EVERY_S:
                    last_push = now
                    await _push(session)
                await asyncio.sleep(0)
        except JobAborted as exc:
            job.state, job.error, job.message = "failed", str(exc), f"failed: {exc}"
        except Exception as exc:  # noqa: BLE001 - a job must never take the server down
            job.state, job.error, job.message = "failed", f"{type(exc).__name__}: {exc}", "failed"
        finally:
            job.finished_at = _now()
            job.wall_s = time.perf_counter() - t_start
            self._tasks.pop(job.id, None)
            await _push(session)

    async def wait(self, jid: str) -> Job:
        """Await completion (tests / synchronous API)."""
        t = self._tasks.get(jid)
        if t is not None:
            await t
        return self.get(jid)


async def _push(session) -> None:
    b = getattr(session, "broadcast", None)
    if b is not None:
        try:
            await b()
        except Exception:  # noqa: BLE001 - a closed socket must not fail the job
            pass


jobs = JobManager()
