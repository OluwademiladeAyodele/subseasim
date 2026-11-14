"""Fluid properties as seen by the hydraulic solver.

The Release 1 network solver requires properties that are uniform along the
flow path. ``FlowProperties.from_fluid`` refuses fluid models that are not
constant-property, rather than silently evaluating them at an arbitrary
point (which would make the hydraulic result inconsistent).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.simulation.fluid_properties.base import FluidModel


@dataclass(frozen=True)
class FlowProperties:
    rho: float  # kg/m3
    mu: float  # Pa.s

    @classmethod
    def from_fluid(cls, fluid: FluidModel) -> "FlowProperties":
        if not fluid.is_constant_property:
            raise NotImplementedError(
                "The Release 1 series solver supports constant-property fluids only; "
                "a P/T-dependent fluid requires the marching solver (planned Release 2)."
            )
        # Any (P, T) gives the same value for a constant-property model.
        return cls(rho=fluid.density(0.0, 0.0), mu=fluid.viscosity(0.0, 0.0))
