"""Pipe-friction relations (single-phase, Newtonian, fully developed flow).

Darcy-Weisbach:   dP_f = f (L/D) rho v|v| / 2

Darcy friction factor f from Churchill (1977), "Friction-factor equation
spans all fluid-flow regimes", Chem. Eng. 84(24) 91-92:

    f = 8 [ (8/Re)^12 + (A + B)^-1.5 ]^(1/12)
    A = [ 2.457 ln( 1 / ((7/Re)^0.9 + 0.27 eps/D) ) ]^16
    B = (37530 / Re)^16

Chosen because it is a single continuous expression (laminar 64/Re limit,
turbulent Colebrook-like behaviour, smooth interpolation through transition)
which keeps the hydraulic residual continuous and monotonic for the root
finder. The transition region (2000 < Re < 4000) is physically uncertain
and is flagged by diagnostics.
"""

from __future__ import annotations

import math

RE_LAMINAR_LIMIT = 2000.0
RE_TURBULENT_LIMIT = 4000.0


def reynolds(rho: float, v: float, d: float, mu: float) -> float:
    return rho * abs(v) * d / mu


def churchill_friction_factor(re: float, rel_roughness: float) -> float:
    """Darcy friction factor. ``re`` must be > 0."""
    if re <= 0:
        raise ValueError("Reynolds number must be positive")
    a = (2.457 * math.log(1.0 / ((7.0 / re) ** 0.9 + 0.27 * rel_roughness))) ** 16
    b = (37530.0 / re) ** 16
    return 8.0 * ((8.0 / re) ** 12 + (a + b) ** -1.5) ** (1.0 / 12.0)


def colebrook_friction_factor(re: float, rel_roughness: float, tol: float = 1e-12) -> float:
    """Reference implicit Colebrook-White solution (turbulent only).

    Used by the validation tests as an independent reference; not used by
    the solver.
    """
    x = 0.02 ** -0.5
    for _ in range(100):
        x_new = -2.0 * math.log10(rel_roughness / 3.7 + 2.51 * x / re)
        if abs(x_new - x) < tol:
            break
        x = x_new
    return 1.0 / x_new**2


def friction_pressure_drop(q: float, rho: float, mu: float, d: float, length: float, roughness: float) -> float:
    """Signed frictional pressure drop in the flow direction [Pa]."""
    if q == 0.0:
        return 0.0
    area = math.pi * d * d / 4.0
    v = q / area
    re = reynolds(rho, v, d, mu)
    f = churchill_friction_factor(re, roughness / d)
    return f * (length / d) * rho * v * abs(v) / 2.0
