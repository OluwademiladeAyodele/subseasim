"""Steady-state hydraulic solver for a series flow path.

Open path (no closed element): find the single volumetric flow Q with

    F(Q) = P_res - P_boundary - sum_i dP_i(Q) = 0

where the sum runs over every element (the inflow element contributes the
IPR drawdown Q/J). Each dP_i is continuous and non-decreasing in Q and the
IPR term is strictly increasing, so F is strictly decreasing and the root
is unique. With F0 = F(0) (the net static driving pressure) the root lies in

    [0, J F0]   if F0 > 0        (normal production)
    [J F0, 0]   if F0 < 0        (reverse flow / injection)

because F(J F0) = -sum_{non-IPR} dP_i(J F0), whose sign is opposite to F0.
This bracket is exact, so Brent's method always converges.

Closed path: Q = 0. Nodes hydraulically connected to the reservoir take the
static (hydrostatic) pressure referenced to P_res; nodes connected to the
boundary take static pressure referenced to P_boundary; nodes isolated
between two closed elements are TRAPPED - incompressible steady state cannot
determine their pressure, so they retain their last calculated value (or are
reported as undetermined if none exists).

Node pressures are obtained by marching from the reservoir:
P_{k+1} = P_k - dP_k(Q). Flow is identical in every element by construction
(series path, incompressible fluid) - mass conservation is exact.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

from app.simulation.components.elements import InflowElement
from app.simulation.hydraulics.properties import FlowProperties
from app.simulation.solver.root_finding import SolverError, solve_bracketed
from app.simulation.topology.topology import SeriesTopology

NodeState = Literal["flowing", "static_reservoir", "static_boundary", "trapped"]
ElementState = Literal["flowing", "no_flow", "closed"]
HydraulicStatus = Literal["solved", "closed_in", "failed"]

#: Residual acceptance: |F| <= max(RESIDUAL_ABS_PA, RESIDUAL_REL * pressure scale)
RESIDUAL_ABS_PA = 1.0
RESIDUAL_REL = 1e-8


@dataclass
class HydraulicResult:
    status: HydraulicStatus
    q: float  # m3/s, signed (+ = production direction)
    node_pressure: dict[str, float | None]
    node_state: dict[str, NodeState]
    element_dp: dict[str, float | None]
    element_state: dict[str, ElementState]
    driving_pressure: float  # F(0) [Pa]
    residual: float = 0.0
    iterations: int = 0
    message: str = ""
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status != "failed"


def _failed(topology: SeriesTopology, message: str, f0: float = math.nan) -> HydraulicResult:
    return HydraulicResult(
        status="failed",
        q=math.nan,
        node_pressure={n: None for n in topology.node_order},
        node_state={n: "flowing" for n in topology.node_order},
        element_dp={e.id: None for e in topology.path},
        element_state={e.id: "no_flow" for e in topology.path},
        driving_pressure=f0,
        message=message,
    )


def solve_hydraulics(
    topology: SeriesTopology,
    p_res: float,
    p_boundary: float,
    props: FlowProperties,
    previous_pressure: dict[str, float | None] | None = None,
) -> HydraulicResult:
    path = topology.path
    nodes = topology.node_order
    inflow = path[0]
    assert isinstance(inflow, InflowElement)
    j = inflow.ipr.j

    closed_idx = [i for i, e in enumerate(path) if e.is_closed()]

    def static_drop(i: int) -> float:
        return path[i].static_dp(props)

    f0 = p_res - p_boundary - sum(static_drop(i) for i in range(len(path)))

    if not closed_idx:
        def residual(q: float) -> float:
            return p_res - p_boundary - sum(e.dp(q, props) for e in path)

        try:
            if f0 == 0.0:
                q, iters, res = 0.0, 0, 0.0
            else:
                lo, hi = sorted((0.0, j * f0))
                root = solve_bracketed(residual, lo, hi)
                if not root.converged:
                    return _failed(topology, "hydraulic solver did not converge", f0)
                q, iters, res = root.x, root.iterations, root.residual
        except (SolverError, OverflowError, ZeroDivisionError, ValueError) as exc:
            return _failed(topology, f"hydraulic solver error: {exc}", f0)

        tol = max(RESIDUAL_ABS_PA, RESIDUAL_REL * max(abs(p_res), abs(p_boundary)))
        if not math.isfinite(q) or not math.isfinite(res) or abs(res) > tol:
            return _failed(topology, f"operating point residual {res:.3g} Pa exceeds tolerance {tol:.3g} Pa", f0)

        pressures: dict[str, float | None] = {nodes[0]: p_res}
        dps: dict[str, float | None] = {}
        p = p_res
        for i, e in enumerate(path):
            dp = e.dp(q, props)
            dps[e.id] = dp
            p -= dp
            pressures[nodes[i + 1]] = p
        # Close the march exactly onto the boundary (difference == residual).
        pressures[nodes[-1]] = p_boundary
        flowing = q != 0.0
        return HydraulicResult(
            status="solved",
            q=q,
            node_pressure=pressures,
            node_state={n: "flowing" for n in nodes},
            element_dp=dps,
            element_state={e.id: ("flowing" if flowing else "no_flow") for e in path},
            driving_pressure=f0,
            residual=res,
            iterations=iters,
        )

    # ---- closed-in: Q = 0 --------------------------------------------------
    first, last = closed_idx[0], closed_idx[-1]
    pressures = {}
    state: dict[str, NodeState] = {}
    notes: list[str] = []

    # Reservoir side: nodes 0..first (node `first` is upstream of element `first`).
    p = p_res
    pressures[nodes[0]] = p
    state[nodes[0]] = "static_reservoir"
    for i in range(first):
        p -= static_drop(i)
        pressures[nodes[i + 1]] = p
        state[nodes[i + 1]] = "static_reservoir"

    # Boundary side: nodes last+1..end.
    p = p_boundary
    pressures[nodes[-1]] = p
    state[nodes[-1]] = "static_boundary"
    for i in range(len(path) - 1, last, -1):
        p += static_drop(i)
        pressures[nodes[i]] = p
        state[nodes[i]] = "static_boundary"

    # Trapped nodes between the first and last closed elements.
    prev = previous_pressure or {}
    for k in range(first + 1, last + 1):
        n = nodes[k]
        pressures[n] = prev.get(n)
        state[n] = "trapped"
        if pressures[n] is None:
            notes.append(f"pressure at {n} is undetermined (trapped volume with no history)")
    if last > first:
        notes.append("trapped section: pressure retained from moment of isolation (no leakage, isothermal, rigid volume assumed)")

    dps = {}
    for i, e in enumerate(path):
        pu, pd = pressures.get(nodes[i]), pressures.get(nodes[i + 1])
        dps[e.id] = None if pu is None or pd is None else pu - pd

    return HydraulicResult(
        status="closed_in",
        q=0.0,
        node_pressure=pressures,
        node_state=state,
        element_dp=dps,
        element_state={e.id: ("closed" if i in closed_idx else "no_flow") for i, e in enumerate(path)},
        driving_pressure=f0,
        notes=notes,
    )
