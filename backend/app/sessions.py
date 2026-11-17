"""Per-user simulation sessions and the backend simulation loop.

Each browser session owns an independent ``SimulationEngine`` so that
several interns on one internal server never share a simulation. A single
asyncio task advances every RUNNING session once per wall-clock tick by
``elapsed_wall_time * time_scale`` simulation seconds and pushes deltas to
the session's WebSocket clients. All engine access happens on the event-loop
thread (API routes are ``async``), so no locking is required.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field

from fastapi import WebSocket

from app.core.config import Settings, settings as default_settings
from app.scenarios.loader import get_scenario
from app.simulation.engine import SimulationEngine
from app.training.framework import TrainingSession
from app.training.registry import get_exercise

log = logging.getLogger("subseasim.sessions")

#: Max wall-clock interval credited in one tick (protects against stalls).
MAX_TICK_CREDIT_FACTOR = 4.0


class SessionLimitReached(RuntimeError):
    pass


@dataclass
class Session:
    id: str
    engine: SimulationEngine
    training: TrainingSession | None = None
    sockets: set[WebSocket] = field(default_factory=set)
    last_activity: float = field(default_factory=time.monotonic)
    #: Last time at least one WebSocket client was attached.
    last_watched: float = field(default_factory=time.monotonic)
    sent_event_id: int = 0
    sent_sample_seq: int = 0

    def touch(self) -> None:
        self.last_activity = time.monotonic()

    def update_training(self) -> None:
        if self.training is not None and self.training.update(self.engine):
            step = self.training.d.steps[self.training.index]
            self.engine.events.add(self.engine.time_s, "training", f"Training task complete: {step.title}")

    def payload(self, include_static: bool = True) -> dict:
        return {
            "session_id": self.id,
            "state": self.engine.snapshot(include_static=include_static),
            "training": self.training.state(self.engine) if self.training else None,
        }

    def start_training(self, exercise_id: str) -> None:
        ex = get_exercise(exercise_id)
        self.engine.load_scenario(get_scenario(ex.scenario_id))
        self.training = TrainingSession(ex)
        self.engine.events.add(0.0, "training", f"Training exercise started: {ex.title}")
        self.sent_event_id = 0
        self.sent_sample_seq = 0

    async def broadcast(self) -> None:
        if not self.sockets:
            self.sent_event_id = self.engine.events.last_id
            self.sent_sample_seq = self.engine.history.last_seq
            return
        msg = {
            "type": "update",
            **self.payload(include_static=False),
            "events": [e.to_dict() for e in self.engine.events.since(self.sent_event_id)],
            "samples": self.engine.history.since(self.sent_sample_seq),
        }
        self.sent_event_id = self.engine.events.last_id
        self.sent_sample_seq = self.engine.history.last_seq
        dead = []
        for ws in list(self.sockets):
            try:
                await ws.send_json(msg)
            except Exception:  # noqa: BLE001 - any send failure means the socket is gone
                dead.append(ws)
        for ws in dead:
            self.sockets.discard(ws)

    def init_message(self) -> dict:
        return {
            "type": "init",
            **self.payload(include_static=True),
            "events": [e.to_dict() for e in self.engine.events.all()],
            "samples": self.engine.history.all(),
        }


class SessionManager:
    def __init__(self, cfg: Settings = default_settings):
        self.settings = cfg
        self.sessions: dict[str, Session] = {}
        self._task: asyncio.Task | None = None
        #: loop health (exposed by /api/health)
        self.metrics: dict = {"tick_ms": 0.0, "tick_ms_max": 0.0, "real_period_s": 0.0, "running": 0, "sockets": 0}

    def create(self, scenario_id: str) -> Session:
        self._expire_idle()
        if len(self.sessions) >= self.settings.max_sessions:
            # Full: reclaim the least-recently-used session that nobody is
            # watching (abandoned tabs, closed browsers). Refuse only when
            # every session has a live browser attached.
            idle = [s for s in self.sessions.values() if not s.sockets]
            if not idle:
                raise SessionLimitReached(
                    f"the training server is at capacity ({self.settings.max_sessions} active sessions with a browser attached)"
                )
            oldest = min(idle, key=lambda s: s.last_activity)
            del self.sessions[oldest.id]
            log.info("session %s evicted (LRU, no browser attached) to admit a new session", oldest.id)
        sid = uuid.uuid4().hex
        s = Session(sid, SimulationEngine(get_scenario(scenario_id), self.settings))
        self.sessions[sid] = s
        return s

    def get(self, sid: str) -> Session:
        s = self.sessions[sid]
        s.touch()
        return s

    def _expire_idle(self) -> None:
        now = time.monotonic()
        for sid, s in list(self.sessions.items()):
            if not s.sockets and now - s.last_activity > self.settings.session_idle_timeout_s:
                del self.sessions[sid]

    async def tick(self, elapsed_wall_s: float, real_wall_s: float | None = None) -> None:
        """Advance every running session by ``elapsed_wall_s`` x speed.
        ``real_wall_s`` is the true time since the last tick (the credit may be
        capped); the achieved speed is measured against it, so a slow loop is
        reported honestly."""
        real = real_wall_s if real_wall_s is not None else elapsed_wall_s
        now = time.monotonic()
        for s in list(self.sessions.values()):
            if s.sockets:
                s.last_watched = now
            elif s.engine.status == "running" and now - max(s.last_watched, s.last_activity) > self.settings.orphan_pause_s:
                # no browser attached AND no API activity: nobody is using it
                s.engine.pause()
                s.engine.events.add(
                    s.engine.time_s, "lifecycle",
                    f"Simulation paused automatically: no browser connected for {self.settings.orphan_pause_s:.0f} s",
                )
            if s.engine.status == "running":
                t0 = s.engine.time_s
                s.engine.advance(elapsed_wall_s * s.engine.time_scale)
                if real > 0:
                    inst = (s.engine.time_s - t0) / real
                    prev = s.engine.achieved_speed
                    # smoothed simulated-seconds per wall-second actually achieved
                    s.engine.achieved_speed = inst if prev is None else 0.8 * prev + 0.2 * inst
                s.update_training()
                await s.broadcast()
                # yield between sessions so API requests are never starved
                await asyncio.sleep(0)
            else:
                s.engine.achieved_speed = None

    async def run(self) -> None:
        period = self.settings.tick_period_s
        last = time.monotonic()
        while True:
            await asyncio.sleep(period)
            now = time.monotonic()
            real = now - last
            elapsed = min(real, period * MAX_TICK_CREDIT_FACTOR)
            last = now
            t0 = time.perf_counter()
            try:
                await self.tick(elapsed, real)
            except Exception:  # noqa: BLE001 - keep the loop alive; error is logged
                log.exception("simulation tick failed")
            ms = (time.perf_counter() - t0) * 1000
            m = self.metrics
            m["tick_ms"] = 0.8 * m["tick_ms"] + 0.2 * ms
            m["tick_ms_max"] = max(m["tick_ms_max"] * 0.99, ms)
            m["real_period_s"] = real
            m["running"] = sum(1 for x in self.sessions.values() if x.engine.status == "running")
            m["sockets"] = sum(len(x.sockets) for x in self.sessions.values())

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self.run())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None


manager = SessionManager()
