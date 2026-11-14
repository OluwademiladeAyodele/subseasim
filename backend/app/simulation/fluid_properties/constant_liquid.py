"""Constant-property single-phase liquid (Release 1 fluid model).

Represents an ILLUSTRATIVE undersaturated (or dead) oil, or water, with
density, viscosity and heat capacity independent of pressure and
temperature. Valid only while the local pressure stays above the configured
bubble-point pressure; the diagnostics module checks that.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ConstantPropertyLiquid:
    name: str
    rho: float  # kg/m3
    mu: float  # Pa.s
    cp: float  # J/(kg K)
    beta: float  # 1/K
    p_bubble: float  # Pa abs

    is_constant_property: bool = True

    def __post_init__(self) -> None:
        for label, v in (("density", self.rho), ("viscosity", self.mu), ("specific heat", self.cp)):
            if not v > 0:
                raise ValueError(f"{label} must be positive, got {v}")
        if self.beta < 0 or self.p_bubble < 0:
            raise ValueError("thermal expansion and bubble point must be non-negative")

    def density(self, p_pa: float, t_k: float) -> float:
        return self.rho

    def viscosity(self, p_pa: float, t_k: float) -> float:
        return self.mu

    def specific_heat(self, p_pa: float, t_k: float) -> float:
        return self.cp

    def thermal_expansion(self, p_pa: float, t_k: float) -> float:
        return self.beta

    def bubble_point_pressure(self, t_k: float) -> float:
        return self.p_bubble
