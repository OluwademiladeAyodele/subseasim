"""Simulation-state containers: event log and trend history."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import asdict, dataclass, field
from typing import Literal

EventCategory = Literal["operation", "lifecycle", "boundary", "fluid", "outcome", "training_rule", "rejected", "training", "scenario"]
SimStatus = Literal["ready", "running", "paused"]


@dataclass
class Event:
    id: int
    sim_time_s: float
    wall_time: float
    category: EventCategory
    message: str
    component: str | None = None
    severity: Literal["info", "warning", "error"] = "info"
    detail: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class EventLog:
    maxlen: int
    _events: deque = field(init=False)
    _seq: int = field(init=False, default=0)

    def __post_init__(self) -> None:
        self._events = deque(maxlen=self.maxlen)

    def add(self, sim_time_s: float, category: EventCategory, message: str, **kw) -> Event:
        self._seq += 1
        ev = Event(self._seq, sim_time_s, time.time(), category, message, **kw)
        self._events.append(ev)
        return ev

    @property
    def last_id(self) -> int:
        return self._seq

    def since(self, event_id: int) -> list[Event]:
        return [e for e in self._events if e.id > event_id]

    def all(self) -> list[Event]:
        return list(self._events)

    def clear(self) -> None:
        self._events.clear()


@dataclass
class History:
    """Trend samples produced by the engine (never synthesised)."""

    maxlen: int
    _samples: deque = field(init=False)
    _seq: int = field(init=False, default=0)

    def __post_init__(self) -> None:
        self._samples = deque(maxlen=self.maxlen)

    def add(self, sample: dict) -> None:
        self._seq += 1
        sample["seq"] = self._seq
        self._samples.append(sample)

    @property
    def last_seq(self) -> int:
        return self._seq

    def since(self, seq: int) -> list[dict]:
        return [s for s in self._samples if s["seq"] > seq]

    def all(self) -> list[dict]:
        return list(self._samples)

    def clear(self) -> None:
        self._samples.clear()
