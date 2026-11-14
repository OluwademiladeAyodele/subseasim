"""Simulation engine: owns the state of one simulated production system.

Time model
----------
* Hydraulics are QUASI-STEADY: for the current valve positions and boundary
  conditions the steady operating point is solved algebraically. No pressure
  transient, line-pack or water-hammer physics exists in Release 1.
* Valve/choke positions move at a finite actuator rate (genuinely time
  dependent, but only kinematically).
* Temperatures are TRANSIENT (lumped cell energy balance, implicit Euler).

The engine is advanced only by ``advance(dt)`` in simulation seconds, so the
results are independent of wall-clock speed and browser rendering.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.core import units as u
from app.core.config import Settings, settings as default_settings
from app.models.scenario import ScenarioConfig
from app.simulation.build import build_fluid, build_system
from app.simulation.components.elements import CommandRejected, PipeElement, RestrictionElement, ValveElement
from app.simulation.diagnostics.checks import Diagnostic, run_diagnostics
from app.simulation.flowline.pipe import hydrostatic_dp, pipe_reynolds
from app.simulation.fluid_properties.constant_liquid import ConstantPropertyLiquid
from app.simulation.hydraulics.network import HydraulicResult, solve_hydraulics
from app.simulation.hydraulics.properties import FlowProperties
from app.simulation.instruments.instruments import Reading, measure
from app.simulation.solver.integration import substeps
from app.simulation.state import EventLog, History, SimStatus
from app.simulation.thermodynamics.thermal import ThermalModel
from app.simulation.valves.characteristics import CHARACTERISTIC_DESCRIPTIONS

MODEL_DESCRIPTION = {
    "hydraulics": "Quasi-steady, single-phase incompressible liquid; series path; linear IPR; "
    "Darcy-Weisbach/Churchill friction; orifice-type restrictions. Recalculated instantly - no pressure transients.",
    "thermal": "Transient lumped energy balance (cells in series, implicit Euler); isenthalpic throttling at restrictions.",
    "valves": "Rate-limited actuator travel (constant stroke speed); generic inherent characteristics, not vendor data.",
    "instruments": "Ideal transmitters within calibrated range (no noise, drift or faults in Release 1).",
}


class InvalidOperatingInput(ValueError):
    pass


@dataclass
class _PendingOutcome:
    label: str
    tag: str | None
    target: float | None
    before: dict


class SimulationEngine:
    def __init__(self, scenario: ScenarioConfig, cfg: Settings = default_settings):
        self.settings = cfg
        self.events = EventLog(cfg.event_log_length)
        self.history = History(cfg.history_length)
        self.time_scale = 1.0
        self._load(scenario)
        self.events.add(0.0, "scenario", f"Scenario loaded: {scenario.name}")

    # ------------------------------------------------------------------ setup
    def _load(self, scenario: ScenarioConfig) -> None:
        self.scenario = scenario
        built = build_system(scenario)
        self.topology = built.topology
        self.fluid: ConstantPropertyLiquid = built.fluid
        self.ipr = built.ipr
        self.p_boundary = built.p_boundary
        self.instruments = built.instruments
        self.thermal = ThermalModel(self.topology, self.fluid, self.ipr.t_res, built.t_boundary_fluid)
        self.restrictions: dict[str, RestrictionElement] = {
            e.tag: e for e in self.topology.path if isinstance(e, RestrictionElement)
        }
        self.status: SimStatus = "ready"
        self.time_s = 0.0
        self._last_sample_t = -math.inf
        self._pending: list[_PendingOutcome] = []
        self.hyd: HydraulicResult | None = None
        self._solve()
        # Initial condition: thermal steady state for the initial configuration.
        self.thermal.step(self.hyd.q if self.hyd.ok else 0.0, self.hyd.element_dp, None)
        self._measure()
        self._record_sample(force=True)

    # ------------------------------------------------------------ calculation
    @property
    def props(self) -> FlowProperties:
        return FlowProperties.from_fluid(self.fluid)

    def _solve(self) -> None:
        prev = self.hyd.node_pressure if self.hyd is not None and self.hyd.ok else None
        self.hyd = solve_hydraulics(self.topology, self.ipr.p_res, self.p_boundary, self.props, prev)

    def _thermal_refresh(self, dt: float) -> None:
        q = self.hyd.q if self.hyd.ok else 0.0
        self.thermal.step(q, self.hyd.element_dp, dt)

    def _measure(self) -> None:
        temps = self.thermal.node_temperature
        q = self.hyd.q if self.hyd.ok else math.nan
        self.readings: dict[str, Reading] = {
            i.tag: measure(i, self.hyd.ok, self.hyd.node_pressure, temps, q) for i in self.instruments
        }
        self.diagnostics: list[Diagnostic] = run_diagnostics(self.topology, self.hyd, self.fluid, self.props, temps)
        if any(d.severity == "error" for d in self.diagnostics) and self.hyd.ok:
            # Physically invalid point: flag every reading rather than show plausible numbers.
            for tag, r in self.readings.items():
                r.status = "BAD"
                r.value = None

    def recompute(self) -> None:
        """Re-solve hydraulics for the present state without advancing time."""
        self._solve()
        self._thermal_refresh(0.0)
        self._measure()

    # ------------------------------------------------------------------- time
    def advance(self, dt_total: float) -> None:
        if self.status != "running" or dt_total <= 0:
            return
        for dt in substeps(dt_total, self.settings.max_substep_s):
            moving = [r for r in self.restrictions.values() if r.actuator.is_moving]
            for r in moving:
                r.actuator.step(dt)
            if moving:
                self._solve()
            self._thermal_refresh(dt)
            self.time_s += dt
        self._measure()
        self._check_outcomes()
        self._record_sample()

    def _record_sample(self, force: bool = False) -> None:
        if not force and self.time_s - self._last_sample_t < self.settings.sample_interval_s - 1e-9:
            return
        self._last_sample_t = self.time_s
        s: dict = {"t": self.time_s, "q": self.hyd.q if self.hyd.ok else None}
        for tag, r in self.readings.items():
            s[f"inst:{tag}"] = r.value
        for tag, r in self.restrictions.items():
            s[f"pos:{tag}"] = r.actuator.position_pct
            s[f"cmd:{tag}"] = r.actuator.commanded_pct
        self.history.add(s)

    # -------------------------------------------------------------- lifecycle
    def start(self) -> None:
        if self.status != "ready":
            raise CommandRejected(f"cannot start: simulation is {self.status}")
        self.status = "running"
        self.events.add(self.time_s, "lifecycle", "Simulation started")

    def pause(self) -> None:
        if self.status != "running":
            raise CommandRejected(f"cannot pause: simulation is {self.status}")
        self.status = "paused"
        self.events.add(self.time_s, "lifecycle", "Simulation paused (simulation time frozen)")

    def resume(self) -> None:
        if self.status != "paused":
            raise CommandRejected(f"cannot resume: simulation is {self.status}")
        self.status = "running"
        self.events.add(self.time_s, "lifecycle", "Simulation resumed")

    def reset(self) -> None:
        self.history.clear()
        self._load(self.scenario)
        self.events.add(0.0, "lifecycle", "Simulation reset to scenario initial conditions")

    def load_scenario(self, scenario: ScenarioConfig) -> None:
        self.history.clear()
        self._load(scenario)
        self.events.add(0.0, "scenario", f"Scenario loaded: {scenario.name}")

    def set_time_scale(self, scale: float) -> None:
        if scale not in self.settings.allowed_time_scales:
            raise CommandRejected(f"time scale must be one of {self.settings.allowed_time_scales}")
        self.time_scale = scale
        self.events.add(self.time_s, "lifecycle", f"Simulation speed set to {scale:g}x")

    # --------------------------------------------------------------- commands
    def _key_values(self) -> dict:
        h = self.hyd
        return {
            "q": h.q if h.ok else None,
            "p": dict(h.node_pressure),
            "dp": dict(h.element_dp),
        }

    def command_valve(self, tag: str, command: str, position_pct: float | None = None) -> None:
        if tag not in self.restrictions:
            raise CommandRejected(f"unknown valve tag {tag!r}")
        el = self.restrictions[tag]
        try:
            target = el.validate_command(command, position_pct)
        except CommandRejected as exc:
            self.events.add(self.time_s, "rejected", f"Command rejected: {exc}", component=tag, severity="warning")
            raise
        act = el.actuator
        verb = {"open": "OPEN", "close": "CLOSE"}.get(command, f"SET {target:.1f} %")
        if abs(target - act.commanded_pct) < 1e-9:
            self.events.add(self.time_s, "operation", f"{tag} {verb} commanded (already at commanded position {target:.1f} %)", component=tag)
            return

        if isinstance(el, ValveElement) and target > act.position_pct and act.position_pct == 0.0:
            self._check_opening_rule(el)

        act.commanded_pct = target
        travel = act.time_to_target()
        note = "" if self.status == "running" else " - simulation not running: valve will move when the simulation runs"
        self.events.add(
            self.time_s, "operation",
            f"{tag} {verb} commanded ({act.position_pct:.1f} % -> {target:.1f} %, travel ~{travel:.0f} s){note}",
            component=tag,
        )
        self._pending = [p for p in self._pending if p.tag != tag]
        self._pending.append(_PendingOutcome(f"{tag} {verb}", tag, target, self._key_values()))

    def _check_opening_rule(self, el: ValveElement) -> None:
        limit_bar = self.scenario.training_rules.max_opening_differential_bar
        if limit_bar is None:
            return
        dp = self.hyd.element_dp.get(el.id)
        if dp is None:
            self.events.add(
                self.time_s, "training_rule",
                f"TRAINING RULE: differential across {el.tag} is undetermined (trapped section) - verify equalisation before opening",
                component=el.tag, severity="warning",
            )
            return
        if abs(dp) > u.bar_to_pa_delta(limit_bar):
            self.events.add(
                self.time_s, "training_rule",
                f"TRAINING RULE: {el.tag} opened against {u.pa_to_bar_delta(dp):.1f} bar differential "
                f"(training limit {limit_bar:g} bar). Gate valves are normally equalised before opening.",
                component=el.tag, severity="warning",
                detail="This is a training rule, not a real interlock or operating procedure.",
            )

    def set_boundary(
        self,
        reservoir_pressure_pa: float | None = None,
        productivity_index_si: float | None = None,
        reservoir_temperature_k: float | None = None,
        downstream_pressure_pa: float | None = None,
    ) -> None:
        before = self._key_values()
        changes: list[str] = []
        if reservoir_pressure_pa is not None:
            if not reservoir_pressure_pa > 0:
                raise InvalidOperatingInput("reservoir pressure must be positive (absolute)")
            changes.append(f"reservoir pressure {u.pa_to_bara(self.ipr.p_res):.1f} -> {u.pa_to_bara(reservoir_pressure_pa):.1f} bara")
            self.ipr.p_res = reservoir_pressure_pa
        if productivity_index_si is not None:
            if not productivity_index_si > 0:
                raise InvalidOperatingInput("productivity index must be positive")
            changes.append(
                f"productivity index {u.pi_si_to_m3d_per_bar(self.ipr.j):.2f} -> {u.pi_si_to_m3d_per_bar(productivity_index_si):.2f} (m3/d)/bar"
            )
            self.ipr.j = productivity_index_si
        if reservoir_temperature_k is not None:
            if not reservoir_temperature_k > 0:
                raise InvalidOperatingInput("temperature must be positive (K)")
            changes.append(f"reservoir temperature {u.k_to_c(self.ipr.t_res):.1f} -> {u.k_to_c(reservoir_temperature_k):.1f} degC")
            self.ipr.t_res = reservoir_temperature_k
            self.thermal.t_res = reservoir_temperature_k
        if downstream_pressure_pa is not None:
            if not downstream_pressure_pa > 0:
                raise InvalidOperatingInput("downstream pressure must be positive (absolute)")
            changes.append(f"downstream pressure {u.pa_to_bara(self.p_boundary):.1f} -> {u.pa_to_bara(downstream_pressure_pa):.1f} bara")
            self.p_boundary = downstream_pressure_pa
        if not changes:
            return
        self.recompute()
        label = "; ".join(changes)
        self.events.add(self.time_s, "boundary", f"Boundary condition changed: {label}")
        self._emit_outcome(_PendingOutcome("Boundary change", None, None, before))
        self._record_sample(force=True)

    def set_fluid(self, **kw: float) -> None:
        before = self._key_values()
        f = self.fluid
        new = ConstantPropertyLiquid(
            name=f.name,
            rho=kw.get("density") or f.rho,
            mu=kw.get("viscosity") or f.mu,
            cp=kw.get("specific_heat") or f.cp,
            beta=f.beta if kw.get("thermal_expansion") is None else kw["thermal_expansion"],
            p_bubble=f.p_bubble if kw.get("bubble_point_pressure") is None else kw["bubble_point_pressure"],
        )
        self.fluid = new
        self.thermal.fluid = new
        self.recompute()
        self.events.add(
            self.time_s, "fluid",
            f"Fluid properties changed: density {new.rho:.0f} kg/m3, viscosity {u.pas_to_cp(new.mu):.2f} cP, "
            f"cp {new.cp:.0f} J/(kg K), bubble point {u.pa_to_bara(new.p_bubble):.1f} bara",
        )
        self._emit_outcome(_PendingOutcome("Fluid change", None, None, before))
        self._record_sample(force=True)

    # --------------------------------------------------------------- outcomes
    def _check_outcomes(self) -> None:
        remaining = []
        for p in self._pending:
            act = self.restrictions[p.tag].actuator if p.tag else None
            if act is None or (not act.is_moving and abs(act.position_pct - (p.target or 0.0)) < 1e-9):
                self._emit_outcome(p)
            else:
                remaining.append(p)
        self._pending = remaining

    def _emit_outcome(self, p: _PendingOutcome) -> None:
        after = self._key_values()
        self.events.add(self.time_s, "outcome", f"Result of {p.label}: {explain_change(self, p.before, after, p.tag)}", component=p.tag)

    # --------------------------------------------------------------- snapshot
    def snapshot(self, include_static: bool = True) -> dict:
        h = self.hyd
        props = self.props
        nodes = []
        for nid in self.topology.node_order:
            n = self.topology.nodes[nid]
            nodes.append({
                "id": nid, "name": n.name, "elevation_m": n.elevation,
                "pressure_pa": h.node_pressure.get(nid),
                "temperature_k": self.thermal.node_temperature.get(nid),
                "state": h.node_state.get(nid),
            })
        elements = []
        for e in self.topology.path:
            d: dict = {
                "id": e.id, "name": e.name, "kind": e.kind, "from": e.from_node, "to": e.to_node,
                "state": h.element_state.get(e.id), "dp_pa": h.element_dp.get(e.id),
            }
            if isinstance(e, PipeElement):
                g = e.geometry
                d.update({
                    "role": e.role, "length_m": g.length, "inner_diameter_m": g.diameter, "roughness_m": g.roughness,
                    "dz_m": g.dz, "overall_htc_w_m2k": e.overall_htc,
                    "hydrostatic_dp_pa": hydrostatic_dp(props.rho, g.dz),
                    "velocity_m_s": (h.q / g.area) if h.ok else None,
                    "reynolds": pipe_reynolds(h.q, props.rho, props.mu, g) if h.ok and h.q != 0 else 0.0,
                })
                if h.ok and h.element_dp.get(e.id) is not None:
                    d["friction_dp_pa"] = h.element_dp[e.id] - d["hydrostatic_dp_pa"] if h.q != 0 else 0.0
            elif isinstance(e, RestrictionElement):
                a = e.actuator
                d.update({
                    "tag": e.tag, "subtype": e.subtype, "position_pct": a.position_pct, "commanded_pct": a.commanded_pct,
                    "moving": a.is_moving, "time_to_target_s": a.time_to_target(), "full_stroke_time_s": a.full_stroke_time_s,
                    "capacity_m2": e.capacity, "characteristic": e.characteristic,
                    "characteristic_description": CHARACTERISTIC_DESCRIPTIONS[e.characteristic],
                    "rangeability": e.rangeability,
                    "supports_intermediate": e.supports_intermediate, "available": e.available,
                    "supported_commands": e.supported_commands(),
                })
                if isinstance(e, ValveElement):
                    d.update({"bore_diameter_m": e.bore_diameter, "loss_coefficient_open": e.loss_coefficient_open})
                else:
                    d.update({"cv_max": e.cv_max})
            else:  # inflow
                d.update({"productivity_index_si": self.ipr.j})
            elements.append(d)

        instruments = []
        for i in self.instruments:
            r = self.readings[i.tag]
            instruments.append({
                "tag": i.tag, "type": i.type, "description": i.description, "node": i.node,
                "high_node": i.high_node, "low_node": i.low_node, "unit_si": i.unit,
                "range_min_si": i.range_min, "range_max_si": i.range_max,
                "pv_si": r.pv, "value_si": r.value, "status": r.status,
            })

        snap = {
            "scenario": {
                "id": self.scenario.id, "name": self.scenario.name,
                "description": self.scenario.description,
                "data_classification": self.scenario.data_classification,
            },
            "status": self.status,
            "time_s": self.time_s,
            "time_scale": self.time_scale,
            "model": MODEL_DESCRIPTION,
            "boundary": {
                "reservoir_pressure_pa": self.ipr.p_res,
                "reservoir_temperature_k": self.ipr.t_res,
                "productivity_index_si": self.ipr.j,
                "downstream_pressure_pa": self.p_boundary,
                "downstream_fluid_temperature_k": self.thermal.t_boundary_fluid,
            },
            "fluid": {
                "name": self.fluid.name, "density_kg_m3": self.fluid.rho, "viscosity_pas": self.fluid.mu,
                "specific_heat_j_kgk": self.fluid.cp, "thermal_expansion_1_k": self.fluid.beta,
                "bubble_point_pressure_pa": self.fluid.p_bubble,
            },
            "hydraulics": {
                "status": h.status, "q_m3s": h.q if h.ok else None,
                "mass_flow_kg_s": h.q * props.rho if h.ok else None,
                "driving_pressure_pa": h.driving_pressure if math.isfinite(h.driving_pressure) else None,
                "residual_pa": h.residual, "iterations": h.iterations, "message": h.message,
            },
            "nodes": nodes,
            "elements": elements,
            "instruments": instruments,
            "diagnostics": [d.to_dict() for d in self.diagnostics],
            "last_event_id": self.events.last_id,
            "last_sample_seq": self.history.last_seq,
        }
        if include_static:
            snap["layout"] = self.scenario.layout.model_dump()
            snap["training_rules"] = self.scenario.training_rules.model_dump()
        return snap


# ------------------------------------------------------------------ explain
def explain_change(engine: SimulationEngine, before: dict, after: dict, tag: str | None) -> str:
    """Plain-language consequence of an operation, from actual model values."""
    q0, q1 = before["q"], after["q"]
    if q1 is None:
        return "no valid operating point could be calculated (see diagnostics)."
    m3d0 = u.m3s_to_m3d(q0) if q0 is not None else None
    m3d1 = u.m3s_to_m3d(q1)
    parts = []
    if m3d0 is None:
        parts.append(f"flow is now {m3d1:.0f} m3/d")
    else:
        parts.append(f"flow {m3d0:.0f} -> {m3d1:.0f} m3/d")
    if tag is not None:
        el = engine.restrictions[tag]
        pu0, pu1 = before["p"].get(el.from_node), after["p"].get(el.from_node)
        pd0, pd1 = before["p"].get(el.to_node), after["p"].get(el.to_node)

        def fmt(a, b):
            if a is None or b is None:
                return "undetermined"
            return f"{u.pa_to_bara(a):.1f} -> {u.pa_to_bara(b):.1f} bara"

        parts.append(f"upstream pressure {fmt(pu0, pu1)}")
        parts.append(f"downstream pressure {fmt(pd0, pd1)}")
        dp1 = after["dp"].get(el.id)
        if dp1 is not None:
            parts.append(f"differential across {tag} now {u.pa_to_bar_delta(dp1):.1f} bar")
    text = "; ".join(parts) + "."
    if q0 not in (None, 0.0) and q1 == 0.0:
        text += (" The flow path is isolated: with no flow there are no friction or restriction losses, so pressure "
                 "on the reservoir side rises toward the static shut-in value (reservoir pressure minus the "
                 "hydrostatic head), and the downstream side settles at the boundary pressure plus hydrostatic head.")
    elif q0 == 0.0 and q1 not in (None, 0.0):
        text += " Production path re-established: the operating point is where reservoir inflow matches the system resistance."
    elif q0 not in (None, 0.0) and q1 != 0.0:
        ratio = q1 / q0
        if abs(ratio - 1) > 1e-3:
            text += f" Flow changed by {100 * (ratio - 1):+.1f} %."
    text += " Temperatures respond over a longer thermal time scale."
    return text
