"""Valve actuator: commanded vs actual position with rate-limited travel.

The actual position moves toward the commanded position at a constant rate

    opening:  100 % / full_stroke_time_s
    closing:  100 % / close_stroke_time_s   (defaults to the opening time)

after an optional dead time ``delay_s`` (control-system / hydraulic-signal
latency of a subsea control module). This is actuator kinematics only: the
hydraulic consequence of each intermediate position is calculated by the
hydraulic model (quasi-steady or dynamic) - the actuator never sets a
pressure or flow.

Phases:  idle -> delay -> travel -> idle
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

POSITION_TOLERANCE_PCT = 1e-9
#: Snap to target when within this travel of it (removes float residue so
#: that a 'closed' valve is exactly 0 %, never 1e-14 %).
SNAP_PCT = 1e-9

Phase = Literal["idle", "delay", "travel"]


@dataclass
class Actuator:
    position_pct: float
    commanded_pct: float
    full_stroke_time_s: float
    close_stroke_time_s: float | None = None
    delay_s: float = 0.0
    _delay_left: float = field(default=0.0, repr=False)

    def __post_init__(self) -> None:
        if not self.full_stroke_time_s > 0:
            raise ValueError("full stroke time must be positive")
        if self.close_stroke_time_s is not None and not self.close_stroke_time_s > 0:
            raise ValueError("close stroke time must be positive")
        if self.delay_s < 0:
            raise ValueError("actuation delay must be non-negative")

    @property
    def _closing(self) -> bool:
        return self.commanded_pct < self.position_pct

    @property
    def rate_pct_per_s(self) -> float:
        t = self.close_stroke_time_s if (self._closing and self.close_stroke_time_s) else self.full_stroke_time_s
        return 100.0 / t

    @property
    def is_moving(self) -> bool:
        """True while a command is being executed (dead time or travel)."""
        return abs(self.commanded_pct - self.position_pct) > POSITION_TOLERANCE_PCT

    @property
    def phase(self) -> Phase:
        if not self.is_moving:
            return "idle"
        return "delay" if self._delay_left > 0 else "travel"

    def command(self, target_pct: float) -> None:
        """Accept a new set point; a fresh command restarts the dead time."""
        if abs(target_pct - self.commanded_pct) < POSITION_TOLERANCE_PCT and self.is_moving:
            return
        self.commanded_pct = target_pct
        self._delay_left = self.delay_s if self.is_moving else 0.0

    def step(self, dt: float) -> None:
        if dt <= 0 or not self.is_moving:
            return
        if self._delay_left > 0:
            used = min(dt, self._delay_left)
            self._delay_left -= used
            dt -= used
            if dt <= 0:
                return
        delta = self.commanded_pct - self.position_pct
        travel = self.rate_pct_per_s * dt
        if abs(delta) <= travel + SNAP_PCT:
            self.position_pct = self.commanded_pct
        else:
            self.position_pct += travel if delta > 0 else -travel

    def time_to_target(self) -> float:
        return self._delay_left + abs(self.commanded_pct - self.position_pct) / self.rate_pct_per_s
