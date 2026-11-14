"""Time-integration helpers.

Simulation time is advanced in fixed-size sub-steps that are independent of
the wall-clock tick and of browser rendering. ``substeps`` splits an interval
into equal steps no larger than ``max_dt``.

The thermal model uses backward (implicit) Euler, which is unconditionally
stable for the linear cell equations, so sub-step size affects accuracy only.
"""

from __future__ import annotations

import math


def substeps(dt_total: float, max_dt: float) -> list[float]:
    if dt_total <= 0:
        return []
    if max_dt <= 0:
        raise ValueError("max_dt must be positive")
    n = max(1, math.ceil(dt_total / max_dt - 1e-12))
    return [dt_total / n] * n


def implicit_euler_cell(t_old: float, t_upstream: float, t_ambient: float, cap: float, adv: float, loss: float, dt: float | None) -> float:
    """One backward-Euler step of a well-mixed cell

        cap dT/dt = adv (T_up - T) + loss (T_amb - T)

    cap = M cp [J/K], adv = mdot cp [W/K], loss = U A [W/K].
    ``dt=None`` returns the steady-state solution (dT/dt = 0).
    """
    if dt is not None and dt <= 0.0:
        return t_old  # no time elapsed: stored energy unchanged
    storage = 0.0 if dt is None else cap / dt
    denom = storage + adv + loss
    if denom <= 0.0:
        return t_old  # adiabatic, stagnant, steady: temperature undefined -> unchanged
    return (storage * t_old + adv * t_upstream + loss * t_ambient) / denom
