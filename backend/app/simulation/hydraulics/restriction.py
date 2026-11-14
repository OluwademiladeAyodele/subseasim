"""Incompressible restriction (orifice-type) relation.

    Q = C sqrt(2 dP / rho),   C = Cd * A_eff   [m2]
 => dP = rho Q|Q| / (2 C^2)

Assumptions: incompressible single-phase liquid, turbulent (Re-independent)
discharge coefficient, no cavitation / flashing (checked by diagnostics),
pressure recovery folded into C. A closed restriction (C = 0) carries no
flow and is handled topologically by the network solver, never by dividing
by zero here.
"""

from __future__ import annotations


def restriction_pressure_drop(q: float, rho: float, capacity: float) -> float:
    if capacity <= 0:
        raise ValueError("restriction pressure drop requested for a closed restriction")
    return rho * q * abs(q) / (2.0 * capacity * capacity)


def restriction_flow(dp: float, rho: float, capacity: float) -> float:
    """Inverse relation (signed). Used in tests and diagnostics."""
    if capacity <= 0:
        return 0.0
    sign = 1.0 if dp >= 0 else -1.0
    return sign * capacity * (2.0 * abs(dp) / rho) ** 0.5
