"""Production choke restriction model.

Capacity at relative opening x:

    C(x) = C_max * f(x),   C_max from Cv_max (see core.units.cv_to_capacity)

with f a generic inherent characteristic (default modified equal-percentage).
Because f is nonlinear AND the choke acts in series with the inflow, tubing,
and flowline resistances, 50 % opening does NOT give 50 % of maximum flow.

Extension point: replace ``capacity`` with a lookup of manufacturer Cv vs
step data, or a multiphase critical/sub-critical choke correlation
(Release 2/3). Release 1 does NOT model choked (critical) flow, cavitation
or flashing; diagnostics warn when the operating point approaches them.
"""

from __future__ import annotations

from app.core.units import cv_to_capacity
from app.simulation.valves.characteristics import Characteristic, relative_capacity


def choke_capacity(cv_max: float, position_pct: float, characteristic: Characteristic, rangeability: float) -> float:
    return cv_to_capacity(cv_max) * relative_capacity(characteristic, position_pct / 100.0, rangeability)
