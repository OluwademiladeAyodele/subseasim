"""Release 1 thermal model.

Pipes (tubing, flowline) are divided into N well-mixed cells in series
("tanks-in-series" / upwind finite-volume). Energy balance per cell:

    M cp dT/dt = mdot cp (T_up - T) - U (pi D dL) (T - T_amb(z))

    M     = rho A dL       fluid mass in the cell (pipe-wall heat capacity
                            neglected -> cool-down is FASTER than reality)
    U     overall heat-transfer coefficient referred to the inner surface
    T_amb linear between the configured inlet/outlet ambient temperatures
          (geothermal profile in the tubing, seabed temperature for flowline)

Integrated with backward Euler (stable for any step). As N grows the
steady-state outlet temperature converges to the plug-flow solution

    T_out = T_amb + (T_in - T_amb) exp(-U pi D L / (mdot cp)).

Zero-volume restrictions (valves, choke) apply isenthalpic throttling of a
constant-property liquid:

    dh = cp dT + (1 - beta T) dP / rho = 0
 => dT = (1 - beta T) dP_loss / (rho cp)        (heating for beta T < 1)

Neglected (documented limitations): frictional heating and potential-energy
change in pipes, Joule-Thomson effects in the reservoir/IPR (inflow enters
at reservoir temperature), tree-body and pipe-wall thermal mass, axial
conduction, insulation transient storage.
"""

from __future__ import annotations

import math

import numpy as np

from app.simulation.components.elements import PipeElement, RestrictionElement
from app.simulation.fluid_properties.base import FluidModel
from app.simulation.solver.integration import implicit_euler_cell
from app.simulation.topology.topology import SeriesTopology


class ThermalModel:
    def __init__(self, topology: SeriesTopology, fluid: FluidModel, t_res: float, t_boundary_fluid: float):
        self.topology = topology
        self.fluid = fluid
        self.t_res = t_res
        self.t_boundary_fluid = t_boundary_fluid
        self.cells: dict[str, np.ndarray] = {}
        self.ambient: dict[str, np.ndarray] = {}
        for e in topology.path:
            if isinstance(e, PipeElement):
                n = e.thermal_cells
                frac = (np.arange(n) + 0.5) / n
                self.ambient[e.id] = e.ambient_in + (e.ambient_out - e.ambient_in) * frac
                self.cells[e.id] = self.ambient[e.id].copy()
        self.node_temperature: dict[str, float] = {}

    # -- helpers -------------------------------------------------------------
    def _props(self, t: float) -> tuple[float, float, float]:
        f = self.fluid
        return f.density(0.0, t), f.specific_heat(0.0, t), f.thermal_expansion(0.0, t)

    def throttling_temperature_rise(self, dp_loss: float, t_in: float) -> float:
        rho, cp, beta = self._props(t_in)
        return (1.0 - beta * t_in) * dp_loss / (rho * cp)

    def _step_pipe(self, e: PipeElement, t_in: float, mdot: float, dt: float | None, reverse: bool) -> float:
        rho, cp, _ = self._props(t_in)
        n = e.thermal_cells
        dl = e.geometry.length / n
        cap = rho * e.geometry.area * dl * cp
        loss = e.overall_htc * math.pi * e.geometry.diameter * dl
        adv = mdot * cp
        cells = self.cells[e.id]
        amb = self.ambient[e.id]
        order = range(n - 1, -1, -1) if reverse else range(n)
        t_up = t_in
        for k in order:
            cells[k] = implicit_euler_cell(float(cells[k]), t_up, float(amb[k]), cap, adv, loss, dt)
            t_up = float(cells[k])
        return t_up

    # -- public --------------------------------------------------------------
    def step(self, q: float, element_dp: dict[str, float | None], dt: float | None) -> dict[str, float]:
        """Advance by ``dt`` seconds (``None`` = jump to thermal steady state)."""
        path = self.topology.path
        nodes = self.topology.node_order
        rho = self.fluid.density(0.0, self.t_res)
        mdot = rho * abs(q) if math.isfinite(q) else 0.0
        reverse = q < 0
        temps: dict[str, float] = {}
        if not reverse:
            temps[nodes[0]] = self.t_res
            seq = list(enumerate(path))
        else:
            temps[nodes[-1]] = self.t_boundary_fluid
            seq = list(reversed(list(enumerate(path))))
        for i, e in seq:
            n_in, n_out = (nodes[i], nodes[i + 1]) if not reverse else (nodes[i + 1], nodes[i])
            t_in = temps[n_in]
            if isinstance(e, PipeElement):
                t_out = self._step_pipe(e, t_in, mdot, dt, reverse)
            elif isinstance(e, RestrictionElement) and mdot > 0.0 and element_dp.get(e.id) is not None:
                dp = element_dp[e.id]
                dp_loss = dp if not reverse else -dp  # type: ignore[operator]
                t_out = t_in + self.throttling_temperature_rise(dp_loss, t_in)
            else:
                t_out = t_in
            temps[n_out] = t_out
        if reverse:
            # The reservoir node is a boundary at reservoir temperature.
            temps[nodes[0]] = self.t_res
        self.node_temperature = temps
        return temps

    def cell_profile(self) -> dict[str, list[float]]:
        return {k: v.tolist() for k, v in self.cells.items()}
