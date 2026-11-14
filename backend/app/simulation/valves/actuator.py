"""Valve actuator: commanded vs actual position with rate-limited travel.

The actual position moves toward the commanded position at a constant rate
100 % / full_stroke_time. This represents actuator travel time only - it is
NOT a hydraulic transient model (pressure/flow are recomputed quasi-steadily
for each intermediate position).
"""

from __future__ import annotations

from dataclasses import dataclass

POSITION_TOLERANCE_PCT = 1e-9
#: Snap to target when within this travel of it (removes float residue so
#: that a 'closed' valve is exactly 0 %, never 1e-14 %).
SNAP_PCT = 1e-9


@dataclass
class Actuator:
    position_pct: float
    commanded_pct: float
    full_stroke_time_s: float

    def __post_init__(self) -> None:
        if not self.full_stroke_time_s > 0:
            raise ValueError("full stroke time must be positive")

    @property
    def rate_pct_per_s(self) -> float:
        return 100.0 / self.full_stroke_time_s

    @property
    def is_moving(self) -> bool:
        return abs(self.commanded_pct - self.position_pct) > POSITION_TOLERANCE_PCT

    def step(self, dt: float) -> None:
        if dt <= 0 or not self.is_moving:
            return
        delta = self.commanded_pct - self.position_pct
        travel = self.rate_pct_per_s * dt
        if abs(delta) <= travel + SNAP_PCT:
            self.position_pct = self.commanded_pct
        else:
            self.position_pct += travel if delta > 0 else -travel

    def time_to_target(self) -> float:
        return abs(self.commanded_pct - self.position_pct) / self.rate_pct_per_s
