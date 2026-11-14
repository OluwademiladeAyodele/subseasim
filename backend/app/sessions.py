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

    def create(self, scenario_id: str) -> Session:
        self._expire_idle()
        if len(self.sessions) >= self.settings.max_sessions:
            raise SessionLimitReached("maximum number of concurrent sessions reached")
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

    async def tick(self, elapsed_wall_s: float) -> None:
        for s in list(self.sessions.values()):
            if s.engine.status == "running":
                s.engine.advance(elapsed_wall_s * s.engine.time_scale)
                s.update_training()
                await s.broadcast()

    async def run(self) -> None:
        period = self.settings.tick_period_s
        last = time.monotonic()
        while True:
            await asyncio.sleep(period)
            now = time.monotonic()
            elapsed = min(now - last, period * MAX_TICK_CREDIT_FACTOR)
            last = now
            try:
                await self.tick(elapsed)
            except Exception:  # noqa: BLE001 - keep the loop alive; error is logged
                log.exception("simulation tick failed")

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
