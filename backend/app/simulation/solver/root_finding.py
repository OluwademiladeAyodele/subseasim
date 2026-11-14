"""Numerical root finding for the hydraulic operating point."""

from __future__ import annotations

from dataclasses import dataclass
import sys
from typing import Callable

from scipy.optimize import brentq

#: Absolute flow tolerance for Brent's method [m3/s]. Deliberately tiny so
#: that convergence is governed by the RELATIVE tolerance: flows through an
#: almost-closed restriction can be orders of magnitude below 1e-12 m3/s and
#: must still be resolved to full relative precision for the pressure
#: residual to close.
XTOL_M3S = 1e-300
#: Relative flow tolerance (scipy's minimum, 4 * machine epsilon).
RTOL = 4 * sys.float_info.epsilon
#: Maximum Brent iterations.
MAX_ITER = 200


class SolverError(RuntimeError):
    pass


@dataclass
class RootResult:
    x: float
    iterations: int
    function_calls: int
    residual: float
    converged: bool


def solve_bracketed(fn: Callable[[float], float], lo: float, hi: float) -> RootResult:
    """Solve fn(x) = 0 on [lo, hi]; fn(lo) and fn(hi) must differ in sign."""
    f_lo, f_hi = fn(lo), fn(hi)
    if f_lo == 0.0:
        return RootResult(lo, 0, 2, 0.0, True)
    if f_hi == 0.0:
        return RootResult(hi, 0, 2, 0.0, True)
    if f_lo * f_hi > 0:
        raise SolverError(f"root not bracketed: f({lo})={f_lo}, f({hi})={f_hi}")
    x, info = brentq(fn, lo, hi, xtol=XTOL_M3S, rtol=RTOL, maxiter=MAX_ITER, full_output=True, disp=False)
    return RootResult(x=x, iterations=info.iterations, function_calls=info.function_calls, residual=fn(x), converged=bool(info.converged))
