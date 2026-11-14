"""Generic inherent flow characteristics: relative capacity f(x), x in [0, 1].

These are textbook idealisations (cf. ISA-75.11 inherent characteristics),
NOT manufacturer data. All satisfy f(0) = 0 and f(1) = 1 and are monotonic,
which the network solver relies on.

    linear             f = x
    quick_opening      f = sqrt(x)
    equal_percentage   f = (R^x - 1) / (R - 1)

The equal-percentage form used here is the "modified" variant that reaches
exactly zero at x = 0 (the pure form R^(x-1) never closes); for x >~ 0.2 it
is close to the pure form. R is the rangeability.
"""

from __future__ import annotations

import math
from typing import Callable, Literal

Characteristic = Literal["linear", "quick_opening", "equal_percentage"]


def relative_capacity(kind: Characteristic, x: float, rangeability: float = 30.0) -> float:
    if not 0.0 <= x <= 1.0:
        raise ValueError(f"relative travel must be in [0, 1], got {x}")
    if kind == "linear":
        return x
    if kind == "quick_opening":
        return math.sqrt(x)
    if kind == "equal_percentage":
        r = rangeability
        return (r**x - 1.0) / (r - 1.0)
    raise ValueError(f"unknown characteristic {kind!r}")


CHARACTERISTIC_DESCRIPTIONS: dict[str, str] = {
    "linear": "f(x) = x (generic linear; also used for gate-valve travel)",
    "quick_opening": "f(x) = sqrt(x) (generic quick-opening)",
    "equal_percentage": "f(x) = (R^x - 1)/(R - 1) (generic modified equal-percentage)",
}

CharacteristicFn = Callable[[float], float]
