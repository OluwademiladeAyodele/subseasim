"""Pipe segment hydraulics (tubing, jumper or flowline).

Pressure drop in the flow direction:

    dP = rho g (z_out - z_in) + dP_friction(Q)

Elevation from node elevations (straight-line TVD change between the two
nodes; the measured length may be longer). Constant density => the
hydrostatic term is exact for the model.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.core.units import G
from app.simulation.hydraulics.friction import friction_pressure_drop, reynolds


@dataclass
class PipeGeometry:
    length: float  # m, measured
    diameter: float  # m, inner
    roughness: float  # m, absolute
    dz: float  # m, outlet minus inlet elevation

    @property
    def area(self) -> float:
        return math.pi * self.diameter**2 / 4.0

    @property
    def volume(self) -> float:
        return self.area * self.length

    def __post_init__(self) -> None:
        if abs(self.dz) > self.length + 1e-6:
            raise ValueError(f"elevation change {self.dz} m exceeds pipe length {self.length} m")


def hydrostatic_dp(rho: float, dz: float) -> float:
    return rho * G * dz


def pipe_pressure_drop(q: float, rho: float, mu: float, geom: PipeGeometry) -> float:
    return hydrostatic_dp(rho, geom.dz) + friction_pressure_drop(q, rho, mu, geom.diameter, geom.length, geom.roughness)


def pipe_reynolds(q: float, rho: float, mu: float, geom: PipeGeometry) -> float:
    return reynolds(rho, q / geom.area, geom.diameter, mu)
