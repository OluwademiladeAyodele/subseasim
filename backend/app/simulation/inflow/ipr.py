"""Reservoir inflow-performance relationship (IPR).

Release 1: linear (constant productivity index) IPR

    Q = J (P_res - P_wf)          [m3/s],  J in (m3/s)/Pa

Valid for single-phase liquid inflow above the bubble point (the regime in
which Vogel-type corrections are unnecessary). The same J is applied to
reverse flow (injectivity == productivity) - an explicit simplification that
the diagnostics module reports whenever reverse flow occurs.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class LinearIPR:
    p_res: float  # Pa abs (static reservoir pressure at the datum)
    j: float  # (m3/s)/Pa
    t_res: float  # K

    def __post_init__(self) -> None:
        if not self.j > 0:
            raise ValueError("productivity index must be positive")
        if not self.p_res > 0:
            raise ValueError("reservoir pressure must be positive (absolute)")

    def drawdown(self, q: float) -> float:
        """P_res - P_wf for a given flow [Pa]. Signed (negative = injection)."""
        return q / self.j

    def flowing_bottomhole_pressure(self, q: float) -> float:
        return self.p_res - self.drawdown(q)
