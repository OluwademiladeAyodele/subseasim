"""Dynamic simulation model: couples the hydraulic network, the chemical
transport / thermal grid, the lumped annulus temperature, the chemical
injection circuits and the instrument response.

One call to ``step(dt)`` advances everything by one fixed solver step:

  1. pump / boundary pressures -> fixed-pressure nodes
  2. hydraulic network, implicit Euler + Newton (pressures, flows)
  3. transport grid: chemical concentration and fluid temperature advected
     by the link flows just calculated (explicit, sub-cycled)
  4. lumped annulus temperature
  5. thermal-expansion source for the next hydraulic step (V beta dT/dt)
  6. transmitter response (lag, update interval, resolution)

Coupling between hydraulics and thermal is sequential (explicit in the
thermal-expansion source, one step lag), which is accurate because the
thermal time scales (minutes-hours) are far longer than the step.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from app.core import units as u
from app.models.scenario import ChemicalConfig, ChemicalRouteConfig, ScenarioConfig
from app.simulation.build import BuiltSystem
from app.simulation.components.elements import CheckValveElement, Element, PipeElement, RestrictionElement
from app.simulation.dynamic.builder import PRODUCTION, DynamicLayout, build_dynamic_layout
from app.simulation.dynamic.network import DynamicSolverError
from app.simulation.dynamic.transport import TransportGrid
from app.simulation.fluid_properties.constant_liquid import ConstantPropertyLiquid
from app.simulation.hydraulics.friction import RE_LAMINAR_LIMIT, RE_TURBULENT_LIMIT
from app.simulation.hydraulics.network import HydraulicResult
from app.simulation.inflow.ipr import LinearIPR
from app.simulation.instruments.instruments import Instrument, Reading, classify

#: Flow below which a link is reported as "no flow" [m3/s] (~0.0009 m3/d).
NO_FLOW_M3S = 1e-8
#: Injection below this is reported as "no injection" (3.6 mL/h).
INJECTION_MIN_M3S = 1e-9


@dataclass
class InjRoute:
    """Additional injection route of a circuit into the production path."""

    cfg: ChemicalRouteConfig
    supply_idx: int
    link: int
    inj_node: str
    status: str = "unknown"
    cum_m3: float = 0.0


@dataclass
class ChemCircuit:
    cfg: ChemicalConfig
    k: int  # chemical index in the transport grid
    supply_idx: int
    inj_link: int
    inj_node: str
    rho: float
    cp: float
    t_inj: float
    running: bool
    p_discharge: float
    p_static: float
    status: str = "unknown"
    cum_injected_m3: float = 0.0
    # optional second route into the annulus service line (same pump)
    ann_supply_idx: int | None = None
    ann_link: int | None = None
    ann_status: str = "none"
    cum_to_annulus_m3: float = 0.0
    # further routes into the production path (same pump)
    routes: list[InjRoute] = field(default_factory=list)

    @property
    def p_supply(self) -> float:
        return self.p_discharge if self.running else self.p_static


@dataclass
class InstrumentState:
    y: float | None = None  # filtered value (SI)
    out: float | None = None  # held / quantised output
    next_update_t: float = 0.0


@dataclass
class DynamicModel:
    cfg: ScenarioConfig
    built: BuiltSystem
    fluid: ConstantPropertyLiquid
    ipr: LinearIPR
    p_boundary: float
    t_boundary_fluid: float
    instruments: list[Instrument]
    layout: DynamicLayout = field(init=False)
    grid: TransportGrid = field(init=False)

    def __post_init__(self) -> None:
        self.layout = build_dynamic_layout(self.cfg, self.built, self.fluid)
        self.net = self.layout.network
        topo = self.built.topology
        self.topology = topo
        node_cfg = {n.id: n for n in self.cfg.nodes}
        node_vol = {nid: node_cfg[nid].volume_m3 for nid in topo.node_order if nid in node_cfg}
        cps = {}
        for ec in self.cfg.elements:
            if getattr(ec, "type", None) == "pipe":
                cps[ec.id] = ec.transport_cells_per_segment or self.cfg.dynamics.transport_cells_per_segment
        self.chem_ids = [c.id for c in self.cfg.chemicals]
        self.grid = TransportGrid(self.layout, topo, len(self.chem_ids), cps, node_vol)
        self._cps, self._node_vol = cps, node_vol
        #: Multiphase (black-oil) coupling, attached by the engine (None = single phase).
        self.mp = None
        self.elements: dict[str, Element] = {e.id: e for e in [*topo.path, *self.built.branch_elements]}
        # production node -> outgoing link along the path (flow metering)
        self.prod_out_link: dict[str, int] = {}
        for k, e in enumerate(topo.path):
            nid = topo.node_order[k]
            self.prod_out_link[nid] = self._first_link(e)
        self.prod_out_link[topo.node_order[-1]] = self._last_link(topo.path[-1])
        # chemicals
        self.circuits: list[ChemCircuit] = []
        zones = self.layout.zones
        for k, c in enumerate(self.cfg.chemicals):
            inj_el = c.check_valve or self._element_by_tag(c.control_valve).id
            if c.check_valve:
                inj_el = self._element_by_tag(c.check_valve).id
            z = zones[c.fluid]
            sidx = self.layout.node_index[c.supply_node]
            if not self.net.nodes[sidx].fixed:
                raise ValueError(f"chemical {c.id}: supply node {c.supply_node} must be a subsystem boundary")
            if c.injection_node not in topo.nodes:
                raise ValueError(f"chemical {c.id}: injection node {c.injection_node} must be on the production path")
            li = self.layout.element_link[inj_el]
            if self.net.links[li].dn != self.layout.node_index[c.injection_node]:
                raise ValueError(f"chemical {c.id}: the injection element must discharge into {c.injection_node}")
            circuit = ChemCircuit(
                c, k, sidx, li, c.injection_node, z.rho, z.cp, u.c_to_k(c.injection_temperature_c), c.pump.running,
                u.bara_to_pa(c.pump.discharge_pressure_bara), u.bara_to_pa(c.pump.static_pressure_bara),
            )
            if c.annulus_supply_node:
                if not (c.annulus_valve and c.annulus_check_valve):
                    raise ValueError(f"chemical {c.id}: annulus route needs annulus_valve and annulus_check_valve")
                a_idx = self.layout.node_index[c.annulus_supply_node]
                if not self.net.nodes[a_idx].fixed:
                    raise ValueError(f"chemical {c.id}: annulus supply node {c.annulus_supply_node} must be a subsystem boundary")
                a_link = self.layout.element_link[self._element_by_tag(c.annulus_check_valve).id]
                if self.net.nodes[self.net.links[a_link].dn].zone in (PRODUCTION, c.fluid):
                    raise ValueError(f"chemical {c.id}: the annulus check valve must discharge into an annulus-system node")
                circuit.ann_supply_idx, circuit.ann_link = a_idx, a_link
            for r in c.routes:
                r_idx = self.layout.node_index[r.supply_node]
                if not self.net.nodes[r_idx].fixed:
                    raise ValueError(f"chemical {c.id} route {r.id}: supply node {r.supply_node} must be a subsystem boundary")
                if r.injection_node not in topo.nodes:
                    raise ValueError(f"chemical {c.id} route {r.id}: injection node {r.injection_node} must be on the production path")
                r_link = self.layout.element_link[self._element_by_tag(r.check_valve).id]
                if self.net.links[r_link].dn != self.layout.node_index[r.injection_node]:
                    raise ValueError(f"chemical {c.id} route {r.id}: check valve {r.check_valve} must discharge into {r.injection_node}")
                circuit.routes.append(InjRoute(r, r_idx, r_link, r.injection_node))
            self.circuits.append(circuit)
        # annulus lumped temperature
        self.annulus_nodes: list[int] = []
        at = self.cfg.dynamics.annulus_thermal
        self.t_ann = None
        if at is not None:
            for eid in at.elements:
                info = self.layout.pipes.get(eid)
                if info is None:
                    raise ValueError(f"annulus_thermal references unknown pipe {eid!r}")
                self.annulus_nodes += [i for i in info.node_idx if i not in self.annulus_nodes]
        # constant temperatures for other branch nodes
        node_all = {n.id: n for n in [*self.cfg.nodes, *self.cfg.subsystems.nodes]}
        self.const_T = np.full(self.net.n, u.c_to_k(4.0))
        chem_T = {c.fluid: u.c_to_k(c.injection_temperature_c) for c in self.cfg.chemicals}
        for i, nd in enumerate(self.net.nodes):
            if nd.zone == "reservoir":
                self.const_T[i] = self.ipr.t_res
            elif nd.zone in chem_T:
                self.const_T[i] = chem_T[nd.zone]
            elif nd.topo in node_all:
                self.const_T[i] = u.c_to_k(node_all[nd.topo].ambient_temperature_c)
        self.T_node = self.const_T.copy()
        self.inst_state = {i.tag: InstrumentState() for i in self.instruments}
        self.time_s = 0.0
        self.failed: str | None = None
        self.p0 = None
        self.max_rate_pa_s = 0.0

    # ----------------------------------------------------------- helpers
    def _element_by_tag(self, tag: str) -> Element:
        for e in [*self.topology.path, *self.built.branch_elements]:
            if getattr(e, "tag", None) == tag:
                return e
        raise ValueError(f"unknown component tag {tag!r}")

    def _first_link(self, e: Element) -> int:
        if isinstance(e, PipeElement):
            return self.layout.pipes[e.id].link_idx[0]
        return self.layout.element_link[e.id]

    def _last_link(self, e: Element) -> int:
        if isinstance(e, PipeElement):
            return self.layout.pipes[e.id].link_idx[-1]
        return self.layout.element_link[e.id]

    @property
    def rhocp(self) -> float:
        return self.fluid.rho * self.fluid.cp

    # ------------------------------------------------------- initialisation
    def initialise(self, hyd: HydraulicResult) -> None:
        """Start from the steady operating point of the configuration."""
        net = self.net
        idx = self.layout.node_index
        P = np.full(net.n, np.nan)
        Q = np.zeros(net.m)
        for i, nd in enumerate(net.nodes):
            if nd.fixed:
                P[i] = nd.p_fixed
        q = hyd.q if hyd.ok and math.isfinite(hyd.q) else 0.0
        if hyd.ok:
            for nid, p in hyd.node_pressure.items():
                if p is not None:
                    P[idx[nid]] = p
        # production links carry q; march interior pipe nodes
        prod_links = set()
        for e in self.topology.path:
            if isinstance(e, PipeElement):
                prod_links.update(self.layout.pipes[e.id].link_idx)
            elif e.id in self.layout.element_link:
                prod_links.add(self.layout.element_link[e.id])
        if self.layout.reservoir:
            prod_links.update(self.layout.reservoir.link_idx)
        for li in prod_links:
            Q[li] = q
        net.Q = Q
        r, _ = net.resistance(Q)
        for e in self.topology.path:
            if isinstance(e, PipeElement):
                info = self.layout.pipes[e.id]
                p = P[info.node_idx[0]]
                for s, li in enumerate(info.link_idx[:-1]):
                    p = p - net.gravity[li] - r[li]
                    P[info.node_idx[s + 1]] = p
        if self.layout.reservoir:
            res = self.layout.reservoir
            p = P[res.node_idx[-1]]
            for s in range(len(res.link_idx) - 1, 0, -1):
                p = p - r[res.link_idx[s]]
                P[res.node_idx[s]] = p
        # initial guesses for any remaining node: configured value or a
        # hydrostatic estimate from a neighbour
        for i, nd in enumerate(net.nodes):
            if math.isnan(P[i]) and nd.initial_pressure is not None:
                P[i] = nd.initial_pressure
        for _ in range(net.n):
            changed = False
            for li, l in enumerate(net.links):
                a, b = l.up, l.dn
                if math.isnan(P[a]) and not math.isnan(P[b]):
                    P[a] = P[b] + l.rho * u.G * (net.nodes[b].elevation - net.nodes[a].elevation)
                    changed = True
                elif math.isnan(P[b]) and not math.isnan(P[a]):
                    P[b] = P[a] - l.rho * u.G * (net.nodes[b].elevation - net.nodes[a].elevation)
                    changed = True
            if not changed:
                break
        P[np.isnan(P)] = u.P_ATM
        net.P = P
        self._apply_supply_pressures()
        if self.mp is None:
            net.solve(None)
            # thermal / transport steady state for the initial flows
            F = self.grid.set_flows(net.Q)
            self._inj_at = None
            dT = self._throttle(F)
            self.grid.step(None, F, dT, self._injections(F), self.ipr.t_res, self.t_boundary_fluid, self.rhocp)
            dT = self._throttle(F)
            self.grid.step(None, F, dT, self._injections(F), self.ipr.t_res, self.t_boundary_fluid, self.rhocp)
            self._update_node_temperatures(None)
        else:
            # property / pressure / temperature fixed-point for the initial steady state
            for _ in range(12):
                self.mp.update(force=True)
                net.solve(None)
                F = self.grid.set_flows(net.Q)
                self._inj_at = None
                dT = self._throttle(F)
                self.grid.step(None, F, dT, self._injections(F), self.ipr.t_res, self.t_boundary_fluid, self.rhocp)
                self._update_node_temperatures(None)
            self.mp.comp.step(None, F, np.zeros(self.grid.n + 1), [], self.ipr.t_res, self.t_boundary_fluid, self.rhocp)
            self.mp.update(force=True)
            self.mp.initialise_content()
        self.S = np.zeros(net.n)
        self.p0 = net.P.copy()
        self.p_prev = net.P.copy()
        for c in self.circuits:
            c.status = self._circuit_status(c)
            c.ann_status = self._annulus_route_status(c)
            for r in c.routes:
                r.status = self._route_status(c, r)
        self._init_instruments()

    # -------------------------------------------------------------- control
    def _apply_supply_pressures(self) -> None:
        net = self.net
        for c in self.circuits:
            net.p_fixed[c.supply_idx] = c.p_supply
            if c.ann_supply_idx is not None:
                net.p_fixed[c.ann_supply_idx] = c.p_supply  # same pump
            for r in c.routes:
                net.p_fixed[r.supply_idx] = c.p_supply  # same pump
        res_i = self.layout.node_index[self.topology.reservoir_node]
        bnd_i = self.layout.node_index[self.topology.boundary_node]
        net.p_fixed[res_i] = self.ipr.p_res
        net.p_fixed[bnd_i] = self.p_boundary

    def set_reservoir_productivity(self, j: float) -> None:
        """Change J: rescale reservoir conductances (dynamic: kh changes)."""
        net = self.net
        if self.layout.reservoir is None:
            li = self.layout.element_link[self.topology.path[0].id]
            k = int(np.flatnonzero(net.lin_idx == li)[0])
            net._lin_T[k] = j
            return
        ratio = j / self.ipr.j
        for li in self.layout.reservoir.link_idx:
            k = int(np.flatnonzero(net.lin_idx == li)[0])
            net._lin_T[k] *= ratio

    def set_fluid(self, fluid: ConstantPropertyLiquid) -> None:
        """Production-fluid change: update link density/viscosity, gravity,
        capacitance of production nodes. The pressure state is kept (the
        new fluid is assumed to fill the system - training simplification)."""
        net = self.net
        old = self.fluid
        self.fluid = fluid
        z = self.layout.zones[PRODUCTION]
        z.rho, z.mu, z.cp, z.beta = fluid.rho, fluid.mu, fluid.cp, fluid.beta
        for k, li in enumerate(net.pipe_idx):
            l = net.links[li]
            if self.layout.pipes[l.element_id].zone == PRODUCTION:
                net._prho[k], net._pmu[k] = fluid.rho, fluid.mu
                net.gravity[li] *= fluid.rho / old.rho
                net.inertance[li] *= fluid.rho / old.rho
        for k, li in enumerate(net.orf_idx):
            if net.nodes[net.links[li].up].zone == PRODUCTION:
                net._orf_rho[k] = fluid.rho
                net.gravity[li] *= fluid.rho / old.rho

    # ------------------------------------------------------------------ step
    def _injection_points(self, c: ChemCircuit) -> list[tuple[str, float]]:
        """(production node, injected flow [m3/s]) for every route of a circuit."""
        pts = [(c.inj_node, float(self.net.Q[c.inj_link]))]
        pts += [(r.inj_node, float(self.net.Q[r.link])) for r in c.routes]
        return pts

    def total_injection(self, c: ChemCircuit) -> float:
        """Total flow of the chemical into the production path [m3/s]."""
        return sum(max(q, 0.0) for _, q in self._injection_points(c))

    def _injections(self, F: np.ndarray) -> list[tuple[int, int, float, float, float]]:
        out = []
        for c in self.circuits:
            for node, q in self._injection_points(c):
                if q <= 0:
                    continue
                lk = self.grid.node_lookup[node]
                ci = lk.cell if lk.cell is not None else self.grid.injection_cell(lk.face, F)  # type: ignore[arg-type]
                out.append((c.k, ci, q, c.t_inj, c.rho * c.cp))
        return out

    def injections_at_nodes(self) -> dict[str, list[tuple[int, float]]]:
        cached = getattr(self, "_inj_at", None)
        if cached is not None:
            return cached
        out: dict[str, list[tuple[int, float]]] = {}
        for c in self.circuits:
            for node, q in self._injection_points(c):
                if q > 0:
                    out.setdefault(node, []).append((c.k, q))
        self._inj_at = out
        return out

    def _update_node_temperatures(self, dt: float | None) -> None:
        T = self.const_T.copy()
        ids, temps = self.grid.hnode_temperature()
        T[ids] = temps
        at = self.cfg.dynamics.annulus_thermal
        if at is not None and self.annulus_nodes:
            t_tub = self.tubing_mean_temperature(at.tubing_elements)
            target = at.tubing_weight * t_tub + (1.0 - at.tubing_weight) * u.c_to_k(at.geothermal_mean_c)
            if self.t_ann is None or dt is None:
                self.t_ann = target
            else:
                self.t_ann = target + (self.t_ann - target) * math.exp(-dt / at.time_constant_s)
            T[self.annulus_nodes] = self.t_ann
        if dt is not None:
            # thermal expansion of stored fluid -> volume source for the next step
            self.S = self.net.vol_node * self.net.beta_node * (T - self.T_node) / dt
            self.S[self.net.fixed] = 0.0
        self.T_node = T

    def tubing_mean_temperature(self, elements: list[str]) -> float:
        cells = [c for e in elements for c in self.grid.cell_of_pipe.get(e, [])]
        if not cells:
            return float(self.grid.T.mean())
        v = self.grid.V[cells]
        return float((self.grid.T[cells] * v).sum() / v.sum())

    def _throttle(self, F: np.ndarray) -> np.ndarray:
        lp = self.mp.link_props if self.mp is not None else None
        return self.grid.throttle(F, self.net.P, self.fluid.rho, self.fluid.cp, self.fluid.beta, lp)

    def attach_multiphase(self, fluid, rho_ref: float, gor: float, wc: float, correlation: str) -> None:
        from app.simulation.multiphase.dynamic import MultiphaseCoupling

        self.mp = MultiphaseCoupling(self, fluid, rho_ref, gor, wc, correlation, self._cps, self._node_vol)

    def step(self, dt: float, t_now: float) -> None:
        net = self.net
        self._apply_supply_pressures()
        if self.mp is not None:
            self.mp.update()
        P_old, Q_old = net.P.copy(), net.Q.copy()
        try:
            net.solve(dt, self.S)
        except (DynamicSolverError, np.linalg.LinAlgError) as exc:
            net.P, net.Q = P_old, Q_old
            self.failed = f"dynamic hydraulic solver failed: {exc}"
            raise DynamicSolverError(self.failed) from exc
        F = self.grid.set_flows(net.Q)
        if self.mp is not None:
            self.mp.set_cell_targets(P_old)
        dT = self._throttle(F)
        inj = self._injections(F)
        self._inj_at = None
        for c in self.circuits:
            c.cum_injected_m3 += max(float(net.Q[c.inj_link]), 0.0) * dt
            if c.ann_link is not None:
                c.cum_to_annulus_m3 += max(float(net.Q[c.ann_link]), 0.0) * dt
            for r in c.routes:
                r.cum_m3 += max(float(net.Q[r.link]), 0.0) * dt
        self.grid.step(dt, F, dT, inj, self.ipr.t_res, self.t_boundary_fluid, self.rhocp)
        if self.mp is not None:
            self.mp.comp.step(dt, F, np.zeros(self.grid.n + 1), [], self.ipr.t_res, self.t_boundary_fluid, self.rhocp)
        self._update_node_temperatures(dt)
        self.max_rate_pa_s = float(np.max(np.abs(net.P - P_old)[~net.fixed])) / dt if net.n else 0.0
        self.p_prev = P_old
        self.time_s = t_now
        self._update_instruments(dt, t_now)

    # ------------------------------------------------------------- queries
    def node_pressure(self, nid: str) -> float:
        return float(self.net.P[self.layout.node_index[nid]])

    def node_temperature(self, nid: str) -> float:
        if nid in self.grid.node_lookup:
            return self.grid.node_value(nid, self.grid.F, self.grid.dT_throttle, "T")
        return float(self.T_node[self.layout.node_index[nid]])

    def element_flow(self, eid: str) -> float:
        e = self.elements[eid]
        if isinstance(e, PipeElement):
            return float(self.net.Q[self.layout.pipes[eid].link_idx[0]])
        return float(self.net.Q[self.layout.element_link[eid]])

    def pipe_position_pressure(self, eid: str, x: float) -> float:
        info = self.layout.pipes[eid]
        L = info.element.geometry.length
        f = min(max(x / L, 0.0), 1.0) * info.segments
        k = min(int(f), info.segments - 1)
        w = f - k
        P = self.net.P
        return float(P[info.node_idx[k]] * (1 - w) + P[info.node_idx[k + 1]] * w)

    def _pv_flow_ref(self, inst: Instrument) -> float | None:
        mp, self.mp = self.mp, None
        try:
            return self._pv(inst)
        finally:
            self.mp = mp

    def _pv(self, inst: Instrument) -> float | None:
        net = self.net
        idx = self.layout.node_index
        if inst.type == "pressure":
            if inst.element:
                return self.pipe_position_pressure(inst.element, inst.distance_m or 0.0)
            return float(net.P[idx[inst.node]])  # type: ignore[index]
        if inst.type == "differential_pressure":
            return float(net.P[idx[inst.high_node]] - net.P[idx[inst.low_node]])  # type: ignore[index]
        if inst.type == "temperature":
            if inst.element and inst.element in self.grid.cell_of_pipe:
                return float(self.grid.T[self.grid.cell_at(inst.element, inst.distance_m or 0.0)])
            if inst.element:
                info = self.layout.pipes[inst.element]
                return float(self.T_node[info.node_idx[0]])
            return self.node_temperature(inst.node)  # type: ignore[arg-type]
        if inst.type == "flow" and self.mp is not None:
            q = self._pv_flow_ref(inst)
            return None if q is None else self.mp.in_situ_flow(inst, q)
        if inst.type == "flow":
            if inst.element:
                e = self.elements[inst.element]
                if isinstance(e, PipeElement) and inst.distance_m is not None:
                    info = self.layout.pipes[e.id]
                    k = min(int(inst.distance_m / e.geometry.length * info.segments), info.segments - 1)
                    return float(net.Q[info.link_idx[k]])
                return self.element_flow(inst.element)
            nid = inst.node
            if nid in self.prod_out_link:
                return float(net.Q[self.prod_out_link[nid]])
            i = idx[nid]  # type: ignore[index]
            for li, l in enumerate(net.links):
                if l.up == i:
                    return float(net.Q[li])
            return None
        if inst.type == "concentration":
            k = self.chem_ids.index(inst.chemical)  # type: ignore[arg-type]
            if inst.element:
                if inst.element not in self.grid.cell_of_pipe:
                    return None
                return float(self.grid.c[k, self.grid.cell_at(inst.element, inst.distance_m or 0.0)])
            if inst.node not in self.grid.node_lookup:
                return None
            return self.grid.node_value(inst.node, self.grid.F, self.grid.dT_throttle, "c", k, self.injections_at_nodes())  # type: ignore[arg-type]
        return None

    def _init_instruments(self) -> None:
        for inst in self.instruments:
            st = self.inst_state[inst.tag]
            pv = self._pv(inst)
            st.y = pv
            st.out = self._quantise(inst, pv)
            st.next_update_t = 0.0

    @staticmethod
    def _quantise(inst: Instrument, v: float | None) -> float | None:
        r = inst.response
        if v is None or r is None or r.resolution_si <= 0:
            return v
        return round(v / r.resolution_si) * r.resolution_si

    def _update_instruments(self, dt: float, t: float) -> None:
        for inst in self.instruments:
            st = self.inst_state[inst.tag]
            pv = self._pv(inst)
            r = inst.response
            if pv is None or not math.isfinite(pv):
                st.y = None
                st.out = None
                continue
            if st.y is None or r is None or r.time_constant_s <= 0:
                st.y = pv
            else:
                st.y += (1.0 - math.exp(-dt / r.time_constant_s)) * (pv - st.y)
            if r is None or r.update_interval_s <= 0 or t >= st.next_update_t - 1e-9:
                st.out = self._quantise(inst, st.y)
                if r is not None and r.update_interval_s > 0:
                    st.next_update_t = t + r.update_interval_s
            elif st.out is None:
                st.out = self._quantise(inst, st.y)

    def readings(self) -> dict[str, Reading]:
        out = {}
        for inst in self.instruments:
            pv = self._pv(inst)
            st = self.inst_state[inst.tag]
            if self.failed:
                out[inst.tag] = Reading(inst.tag, None, None, "BAD")
                continue
            rd = classify(inst, st.out)
            rd.pv = pv  # model process value (before sensor dynamics)
            out[inst.tag] = rd
        return out

    # ------------------------------------------------------------- analysis
    def link_state(self, li: int) -> str:
        if self.net.blocked[li]:
            return "closed"
        return "flowing" if abs(self.net.Q[li]) > NO_FLOW_M3S else "no_flow"

    def node_states(self) -> dict[int, str]:
        out: dict[int, str] = {}
        flowing = np.zeros(self.net.n, dtype=bool)
        for li in range(self.net.m):
            if abs(self.net.Q[li]) > NO_FLOW_M3S and not self.net.blocked[li]:
                flowing[self.net.up[li]] = flowing[self.net.dn[li]] = True
        res_i = self.layout.node_index[self.topology.reservoir_node]
        for comp in self.net.components():
            fixed = [i for i in comp if self.net.fixed[i]]
            for i in comp:
                if flowing[i]:
                    out[i] = "flowing"
                elif not fixed:
                    out[i] = "trapped"
                elif res_i in fixed:
                    out[i] = "static_reservoir"
                else:
                    out[i] = "static_boundary"
        return out

    def _circuit_status(self, c: ChemCircuit) -> str:
        q = float(self.net.Q[c.inj_link])
        iso = self._element_by_tag(c.cfg.isolation_valve)
        cv = self._element_by_tag(c.cfg.control_valve)
        iso_open = not (isinstance(iso, RestrictionElement) and iso.actuator.position_pct <= 0)
        cv_open = not (isinstance(cv, RestrictionElement) and cv.actuator.position_pct <= 0)
        # A trapped line section may still decompress through the check valve
        # after isolation (real, tiny, transient flow) - that is not injection.
        if q > INJECTION_MIN_M3S and iso_open and cv_open:
            return "injecting"
        if not c.running:
            return "pump_stopped"
        if not iso_open:
            return "isolated"
        if not cv_open:
            return "metering_closed"
        return "insufficient_differential"

    def available_differential(self, c: ChemCircuit) -> float:
        """Supply pressure + static head to the injection point - production
        pressure there - check-valve cracking pressure [Pa]."""
        net = self.net
        sup = net.nodes[c.supply_idx]
        inj_i = self.layout.node_index[c.inj_node]
        head = c.rho * u.G * (sup.elevation - net.nodes[inj_i].elevation)
        crack = 0.0
        if c.cfg.check_valve:
            e = self._element_by_tag(c.cfg.check_valve)
            if isinstance(e, CheckValveElement):
                crack = e.cracking_pressure
        return c.p_supply + head - float(net.P[inj_i]) - crack

    def _annulus_route_status(self, c: ChemCircuit) -> str:
        if c.ann_link is None:
            return "none"
        miv = self._element_by_tag(c.cfg.annulus_valve)  # type: ignore[arg-type]
        miv_open = not (isinstance(miv, RestrictionElement) and miv.actuator.position_pct <= 0)
        if float(self.net.Q[c.ann_link]) > INJECTION_MIN_M3S and miv_open:
            return "injecting"
        if not c.running:
            return "pump_stopped"
        return "isolated" if not miv_open else "insufficient_differential"

    def _route_status(self, c: ChemCircuit, r: InjRoute) -> str:
        v = self._element_by_tag(r.cfg.valve)
        v_open = not (isinstance(v, RestrictionElement) and v.actuator.position_pct <= 0)
        if float(self.net.Q[r.link]) > INJECTION_MIN_M3S and v_open:
            return "injecting"
        if not c.running:
            return "pump_stopped"
        return "isolated" if not v_open else "insufficient_differential"

    def update_circuit_status(self) -> list[tuple[ChemCircuit, str, str, str]]:
        """Status transitions as (circuit, old, new, route) with route
        "production" (main injection point) or "annulus" (service line)."""
        changes = []
        for c in self.circuits:
            s = self._circuit_status(c)
            if s != c.status:
                changes.append((c, c.status, s, "production"))
                c.status = s
            if c.ann_link is not None:
                a = self._annulus_route_status(c)
                if a != c.ann_status:
                    changes.append((c, c.ann_status, a, "annulus"))
                    c.ann_status = a
            for r in c.routes:
                rs = self._route_status(c, r)
                if rs != r.status:
                    changes.append((c, r.status, rs, f"route:{r.cfg.id}"))
                    r.status = rs
        return changes

    def chemical_front(self, c: ChemCircuit) -> dict:
        """Furthest downstream distance from the injection point at which the
        chemical exceeds 1 % of the concentration just downstream of it."""
        g = self.grid
        F = g.face_flows(self.net.Q)
        lk = g.node_lookup[c.inj_node]
        start = lk.cell if lk.cell is not None else g.injection_cell(lk.face, F)  # type: ignore[arg-type]
        conc = g.c[c.k]
        ref = float(conc[start:].max()) if F[min(start, g.n)] >= 0 else float(conc[: start + 1].max())
        x0 = float(g.pos[start])
        front = 0.0
        if ref > 1e-7:  # ignore numerical traces below 0.1 ppm
            thr = max(0.01 * ref, 1e-7)
            above = np.flatnonzero(conc > thr)
            if above.size:
                front = float(max(abs(g.pos[above[-1]] - x0), abs(g.pos[above[0]] - x0)))
        return {"injection_cell": int(start), "path_position_m": x0, "front_distance_m": front}

    def plug_flow_time(self, from_node: str, to_cell: int) -> float | None:
        """Plug-flow residence time t = V / Q between an injection node and a
        downstream cell, using the CURRENT local face flows."""
        g = self.grid
        F = g.face_flows(self.net.Q)
        lk = g.node_lookup[from_node]
        start = lk.cell if lk.cell is not None else g.injection_cell(lk.face, F)  # type: ignore[arg-type]
        if to_cell < start:
            return None
        t = 0.0
        for ci in range(start, to_cell + 1):
            q = F[ci + 1]
            if q <= 0:
                return None
            t += g.V[ci] / q * (0.5 if ci in (start, to_cell) else 1.0)
        return t

    def diagnostics(self) -> list[dict]:
        out: list[dict] = []
        net = self.net
        topo_nodes = {**self.topology.nodes, **self.built.branch_nodes}
        if self.failed:
            out.append({"severity": "error", "code": "DYNAMIC_SOLVER_FAILED", "message": self.failed, "location": None})
            return out
        if not net.last_converged:
            out.append({"severity": "warning", "code": "DYNAMIC_NOT_CONVERGED",
                        "message": f"Dynamic hydraulic step did not fully converge in {net.last_iterations} Newton iterations "
                                   f"(link residual {net.last_residual:.3g} Pa). Results may be inaccurate.", "location": None})
        for i, nd in enumerate(net.nodes):
            p = net.P[i]
            if nd.zone == "reservoir":
                continue
            if p <= 0:
                nm = topo_nodes[nd.topo].name if nd.topo in topo_nodes else nd.name
                out.append({"severity": "error", "code": "NEGATIVE_ABSOLUTE_PRESSURE",
                            "message": f"Absolute pressure at {nm} is {u.pa_to_bara(p):.2f} bara (<= 0): a liquid cannot sustain "
                                       "this (column separation / cavitation is not modelled). Results are not physically valid.",
                            "location": nd.topo})
            elif self.mp is None and nd.zone == PRODUCTION and nd.topo and p < self.fluid.p_bubble:
                out.append({"severity": "warning", "code": "BELOW_BUBBLE_POINT",
                            "message": f"Pressure at {topo_nodes[nd.topo].name} ({u.pa_to_bara(p):.1f} bara) is below the bubble "
                                       f"point ({u.pa_to_bara(self.fluid.p_bubble):.1f} bara): gas would come out of solution; "
                                       "the single-phase liquid model is not valid here.", "location": nd.topo})
        q_res = float(net.Q[self.layout.element_link[self.topology.path[0].id]])
        if q_res < -NO_FLOW_M3S:
            out.append({"severity": "warning", "code": "REVERSE_FLOW",
                        "message": "Fluid is flowing back into the reservoir (cross-flow / injection). Injectivity is assumed "
                                   "equal to productivity and the same fluid is assumed.", "location": None})
        if self.mp is not None:
            out += self.mp.diagnostics()
        for eid, info in self.layout.pipes.items():
            if info.zone != PRODUCTION or self.mp is not None:
                continue
            q = abs(float(net.Q[info.link_idx[0]]))
            if q > NO_FLOW_M3S:
                re = self.fluid.rho * q / info.area * info.hydraulic_diameter / self.fluid.mu
                if RE_LAMINAR_LIMIT < re < RE_TURBULENT_LIMIT:
                    out.append({"severity": "info", "code": "TRANSITIONAL_FLOW",
                                "message": f"{info.element.name}: Reynolds number {re:.0f} is in the laminar-turbulent transition; "
                                           "friction factor is uncertain.", "location": eid})
        # Chemical sent into the annulus system is accounted separately; the
        # annulus-system fluid composition itself is not tracked, so fluid
        # returning to the production bore (crossover) is treated as brine.
        if any(c.cum_to_annulus_m3 > 1e-4 for c in self.circuits):
            for li, l in enumerate(net.links):
                if net.blocked[li] or net.Q[li] <= NO_FLOW_M3S:
                    continue
                if net.nodes[l.up].zone == "annulus" and net.nodes[l.dn].zone == PRODUCTION:
                    out.append({"severity": "info", "code": "ANNULUS_COMPOSITION_UNTRACKED",
                                "message": f"Annulus-system fluid is entering the production bore through {l.element_id}. Methanol "
                                           "previously injected into the annulus service line is not tracked inside the annulus, so "
                                           "this inflow is treated as annulus brine in the production-line concentrations.",
                                "location": l.element_id})
                    break
        for comp in net.components():
            if not any(net.fixed[i] for i in comp):
                names = sorted({net.nodes[i].topo for i in comp if net.nodes[i].topo})
                if names:
                    out.append({"severity": "info", "code": "TRAPPED_SECTION",
                                "message": "Isolated volume (" + ", ".join(names) + "): pressure follows its own mass balance - "
                                           "seat leakage, thermal expansion/contraction and compressibility.", "location": names[0]})
        return out
