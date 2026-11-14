"""Fluid-property model interface.

The hydraulic solver in Release 1 assumes properties that do NOT vary along
the flow path (incompressible, constant viscosity). A model that varies with
P and T must therefore be paired with a marching solver (Release 2); the
``is_constant_property`` flag lets the engine refuse an incompatible pairing
instead of silently producing an inconsistent answer.

Extension point: petroleum PVT (black-oil correlations, EOS packages) and
CoolProp adapters implement this protocol.
"""

from __future__ import annotations

from typing import Protocol


class FluidModel(Protocol):
    name: str
    is_constant_property: bool

    def density(self, p_pa: float, t_k: float) -> float:
        """kg/m3"""

    def viscosity(self, p_pa: float, t_k: float) -> float:
        """Pa.s"""

    def specific_heat(self, p_pa: float, t_k: float) -> float:
        """J/(kg K), isobaric"""

    def thermal_expansion(self, p_pa: float, t_k: float) -> float:
        """1/K, volumetric"""

    def bubble_point_pressure(self, t_k: float) -> float:
        """Pa abs. Single-phase validity limit."""
