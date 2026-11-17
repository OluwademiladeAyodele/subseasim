"""Simulation engine: owns the state of one simulated production system.

Two simulation modes share one engine, one command set and one API:

steady (Release 1, quasi-steady)
  * Hydraulics: for the current valve positions and boundary conditions the
    steady operating point of the series path is solved algebraically and
    recalculated instantly. No line-pack, inertia or reservoir transient.
  * Valve/choke positions move at a finite actuator rate.
  * Temperatures are transient (lumped cell energy balance, implicit Euler).
  * Branch subsystems (annulus, chemical injection) are NOT modelled.

dynamic (Release 2)
  * Lumped compressible hydraulic network (production path + annulus +
    chemical-injection circuits + optional radial reservoir), implicit
    Euler + Newton on a FIXED solver step independent of wall clock,
    simulation speed and rendering (see ``simulation.dynamic``).
  * Chemical transport/mixing and fluid temperature on a finite-volume grid
    advected by the calculated flows.
  * Transmitter dynamics (lag, update interval, resolution) on top.
  * The steady series solution is still calculated as a "steady-state
    reference" (where the production path would settle).

The engine is advanced only by ``advance(dt)`` in simulation seconds.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from app.core import units as u
from app.core.config import Settings, settings as default_settings
from app.models.scenario import ScenarioConfig
from app.simulation.build import build_fluid, build_system
from app.scenarios.loader import get_schematic
from app.simulation.control.hydraulics import ControlHydraulics
from app.simulation.fluid_properties.black_oil import P_SC, T_SC, BlackOilFluid, BlackOilParams
from app.simulation.hydraulics.network import _failed as _hyd_failed
from app.models.sand import SandChokeInputs
from app.simulation.mpfm.meter import MPFM
from app.simulation.sand.erosion import MATERIALS
from app.simulation.sand.system import SandChokeSystem, configure_choke, production_choke
from app.simulation.multiphase.report import build_report
from app.simulation.multiphase.steady import solve_steady
from app.simulation.components.elements import (
    CheckValveElement,
    ChokeElement,
    CommandRejected,
    PipeElement,
    RestrictionElement,
    ValveElement,
)
from app.simulation.diagnostics.checks import Diagnostic, run_diagnostics
from app.simulation.dynamic.integrity import IntegrityManager, IntegrityTestRejected, candidate_test_points
from app.simulation.dynamic.model import NO_FLOW_M3S, DynamicModel
from app.simulation.dynamic.network import DynamicSolverError
from app.simulation.flowline.pipe import hydrostatic_dp, pipe_reynolds
from app.simulation.fluid_properties.constant_liquid import ConstantPropertyLiquid
from app.simulation.hydraulics.network import HydraulicResult, solve_hydraulics
from app.simulation.hydraulics.properties import FlowProperties
from app.simulation.instruments.instruments import Reading, measure
from app.simulation.solver.integration import substeps
from app.simulation.state import EventLog, History, SimStatus
from app.simulation.thermodynamics.thermal import ThermalModel
from app.simulation.valves.characteristics import CHARACTERISTIC_DESCRIPTIONS

Mode = Literal["steady", "dynamic"]

MODEL_DESCRIPTION = {
    "hydraulics": "Quasi-steady, single-phase incompressible liquid; series path; linear IPR; "
    "Darcy-Weisbach/Churchill friction; orifice-type restrictions. Recalculated instantly - no pressure transients.",
    "thermal": "Transient lumped energy balance (cells in series, implicit Euler); isenthalpic throttling at restrictions.",
    "valves": "Rate-limited actuator travel (constant stroke speed); generic inherent characteristics, not vendor data.",
    "instruments": "Ideal transmitters within calibrated range (no noise, drift or faults in Release 1).",
}

DYNAMIC_MODEL_DESCRIPTION = {
    "hydraulics": "DYNAMIC: lumped compressible network - node mass balance C dP/dt = sum Q + V beta dT/dt, link momentum "
    "I dQ/dt = dP - rho g dz - R(Q); compliance from liquid compressibility + pipe-wall elasticity (Korteweg); implicit Euler "
    "+ Newton on a fixed step. Pressure waves are represented only approximately (step >> acoustic transit time of a segment).",
    "reservoir": "Radial single-phase diffusion on a logarithmic grid with a constant-pressure outer boundary; kh derived from "
    "the productivity index so the final steady state equals the linear IPR.",
    "transport": "Chemical volume fractions and temperature advected by the calculated link flows (finite volume, upwind, "
    "sub-cycled). Numerical dispersion only (no Taylor dispersion term).",
    "thermal": "Cell energy balance with heat loss to ambient, isenthalpic throttling, enthalpy mixing of injected chemicals; "
    "fluid heat capacity only (pipe-wall/tree-body thermal mass neglected). Annulus: lumped temperature.",
    "valves": "Dead time + rate-limited travel (separate open/close times); seat leakage when closed; check valves with "
    "cracking pressure.",
    "instruments": "First-order sensor lag, update interval and resolution applied to the modelled process value.",
}

#: Production-node pressure rate below which the process counts as settled.
SETTLED_RATE_PA_S = 5.0  # = 0.003 bar/min
SETTLED_HOLD_S = 120.0


class InvalidOperatingInput(ValueError):
    pass


@dataclass
class _PendingOutcome:
    label: str
    tag: str | None
    target: float | None
    before: dict


class SimulationEngine:
    def __init__(self, scenario: ScenarioConfig, cfg: Settings = default_settings, mode: Mode | None = None):
        self.settings = cfg
        self.events = EventLog(cfg.event_log_length)
        self.history = History(cfg.history_length)
        self.time_scale = 1.0
        self._mode_override = mode
        self._fluid_model_override: str | None = None
        #: Sand & choke inputs entered in this session (survive reset / model switches).
        self._sand_inputs: SandChokeInputs | None = None
        self._load(scenario)
        self.events.add(0.0, "scenario", f"Scenario loaded: {scenario.name} ({self.mode} model)")

    # ------------------------------------------------------------------ setup
    def _load(self, scenario: ScenarioConfig) -> None:
        self.scenario = scenario
        self.dyn = None  # a reload must never see the previous run's dynamic model
        self.mode: Mode = self._mode_override or scenario.dynamics.mode
        built = build_system(scenario)
        self.fluid_model = self._fluid_model_override or scenario.fluid_model
        if self.fluid_model == "black_oil" and scenario.black_oil is None:
            self.fluid_model = "single_phase"
        self.bo: BlackOilFluid | None = None
        self.mp_steady = None
        self._ref_dirty = False
        if self.fluid_model == "black_oil":
            bc = scenario.black_oil
            self.bo = BlackOilFluid(self._bo_params(bc.oil_api, bc.gas_specific_gravity, bc.producing_gor_sm3_sm3,
                                                    bc.water_cut_fraction, bc.water_salinity_wt_pct))
            self.mp_gor, self.mp_wc, self.mp_correlation = bc.producing_gor_sm3_sm3, bc.water_cut_fraction, bc.correlation
            st, rho, drdp, drdt, cp = self.bo.mixture(built.ipr.p_res, built.ipr.t_res)
            self.rho_ref = float(rho[0])
            # equivalent "reference" liquid: the network, thermal model and transport work in
            # reference volumes (mass / rho_ref); see docs/MULTIPHASE_FLOW_MODEL.md section 5
            built.fluid = ConstantPropertyLiquid(
                name=f"{bc.name} (three-phase black oil)", rho=self.rho_ref, mu=float(st.mu_l[0]), cp=float(cp[0]),
                beta=float(-drdt[0] / rho[0]), p_bubble=0.0, compressibility=float(drdp[0] / rho[0]))
        self.built = built
        self.topology = built.topology
        self.fluid: ConstantPropertyLiquid = built.fluid
        self.ipr = built.ipr
        self.p_boundary = built.p_boundary
        self.instruments = built.instruments
        self.thermal = ThermalModel(self.topology, self.fluid, self.ipr.t_res, built.t_boundary_fluid)
        self.restrictions: dict[str, RestrictionElement] = {
            e.tag: e for e in self.topology.path if isinstance(e, RestrictionElement)
        }
        for e in built.branch_elements:
            if isinstance(e, RestrictionElement):
                self.restrictions[e.tag] = e
        self._production_tags = {e.tag for e in self.topology.path if isinstance(e, RestrictionElement)}
        self.status: SimStatus = "ready"
        self.time_s = 0.0
        self._step_count = 0
        self._time_debt = 0.0
        self._last_sample_t = -math.inf
        self._pending: list[_PendingOutcome] = []
        self._settle_pending: str | None = None
        self._settle_since: float | None = None
        self.achieved_speed: float | None = None
        self.hyd: HydraulicResult | None = None
        self.ctrl = ControlHydraulics(scenario.control_hydraulics) if scenario.control_hydraulics else None
        self.sand: SandChokeSystem | None = None
        self._sand_health = None
        self._sand_alarm = False
        self._sand_check_t = 0.0
        sand_inputs = self.sand_inputs
        if sand_inputs is not None:
            configure_choke(production_choke(self), sand_inputs)
            if self.bo is not None:
                self.sand = SandChokeSystem(self, sand_inputs)
        self._solve()
        # Initial condition: thermal steady state for the initial configuration.
        self.thermal.step(self.hyd.q if self.hyd.ok else 0.0, self.hyd.element_dp, None)
        self.dyn: DynamicModel | None = None
        self.integrity = IntegrityManager(self)
        if self.mode == "dynamic":
            self.dyn = DynamicModel(scenario, built, self.fluid, self.ipr, self.p_boundary, built.t_boundary_fluid, self.instruments)
            if self.bo is not None:
                self.dyn.attach_multiphase(self.bo, self.rho_ref, self.mp_gor, self.mp_wc, self.mp_correlation)
            self.dyn.initialise(self.hyd)
        if self.sand is not None:
            self.sand._update_rates_only()  # first evaluation once the operating point exists
        self.mpfm: MPFM | None = None
        if scenario.mpfm is not None and self.bo is not None:
            self.mpfm = MPFM(scenario.mpfm, self.bo, self.mp_gor, self.mp_wc)
            self._mpfm_update(force=True)
        self._measure()
        self._record_sample(force=True)

    # ------------------------------------------------------------------ MPFM
    def _mpfm_truth(self) -> tuple[float, float, float, float, float] | None:
        """True local state at the meter: (p, T, mass flow into the node, GOR, WC)."""
        loc = self.mpfm.cfg.location_node  # type: ignore[union-attr]
        nodes = self.topology.node_order
        if loc not in nodes or loc == nodes[0]:
            return None
        up = nodes[nodes.index(loc) - 1]
        if self.dyn is not None:
            d = self.dyn
            hid = d.layout.node_index[loc]
            k = d.mp.pos.get(hid)
            gor_n, wc_n = d.mp.node_composition()
            gor, wc = (float(gor_n[k]), float(wc_n[k])) if k is not None else (self.mp_gor, self.mp_wc)
            w = self.rho_ref * float(d.net.Q[d.prod_out_link[up]])
            return d.node_pressure(loc), d.node_temperature(loc), w, gor, wc
        h = self.hyd
        if not h.ok or h.node_pressure.get(loc) is None:
            return None
        return h.node_pressure[loc], self.thermal.node_temperature.get(loc, self.ipr.t_res), self.rho_ref * max(h.q, 0.0), self.mp_gor, self.mp_wc

    def _mpfm_update(self, force: bool = False) -> None:
        m = self.mpfm
        if m is None or not (force or m.due(self.time_s)):
            return
        tr = self._mpfm_truth()
        if tr is None:
            return
        for old, new in m.update(self.time_s, *tr):
            sev = "error" if new == "BAD" else "warning" if new == "DEGRADED" else "info"
            why = "; ".join(f["message"] for f in m.flags) or "all checks passed"
            self.events.add(self.time_s, "instrument", f"{m.cfg.tag} measurement quality {old} -> {new}: {why}",
                            component=m.cfg.tag, severity=sev)

    # ------------------------------------------------------- sand & choke
    @property
    def sand_inputs(self) -> SandChokeInputs | None:
        if self._sand_inputs is not None:
            return self._sand_inputs
        return self.scenario.sand_choke.model_copy(deep=True) if self.scenario.sand_choke is not None else None

    def set_sand_inputs(self, inputs: SandChokeInputs, label: str = "updated") -> None:
        self._sand_inputs = inputs
        configure_choke(production_choke(self), inputs)
        if self.bo is not None:
            if self.sand is None:
                self.sand = SandChokeSystem(self, inputs)
            else:
                self.sand.apply_inputs(inputs)
        self.recompute()
        if self.dyn is not None:
            self.dyn.net.refresh_restrictions()
        self.events.add(self.time_s, "instrument", f"Sand & choke inputs {label}: predictions recalculated"
                        + ("" if self.bo is not None else " (sand and erosion need the three-phase fluid model)"))
        self._record_sample(force=True)

    def load_sand_example(self) -> None:
        if self.scenario.sand_choke_example is None:
            raise CommandRejected("this scenario has no illustrative sand / choke example")
        self.set_sand_inputs(self.scenario.sand_choke_example.model_copy(deep=True), "replaced by the ILLUSTRATIVE example set")

    def sand_fast_forward(self, days: float) -> None:
        if self.sand is None:
            raise CommandRejected("sand and choke erosion need the three-phase fluid model")
        self.sand.fast_forward(days)
        self.events.add(self.time_s, "instrument",
                        f"Choke wear fast-forwarded {days:g} days at the current operating point (quasi-steady: sand rate, opening "
                        f"and differential held constant); trim service time now {self.sand.service_s / 86400:.0f} days")
        self._sand_events(force=True)
        self._record_sample(force=True)

    def _sand_events(self, force: bool = False) -> None:
        s = self.sand
        if s is None or (not force and self.time_s - self._sand_check_t < 60.0):
            return
        self._sand_check_t = self.time_s
        snap = s.snapshot()
        cat = snap["health"]["category"]
        if self._sand_health is not None and cat != self._sand_health:
            sev = "error" if cat in ("Critical condition", "Changeout assessment required") else "warning" if cat != "Normal" else "info"
            self.events.add(self.time_s, "alarm" if sev != "info" else "instrument",
                            f"Choke health {self._sand_health} -> {cat}: {snap['recommendation']['text']}", component=s.choke.tag if s.choke else None,
                            severity=sev)
        self._sand_health = cat
        alarm = bool(snap["detector"]["alarm"])
        if alarm != self._sand_alarm:
            d = snap["detector"]
            self.events.add(self.time_s, "alarm" if alarm else "instrument",
                            f"{d['tag']} sand {'ALARM' if alarm else 'alarm cleared'}: {d['reading_g_s'] or 0:.3f} g/s "
                            f"(threshold {d['alarm_threshold_g_s']:g} g/s)", component=d["tag"], severity="warning" if alarm else "info")
            self._sand_alarm = alarm

    def set_mpfm_faults(self, **kw) -> None:
        if self.mpfm is None:
            raise CommandRejected("no multiphase flow meter is active (three-phase fluid model required)")
        changes = {k: v for k, v in kw.items() if v is not None}
        if not changes:
            return
        self.mpfm.set_faults(**changes)
        desc = ", ".join(f"{k.replace('_', ' ')} = {v}" for k, v in changes.items())
        self.events.add(self.time_s, "instrument", f"{self.mpfm.cfg.tag} fault settings changed (instructor): {desc}",
                        component=self.mpfm.cfg.tag, severity="warning")
        self._mpfm_update(force=True)

    def calibrate_mpfm(self) -> None:
        if self.mpfm is None:
            raise CommandRejected("no multiphase flow meter is active (three-phase fluid model required)")
        tr = self._mpfm_truth()
        gor, wc = (tr[3], tr[4]) if tr else (self.mp_gor, self.mp_wc)
        self.mpfm.calibrate(self.time_s, self.bo, gor, wc)
        self.events.add(self.time_s, "instrument",
                        f"{self.mpfm.cfg.tag} calibrated: dP zero check, meter PVT updated from a fluid sample "
                        f"(GOR {gor:.0f} Sm3/Sm3, WC {wc * 100:.1f} %, salinity {self.bo.params.water_salinity_wt_pct:.1f} wt%), "
                        "discharge coefficient re-established", component=self.mpfm.cfg.tag)
        self._mpfm_update(force=True)

    @property
    def dt_dynamic(self) -> float:
        return self.settings.dynamic_step_s

    # ------------------------------------------------------------ calculation
    @property
    def props(self) -> FlowProperties:
        return FlowProperties.from_fluid(self.fluid)

    def _bo_params(self, api, gas_sg, gor, wc, salinity) -> BlackOilParams:
        bc = self.scenario.black_oil
        return BlackOilParams(bc.name, api, gas_sg, gor, wc, salinity, bc.oil_specific_heat_j_kgk, bc.gas_specific_heat_j_kgk,
                              bc.water_specific_heat_j_kgk, bc.gas_cp_cv)

    def _node_temperatures(self) -> dict[str, float]:
        out = {self.topology.node_order[0]: self.ipr.t_res}
        if getattr(self, "dyn", None) is not None:
            out.update({nid: self.dyn.node_temperature(nid) for nid in self.topology.node_order[1:]})
        else:
            out.update(self.thermal.node_temperature)
        for nid in self.topology.node_order:
            out.setdefault(nid, self.ipr.t_res)
        return out

    def _solve_multiphase(self) -> None:
        """Steady three-phase operating point (marching solver)."""
        prev = self.hyd.node_pressure if self.hyd is not None and self.hyd.ok else None
        topo = self.topology
        if any(e.is_closed() for e in topo.path):
            # closed-in: static columns at the reference (reservoir-condition) density - approximate
            self.hyd = solve_hydraulics(topo, self.ipr.p_res, self.p_boundary, self.props, prev)
            self.hyd.notes.append("multiphase closed-in reference: static columns at reservoir-condition density (approximate)")
            self.mp_steady = None
            return
        r = solve_steady(topo, self.bo, self.ipr.p_res, self.p_boundary, self.ipr.j, self.rho_ref, self._node_temperatures(),
                         self.mp_gor, self.mp_wc, self.mp_correlation)
        self.mp_steady = r
        if not r.ok:
            self.hyd = _hyd_failed(topo, f"multiphase steady solver: {r.message}")
            return
        self.hyd = HydraulicResult(
            status="solved", q=r.q_ref, node_pressure=dict(r.node_pressure), node_state={n: "flowing" for n in topo.node_order},
            element_dp=dict(r.element_dp), element_state={e.id: "flowing" for e in topo.path}, driving_pressure=math.nan,
            iterations=r.iterations, message=r.message)

    def _solve(self) -> None:
        if self.bo is not None:
            self._solve_multiphase()
            return
        prev = self.hyd.node_pressure if self.hyd is not None and self.hyd.ok else None
        self.hyd = solve_hydraulics(self.topology, self.ipr.p_res, self.p_boundary, self.props, prev)

    def _thermal_refresh(self, dt: float) -> None:
        q = self.hyd.q if self.hyd.ok else 0.0
        self.thermal.step(q, self.hyd.element_dp, dt)

    def _measure(self) -> None:
        if self.dyn is not None:
            self.readings: dict[str, Reading] = self.dyn.readings()
            self.diagnostics: list[Diagnostic] = [Diagnostic(**d) for d in self.dyn.diagnostics()]
            if any(d.severity == "error" for d in self.diagnostics):
                for r in self.readings.values():
                    r.status, r.value = "BAD", None
            return
        temps = self.thermal.node_temperature
        q = self.hyd.q if self.hyd.ok else math.nan
        self.readings = {
            i.tag: measure(i, self.hyd.ok, self.hyd.node_pressure, temps, q) for i in self.instruments
        }
        if self.bo is not None and self.hyd.ok:
            for i in self.instruments:
                r = self.readings[i.tag]
                nid = i.node
                if i.type == "flow" and r.value is not None and nid in self.topology.nodes and self.hyd.node_pressure.get(nid):
                    rho = float(self.bo.state(self.hyd.node_pressure[nid], temps[nid], self.mp_gor, self.mp_wc).rho_ns[0])
                    r.value *= self.rho_ref / rho
                    if r.pv is not None:
                        r.pv *= self.rho_ref / rho
        self.diagnostics = run_diagnostics(self.topology, self.hyd, self.fluid, self.props, temps)
        if any(d.severity == "error" for d in self.diagnostics) and self.hyd.ok:
            # Physically invalid point: flag every reading rather than show plausible numbers.
            for tag, r in self.readings.items():
                if r.status != "NOT_MODELLED":
                    r.status = "BAD"
                    r.value = None

    def recompute(self) -> None:
        """Re-solve hydraulics for the present state without advancing time."""
        self._solve()
        if self.dyn is None:
            self._thermal_refresh(0.0)
            if getattr(self, "mpfm", None) is not None:
                self._mpfm_update(force=True)
        self._measure()

    # ------------------------------------------------------------------- time
    def advance(self, dt_total: float) -> None:
        if self.status != "running" or dt_total <= 0:
            return
        if self.dyn is not None:
            self._advance_dynamic(dt_total)
            return
        moved = False
        for dt in substeps(dt_total, self.settings.max_substep_s):
            self._hydraulics_step(dt)
            moving = [r for r in self.restrictions.values() if r.actuator.is_moving]
            for r in moving:
                r.actuator.step(dt)
            if any(r.tag in self._production_tags for r in moving):
                if self.bo is None:
                    self._solve()
                else:
                    moved = True  # multiphase march is costly: solve once per advance
            self._thermal_refresh(dt)
            self.time_s += dt
        if moved:
            self._solve()
        if self.mpfm is not None:
            self._mpfm_update(force=True)
        if self.sand is not None:
            self.sand.step(dt_total)
            self._sand_events()
        self._measure()
        self._check_outcomes()
        self._record_sample()

    def _advance_dynamic(self, dt_total: float) -> None:
        """Integrate on a fixed global step grid: results are identical for
        any partitioning of the requested interval (deterministic)."""
        dt = self.dt_dynamic
        self._time_debt += dt_total
        n = int(math.floor(self._time_debt / dt + 1e-9))
        self._time_debt -= n * dt
        for _ in range(n):
            try:
                self._dynamic_step(dt)
            except DynamicSolverError as exc:
                self.status = "paused"
                self.events.add(self.time_s, "lifecycle", f"Simulation paused: {exc}", severity="error",
                                detail="The dynamic solver could not find a valid state for this step. The last valid state is kept.")
                break
        self._measure()
        self._check_outcomes()

    def _hydraulics_step(self, dt: float) -> None:
        """Control hydraulics: header pressures, then fail-safe closure of
        the valves whose supply has fallen below its operating minimum."""
        if self.ctrl is None:
            return
        lost, restored = self.ctrl.step(dt)
        for sid in lost:
            sup = self.ctrl.supplies[sid]
            p = u.pa_to_bara(self.ctrl.supply_pressure_at_actuators(sid))
            closing = []
            for tag in self.ctrl.fail_safe_valves(sid):
                el = self.restrictions.get(tag)
                if el is not None and el.actuator.commanded_pct > 0:
                    el.actuator.command(0.0)
                    closing.append(tag)
                    self._pending = [x for x in self._pending if x.tag != tag]
                    self._pending.append(_PendingOutcome(f"{tag} FAIL-SAFE CLOSE", tag, 0.0, self._key_values()))
            self.events.add(
                self.time_s, "alarm",
                f"LOSS OF {sup.name.upper()} HYDRAULIC SUPPLY at the SCM ({p:.0f} bara < {u.pa_to_bara(sup.p_min):.0f} bara minimum). "
                + (f"Fail-safe valves closing: {', '.join(closing)}." if closing else "No fail-safe valve was open."),
                severity="error",
                detail="Spring-return actuators close when the control fluid pressure can no longer hold them open. "
                       "Fail-as-is actuators (choke, metering valves) stay where they are.",
            )
            if closing:
                self._settle_pending = f"{sup.name} hydraulic supply lost"
                self._settle_since = None
        for sid in restored:
            sup = self.ctrl.supplies[sid]
            self.events.add(self.time_s, "operation",
                            f"{sup.name} hydraulic supply restored at the SCM ({u.pa_to_bara(self.ctrl.supply_pressure_at_actuators(sid)):.0f} bara). "
                            "Valves that closed fail-safe stay closed until commanded open.")

    def command_selector(self, tag: str, command: str) -> None:
        if self.ctrl is None or tag not in self.ctrl.selectors:
            raise CommandRejected(f"unknown selector valve {tag!r}")
        if command not in ("open", "close"):
            raise CommandRejected("selector valve command must be 'open' or 'close'")
        sel = self.ctrl.selectors[tag]
        self.ctrl.command_selector(tag, command == "open")
        h = self.ctrl.headers[sel.header]
        note = "" if self.status == "running" else " - simulation not running: the valve will move when the simulation runs"
        self.events.add(self.time_s, "operation",
                        f"Selector valve {tag} {command.upper()} commanded ({h.name}, stroke ~{sel.stroke_time_s:g} s){note}", component=tag)

    def set_hydraulic_supply(self, supply_id: str, available: bool) -> None:
        if self.ctrl is None or supply_id not in self.ctrl.supplies:
            raise CommandRejected(f"unknown hydraulic supply {supply_id!r}")
        sup = self.ctrl.supplies[supply_id]
        if sup.available == available:
            return
        self.ctrl.set_supply_available(supply_id, available)
        self.events.add(self.time_s, "operation" if available else "alarm",
                        f"{sup.name} hydraulic supply from the HPU {'RESTORED' if available else 'LOST (HPU trip / umbilical failure)'}",
                        component=supply_id, severity="info" if available else "warning")

    def _dynamic_step(self, dt: float) -> None:
        self._hydraulics_step(dt)
        moving = [r for r in self.restrictions.values() if r.actuator.is_moving]
        for r in moving:
            r.actuator.step(dt)
        if any(r.tag in self._production_tags for r in moving):
            if self.bo is None:
                self._solve()  # steady-state reference for the new positions
            else:
                self._ref_dirty = True  # multiphase march: recomputed once the valves stop
        elif self._ref_dirty and not any(r.actuator.is_moving for r in self.restrictions.values()):
            self._solve()
            self._ref_dirty = False
        t_next = (self._step_count + 1) * dt
        self.dyn.step(dt, t_next)  # type: ignore[union-attr]
        self._step_count += 1
        self.time_s = t_next
        if self.mpfm is not None:
            self._mpfm_update()
        if self.sand is not None:
            self.sand.step(dt)
            self._sand_events()
        if moving:
            self.readings = self.dyn.readings()  # type: ignore[union-attr]
            self._check_outcomes()
        self.integrity.update()
        self._chemical_events()
        self._check_settled()
        self._record_sample()

    def _sample_interval(self) -> float:
        base = self.settings.sample_interval_s
        if self.dyn is None:
            return base
        return max(base, self.time_scale * self.settings.tick_period_s)

    def _record_sample(self, force: bool = False) -> None:
        if not force and self.time_s - self._last_sample_t < self._sample_interval() - 1e-9:
            return
        self._last_sample_t = self.time_s
        if self.dyn is not None:
            self.readings = self.dyn.readings()
            s: dict = {"t": self.time_s, "q": self._q_dyn()}
            ref = self.hyd
            for i in self.instruments:
                if i.type in ("pressure", "flow") and ref.ok and i.node in ref.node_pressure and i.element is None:
                    if i.type == "pressure":
                        s[f"ref:{i.tag}"] = ref.node_pressure.get(i.node)
                    else:
                        s[f"ref:{i.tag}"] = ref.q
        else:
            s = {"t": self.time_s, "q": self.hyd.q if self.hyd.ok else None}
        for tag, r in self.readings.items():
            s[f"inst:{tag}"] = r.value
        sd = getattr(self, "sand", None)
        if sd is not None and sd.rates:
            s["sand:choke_g_s"] = sd.rates.get("m_sand_choke", 0.0) * 1000.0
            r = sd.det.get("reading_kg_s")
            s["sand:detector_g_s"] = None if r is None else r * 1000.0
            dd = sd.dd_cal()
            s["sand:max_hole_mm"] = float(dd.max()) * 1000.0 if dd.size else None
        m = getattr(self, "mpfm", None)
        if m is not None and m.truth is not None:
            t_d = m.truth_derived(m.truth)
            meas = m.filtered if m.reading is not None and m.quality != "BAD" else {}
            for k in ("oil_sm3_d", "gas_sm3_d", "water_sm3_d", "water_cut"):
                s[f"mpfm:{k}"] = meas.get(k)
                s[f"mpfm_true:{k}"] = t_d[k]
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
        self._mode_override = None
        if scenario.id != self.scenario.id:
            self._sand_inputs = None
        self._load(scenario)
        self.events.add(0.0, "scenario", f"Scenario loaded: {scenario.name} ({self.mode} model)")

    def set_mode(self, mode: Mode) -> None:
        """Switch model and restart from the scenario initial conditions."""
        if mode not in ("steady", "dynamic"):
            raise CommandRejected("mode must be 'steady' or 'dynamic'")
        self._mode_override = mode
        self.history.clear()
        self._load(self.scenario)
        self.events.add(0.0, "lifecycle", f"Simulation model set to {mode.upper()} - restarted from scenario initial conditions")

    def set_time_scale(self, scale: float) -> None:
        if scale not in self.settings.allowed_time_scales:
            raise CommandRejected(f"time scale must be one of {self.settings.allowed_time_scales}")
        self.time_scale = scale
        self.events.add(self.time_s, "lifecycle", f"Simulation speed set to {scale:g}x (solver step unchanged: "
                        f"{self.dt_dynamic:g} s)" if self.dyn is not None else f"Simulation speed set to {scale:g}x")

    # --------------------------------------------------------------- commands
    def _key_values(self) -> dict:
        h = self.hyd
        out = {"q": h.q if h.ok else None, "p": dict(h.node_pressure), "dp": dict(h.element_dp)}
        if self.dyn is not None:
            out["q"] = self._q_dyn()
            out["p"] = {nid: self.dyn.node_pressure(nid) for nid in self.dyn.layout.node_index if "#" not in nid}
            out["dp"] = {e.id: self._dp_dyn(e) for e in self.dyn.elements.values()}
        return out

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

        if self.ctrl is not None and target > act.commanded_pct:
            ok, why = self.ctrl.can_open(tag)
            if not ok:
                self.events.add(self.time_s, "rejected", f"Command rejected: {tag} {why}", component=tag, severity="warning")
                raise CommandRejected(f"{tag}: {why}")

        if (isinstance(el, ValveElement) and el.subtype != "injection_isolation"
                and target > act.position_pct and act.position_pct == 0.0):
            self._check_opening_rule(el)

        act.command(target)
        travel = act.time_to_target()
        note = "" if self.status == "running" else " - simulation not running: valve will move when the simulation runs"
        delay = f", dead time {act.delay_s:g} s" if act.delay_s > 0 else ""
        self.events.add(
            self.time_s, "operation",
            f"{tag} {verb} commanded ({act.position_pct:.1f} % -> {target:.1f} %, travel ~{travel:.0f} s{delay}){note}",
            component=tag,
        )
        self._pending = [p for p in self._pending if p.tag != tag]
        self._pending.append(_PendingOutcome(f"{tag} {verb}", tag, target, self._key_values()))
        self._settle_pending = f"{tag} {verb}"
        self._settle_since = None

    def _check_opening_rule(self, el: ValveElement) -> None:
        limit_bar = self.scenario.training_rules.max_opening_differential_bar
        if limit_bar is None:
            return
        if self.dyn is not None:
            dp = self._dp_dyn(el)
        elif el.tag in self._production_tags:
            dp = self.hyd.element_dp.get(el.id)
        else:
            return
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
            if self.dyn is not None:
                self.dyn.set_reservoir_productivity(productivity_index_si)
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
            if self.dyn is not None:
                self.dyn.p_boundary = downstream_pressure_pa
        if not changes:
            return
        self.recompute()
        label = "; ".join(changes)
        self.events.add(self.time_s, "boundary", f"Boundary condition changed: {label}")
        if self.dyn is not None:
            # The boundary acts at the system ends only; everything inside
            # responds over simulated time (logged separately when settled).
            self._settle_pending = "boundary change"
            self._settle_since = None
            self.events.add(self.time_s, "outcome", "Result of Boundary change: the new boundary acts at the system ends; "
                            "interior pressures, flows and temperatures will evolve over simulated time "
                            f"(steady-state reference flow {self._fmt_q(self.hyd.q if self.hyd.ok else None)}).")
        else:
            self._emit_outcome(_PendingOutcome("Boundary change", None, None, before))
        self._record_sample(force=True)

    def set_fluid_model(self, model: str) -> None:
        """Switch single-phase / three-phase and restart from the scenario initial conditions."""
        if model not in ("single_phase", "black_oil"):
            raise CommandRejected("fluid model must be 'single_phase' or 'black_oil'")
        if model == "black_oil" and self.scenario.black_oil is None:
            raise CommandRejected("this scenario has no black-oil fluid configuration")
        self._fluid_model_override = model
        self.history.clear()
        self._load(self.scenario)
        label = "THREE-PHASE black oil (oil, gas, water)" if model == "black_oil" else "SINGLE-PHASE liquid (simplified)"
        self.events.add(0.0, "fluid", f"Fluid model set to {label} - restarted from scenario initial conditions")

    def set_black_oil(self, producing_gor_sm3_sm3: float | None = None, water_cut: float | None = None,
                      oil_api: float | None = None, gas_specific_gravity: float | None = None,
                      water_salinity_wt_pct: float | None = None, correlation: str | None = None) -> None:
        """Change the reservoir fluid. GOR / water cut change the composition
        ENTERING the well (it is transported up the well with the fluid);
        API, gas gravity and salinity re-characterise the fluid everywhere."""
        if self.bo is None:
            raise CommandRejected("the three-phase fluid model is not active (switch the fluid model first)")
        p = self.bo.params
        msgs = []
        if producing_gor_sm3_sm3 is not None or water_cut is not None:
            gor = p.gor_sm3_sm3 if producing_gor_sm3_sm3 is None else producing_gor_sm3_sm3
            wc = self.mp_wc if water_cut is None else water_cut
            if not (0 <= gor <= 2000 and 0 <= wc <= 0.98):
                raise InvalidOperatingInput("GOR must be 0-2000 Sm3/Sm3 and water cut 0-0.98")
            msgs.append(f"producing GOR {self.mp_gor:.0f} -> {gor:.0f} Sm3/Sm3, water cut {100 * self.mp_wc:.1f} -> {100 * wc:.1f} %")
            self.mp_gor, self.mp_wc = gor, wc
            if self.dyn is not None:
                self.dyn.mp.set_reservoir_composition(gor, wc)
        recharacterise = any(v is not None for v in (oil_api, gas_specific_gravity, water_salinity_wt_pct))
        if recharacterise:
            api = p.api if oil_api is None else oil_api
            sg = p.gas_sg if gas_specific_gravity is None else gas_specific_gravity
            sal = p.water_salinity_wt_pct if water_salinity_wt_pct is None else water_salinity_wt_pct
            if not (10 <= api <= 70 and 0.55 <= sg <= 1.5 and 0 <= sal <= 26):
                raise InvalidOperatingInput("API 10-70, gas gravity 0.55-1.5, salinity 0-26 wt%")
            msgs.append(f"oil {p.api:.1f} -> {api:.1f} API, gas SG {p.gas_sg:.3f} -> {sg:.3f}, salinity {p.water_salinity_wt_pct:.1f} -> {sal:.1f} wt%")
        self.bo = BlackOilFluid(self._bo_params(
            p.api if oil_api is None else oil_api, p.gas_sg if gas_specific_gravity is None else gas_specific_gravity,
            self.mp_gor, self.mp_wc, p.water_salinity_wt_pct if water_salinity_wt_pct is None else water_salinity_wt_pct))
        if correlation is not None:
            if correlation not in ("beggs_brill", "no_slip"):
                raise InvalidOperatingInput("correlation must be 'beggs_brill' or 'no_slip'")
            msgs.append(f"multiphase correlation {self.mp_correlation} -> {correlation}")
            self.mp_correlation = correlation
        if self.dyn is not None:
            self.dyn.mp.fluid = self.bo
            self.dyn.mp.correlation = self.mp_correlation
            self.dyn.mp._last_P = None  # force a property re-evaluation
        if self.mpfm is not None:
            self.mpfm.set_true_fluid(self.bo)
        if not msgs:
            return
        self.recompute()
        self.events.add(self.time_s, "fluid", "Reservoir fluid changed: " + "; ".join(msgs),
                        detail=("A GOR / water-cut change applies to fluid ENTERING the well and travels up with it; "
                                "a re-characterisation (API, gas gravity, salinity) changes the properties everywhere at once."))
        self._settle_pending = "fluid change"
        self._settle_since = None
        self._record_sample(force=True)

    def set_fluid(self, **kw: float) -> None:
        if self.bo is not None:
            raise InvalidOperatingInput("the three-phase fluid is active: change it with the black-oil inputs (GOR, water cut, API, gas gravity)")
        before = self._key_values()
        f = self.fluid
        new = ConstantPropertyLiquid(
            name=f.name,
            rho=kw.get("density") or f.rho,
            mu=kw.get("viscosity") or f.mu,
            cp=kw.get("specific_heat") or f.cp,
            beta=f.beta if kw.get("thermal_expansion") is None else kw["thermal_expansion"],
            p_bubble=f.p_bubble if kw.get("bubble_point_pressure") is None else kw["bubble_point_pressure"],
            compressibility=f.compressibility,
        )
        self.fluid = new
        self.thermal.fluid = new
        if self.dyn is not None:
            self.dyn.set_fluid(new)
        self.recompute()
        self.events.add(
            self.time_s, "fluid",
            f"Fluid properties changed: density {new.rho:.0f} kg/m3, viscosity {u.pas_to_cp(new.mu):.2f} cP, "
            f"cp {new.cp:.0f} J/(kg K), bubble point {u.pa_to_bara(new.p_bubble):.1f} bara",
        )
        if self.dyn is None:
            self._emit_outcome(_PendingOutcome("Fluid change", None, None, before))
        else:
            self._settle_pending = "fluid change"
            self._settle_since = None
        self._record_sample(force=True)

    # ------------------------------------------------------ chemical injection
    def _circuit(self, chem_id: str):
        if self.dyn is None:
            raise CommandRejected("chemical injection is modelled only in the dynamic simulation mode")
        for c in self.dyn.circuits:
            if c.cfg.id == chem_id:
                return c
        raise CommandRejected(f"unknown chemical circuit {chem_id!r}")

    def set_pump(self, chem_id: str, running: bool | None = None, discharge_pressure_pa: float | None = None) -> None:
        c = self._circuit(chem_id)
        msgs = []
        if discharge_pressure_pa is not None:
            pmax = u.bara_to_pa(c.cfg.pump.max_discharge_pressure_bara)
            if not 1e5 < discharge_pressure_pa <= pmax:
                raise InvalidOperatingInput(f"discharge pressure must be between 1 and {c.cfg.pump.max_discharge_pressure_bara:g} bara")
            msgs.append(f"discharge pressure {u.pa_to_bara(c.p_discharge):.1f} -> {u.pa_to_bara(discharge_pressure_pa):.1f} bara")
            c.p_discharge = discharge_pressure_pa
        if running is not None and running != c.running:
            c.running = running
            msgs.append("pump STARTED" if running else "pump STOPPED (supply falls to static head)")
        if not msgs:
            return
        dp = self.dyn.available_differential(c)  # type: ignore[union-attr]
        self.events.add(self.time_s, "chemical", f"{c.cfg.name} injection pump: {'; '.join(msgs)}. "
                        f"Available differential at {c.inj_node}: {u.pa_to_bar_delta(dp):+.1f} bar", component=c.cfg.id)
        self._settle_pending = f"{c.cfg.name} pump"
        self._settle_since = None

    def _chemical_events(self) -> None:
        for c, old, new, route in self.dyn.update_circuit_status():  # type: ignore[union-attr]
            if route == "annulus":
                qa = float(self.dyn.net.Q[c.ann_link])  # type: ignore[union-attr, index]
                if new == "injecting":
                    self.events.add(self.time_s, "chemical",
                                    f"{c.cfg.name} injection into the ANNULUS SERVICE LINE started: {qa * 3600 * 1000:.1f} L/h "
                                    f"through {c.cfg.annulus_valve}", component=c.cfg.id)
                elif old == "injecting":
                    self.events.add(self.time_s, "chemical",
                                    f"{c.cfg.name} injection into the annulus service line stopped ({new.replace('_', ' ')})",
                                    component=c.cfg.id)
                continue
            if route.startswith("route:"):
                r = next(x for x in c.routes if x.cfg.id == route[6:])
                qr = float(self.dyn.net.Q[r.link])  # type: ignore[union-attr]
                where = self.topology.nodes[r.inj_node].name
                if new == "injecting":
                    self.events.add(self.time_s, "chemical",
                                    f"{c.cfg.name} injection through {r.cfg.valve} STARTED: {qr * 3600 * 1000:.1f} L/h entering "
                                    f"the production stream at {where}", component=c.cfg.id)
                elif old == "injecting":
                    self.events.add(self.time_s, "chemical",
                                    f"{c.cfg.name} injection through {r.cfg.valve} stopped ({new.replace('_', ' ')})",
                                    component=c.cfg.id)
                continue
            q = float(self.dyn.net.Q[c.inj_link])  # type: ignore[union-attr]
            if new == "injecting":
                msg = (f"{c.cfg.name} injection STARTED: {q * 3600 * 1000:.1f} L/h entering the production stream at "
                       f"{self.topology.nodes[c.inj_node].name}")
                sev = "info"
            elif old == "injecting":
                why = {"isolated": "isolation valve closed", "pump_stopped": "pump stopped", "metering_closed": "metering valve closed",
                       "insufficient_differential": "insufficient pressure differential (check valve closed)"}.get(new, new)
                msg = (f"{c.cfg.name} injection STOPPED ({why}). Chemical already in the production line continues to move "
                       f"with the production flow.")
                sev = "warning" if new == "insufficient_differential" else "info"
            else:
                continue
            self.events.add(self.time_s, "chemical", msg, component=c.cfg.id, severity=sev)

    # ------------------------------------------------------ integrity testing
    def start_integrity_test(self, **kw) -> None:
        try:
            self.integrity.start(**kw)
        except IntegrityTestRejected as exc:
            self.events.add(self.time_s, "rejected", f"Integrity test rejected: {exc}", severity="warning")
            raise CommandRejected(str(exc)) from None
        self._measure()

    def abort_integrity_test(self, test_id: int) -> None:
        try:
            self.integrity.abort(test_id)
        except IntegrityTestRejected as exc:
            raise CommandRejected(str(exc)) from None

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
        if self.dyn is not None:
            self.events.add(self.time_s, "valve", f"{p.tag} reached {p.target:.1f} % (end of travel)", component=p.tag)
            self.events.add(self.time_s, "outcome", f"Result of {p.label}: {explain_dynamic(self, p.before, after, p.tag)}", component=p.tag)
            return
        self.events.add(self.time_s, "outcome", f"Result of {p.label}: {explain_change(self, p.before, after, p.tag)}", component=p.tag)

    def _check_settled(self) -> None:
        if self._settle_pending is None or self._pending:
            return
        rate = self.dyn.max_rate_pa_s  # type: ignore[union-attr]
        if rate > SETTLED_RATE_PA_S:
            self._settle_since = None
            return
        if self._settle_since is None:
            self._settle_since = self.time_s
            return
        if self.time_s - self._settle_since >= SETTLED_HOLD_S:
            q = self._q_dyn()
            self.events.add(self.time_s, "process",
                            f"Process response to {self._settle_pending} has SETTLED (all pressures changing by less than "
                            f"{SETTLED_RATE_PA_S * 60 / 1e5:.3f} bar/min): flow {self._fmt_q(q)}.")
            self._settle_pending = None

    @staticmethod
    def _fmt_q(q: float | None) -> str:
        return "undetermined" if q is None else f"{u.m3s_to_m3d(q):.1f} m3/d"

    # -------------------------------------------------------------- dynamic
    def _q_dyn(self) -> float | None:
        d = self.dyn
        if d is None or d.failed:
            return None
        last = self.topology.path[-1]
        return d.element_flow(last.id)

    def _dp_dyn(self, e) -> float | None:
        d = self.dyn
        return d.node_pressure(e.from_node) - d.node_pressure(e.to_node)  # type: ignore[union-attr]

    # --------------------------------------------------------------- snapshot
    def snapshot(self, include_static: bool = True) -> dict:
        if self.dyn is not None:
            return self._snapshot_dynamic(include_static)
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
        for nid, n in self.built.branch_nodes.items():
            nodes.append({"id": nid, "name": n.name, "elevation_m": n.elevation, "pressure_pa": None,
                          "temperature_k": None, "state": "not_modelled"})
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
                d.update(self._restriction_static(e))
            else:  # inflow
                d.update({"productivity_index_si": self.ipr.j})
            elements.append(d)
        for e in self.built.branch_elements:
            d = {"id": e.id, "name": e.name, "kind": e.kind, "from": e.from_node, "to": e.to_node, "state": "not_modelled",
                 "dp_pa": None, "branch": True}
            if isinstance(e, PipeElement):
                d.update(self._pipe_static(e))
            elif isinstance(e, RestrictionElement):
                d.update(self._restriction_static(e))
            elif isinstance(e, CheckValveElement):
                d.update({"tag": e.tag, "cracking_pressure_pa": e.cracking_pressure})
            elements.append(d)

        snap = self._common_snapshot(include_static)
        snap.update({
            "model": MODEL_DESCRIPTION,
            "hydraulics": {
                "status": h.status, "q_m3s": h.q if h.ok else None,
                "mass_flow_kg_s": h.q * props.rho if h.ok else None,
                "driving_pressure_pa": h.driving_pressure if math.isfinite(h.driving_pressure) else None,
                "residual_pa": h.residual, "iterations": h.iterations, "message": h.message,
            },
            "nodes": nodes,
            "elements": elements,
            "instruments": self._instrument_snapshot(),
            "diagnostics": [d.to_dict() for d in self.diagnostics],
        })
        return snap

    def _common_snapshot(self, include_static: bool) -> dict:
        snap = {
            "scenario": {
                "id": self.scenario.id, "name": self.scenario.name,
                "description": self.scenario.description,
                "data_classification": self.scenario.data_classification,
            },
            "mode": self.mode,
            "status": self.status,
            "time_s": self.time_s,
            "time_scale": self.time_scale,
            "clock": {
                "elapsed_s": self.time_s,
                "time_of_day_s": (self.scenario.dynamics.clock_start_s + self.time_s) % 86400.0,
                "solver_step_s": self.dt_dynamic if self.dyn is not None else self.settings.max_substep_s,
                "fixed_step": self.dyn is not None,
                "achieved_speed": self.achieved_speed,
                "allowed_speeds": list(self.settings.allowed_time_scales),
            },
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
                "bubble_point_pressure_pa": self.fluid.p_bubble, "compressibility_1_pa": self.fluid.compressibility,
            },
            "last_event_id": self.events.last_id,
            "last_sample_seq": self.history.last_seq,
            "briefing": self.scenario.briefing,
            "control_hydraulics": self.ctrl.snapshot() if self.ctrl is not None else None,
            "fluid_model": self.fluid_model,
            "multiphase": build_report(self) if self.bo is not None else None,
            "sand_choke": (self.sand.snapshot() if self.sand is not None else
                           {"available": False, "reason": "Sand production, detection and choke erosion need the three-phase "
                            "(black-oil) fluid model and sand / choke inputs."}),
            "mpfm": (self.mpfm.snapshot(self.time_s) if self.mpfm is not None else
                     {"tag": self.scenario.mpfm.tag, "quality": "NOT_MODELLED",
                      "reason": "The multiphase flow meter requires the three-phase (black-oil) fluid model."}
                     if self.scenario.mpfm is not None else None),
        }
        if include_static:
            snap["layout"] = self.scenario.layout.model_dump()
            snap["tag_aliases"] = {k: v.model_dump() for k, v in self.scenario.tag_aliases.items()}
            snap["fluid_models"] = ["single_phase"] + (["black_oil"] if self.scenario.black_oil is not None else [])
            si = self.sand_inputs
            snap["sand_choke_inputs"] = si.model_dump() if si is not None else None
            snap["sand_choke_example_available"] = self.scenario.sand_choke_example is not None
            snap["erosion_materials"] = [{"key": m.key, "name": m.name, "k": m.k, "n": m.n, "density_kg_m3": m.density,
                                          "behaviour": m.behaviour, "source": m.source} for m in MATERIALS.values()]
            snap["schematic"] = get_schematic(self.scenario.schematic) if self.scenario.schematic else None
            snap["training_rules"] = self.scenario.training_rules.model_dump()
            snap["integrity_presets"] = [p.model_dump() for p in self.scenario.integrity_tests]
            snap["chemical_config"] = [
                {"id": c.id, "name": c.name, "color": c.color, "display_unit": c.display_unit,
                 "target_min": c.target_min, "target_max": c.target_max}
                for c in self.scenario.chemicals
            ]
        return snap

    def _restriction_static(self, e: RestrictionElement) -> dict:
        a = e.actuator
        d = {
            "tag": e.tag, "subtype": e.subtype, "position_pct": a.position_pct, "commanded_pct": a.commanded_pct,
            "moving": a.is_moving, "phase": a.phase, "time_to_target_s": a.time_to_target(),
            "full_stroke_time_s": a.full_stroke_time_s, "close_stroke_time_s": a.close_stroke_time_s or a.full_stroke_time_s,
            "actuation_delay_s": a.delay_s, "nominal_stroke_time_s": e.nominal_stroke_time_s,
            "seat_leak_area_mm2": e.seat_leak_capacity * 1e6,
            "capacity_m2": e.capacity, "characteristic": e.characteristic,
            "characteristic_description": CHARACTERISTIC_DESCRIPTIONS[e.characteristic],
            "rangeability": e.rangeability,
            "supports_intermediate": e.supports_intermediate, "available": e.available,
            "supported_commands": e.supported_commands(),
        }
        if isinstance(e, ValveElement):
            d.update({"bore_diameter_m": e.bore_diameter, "loss_coefficient_open": e.loss_coefficient_open})
        elif isinstance(e, ChokeElement):
            d.update({"cv_max": e.cv_max})
        return d

    @staticmethod
    def _pipe_static(e: PipeElement) -> dict:
        g = e.geometry
        return {"role": e.role, "length_m": g.length, "inner_diameter_m": g.diameter, "roughness_m": g.roughness,
                "dz_m": g.dz, "overall_htc_w_m2k": e.overall_htc}

    def _instrument_snapshot(self) -> list[dict]:
        out = []
        for i in self.instruments:
            r = self.readings[i.tag]
            d = {
                "tag": i.tag, "type": i.type, "description": i.description, "node": i.node,
                "high_node": i.high_node, "low_node": i.low_node, "unit_si": i.unit,
                "range_min_si": i.range_min, "range_max_si": i.range_max,
                "pv_si": r.pv, "value_si": r.value, "status": r.status,
                "element": i.element, "distance_m": i.distance_m, "chemical": i.chemical, "display_unit": i.display_unit,
            }
            if i.response is not None:
                d["response"] = {"time_constant_s": i.response.time_constant_s, "update_interval_s": i.response.update_interval_s,
                                 "resolution_si": i.response.resolution_si}
            out.append(d)
        return out

    def _snapshot_dynamic(self, include_static: bool) -> dict:
        dyn = self.dyn
        assert dyn is not None
        net = dyn.net
        idx = dyn.layout.node_index
        props = self.props
        states = dyn.node_states()
        nodes = []
        for nid, n in {**self.topology.nodes, **self.built.branch_nodes}.items():
            i = idx[nid]
            nodes.append({
                "id": nid, "name": n.name, "elevation_m": n.elevation,
                "pressure_pa": float(net.P[i]), "temperature_k": dyn.node_temperature(nid),
                "state": states.get(i, "flowing"),
                "rate_pa_s": float((net.P[i] - dyn.p_prev[i]) / self.dt_dynamic),
                "steady_pressure_pa": self.hyd.node_pressure.get(nid) if self.hyd.ok else None,
                "boundary": bool(net.fixed[i]),
            })
        elements = []
        lay = dyn.layout
        F = dyn.grid.face_flows(net.Q)
        for e in [*self.topology.path, *self.built.branch_elements]:
            branch = e in self.built.branch_elements
            d: dict = {"id": e.id, "name": e.name, "kind": e.kind, "from": e.from_node, "to": e.to_node, "branch": branch,
                       "dp_pa": self._dp_dyn(e)}
            if isinstance(e, PipeElement):
                info = lay.pipes[e.id]
                q_in, q_out = float(net.Q[info.link_idx[0]]), float(net.Q[info.link_idx[-1]])
                states_l = [dyn.link_state(li) for li in info.link_idx]
                d["state"] = "flowing" if "flowing" in states_l else "no_flow"
                g = e.geometry
                z = lay.zones[info.zone]
                dp = d["dp_pa"]
                hyd_dp = z.rho * u.G * g.dz
                pack = float(sum(net.cap_node[i] * (net.P[i] - dyn.p0[i]) for i in info.node_idx[1:-1]))
                d.update(self._pipe_static(e))
                d.update({
                    "zone": info.zone, "hydrostatic_dp_pa": hyd_dp, "friction_dp_pa": None if dp is None else dp - hyd_dp,
                    "velocity_m_s": q_in / info.area, "reynolds": z.rho * abs(q_in) / info.area * info.hydraulic_diameter / z.mu,
                    "inlet_flow_m3s": q_in, "outlet_flow_m3s": q_out,
                    "volume_m3": info.volume, "capacitance_m3_per_pa": info.capacitance,
                    "wave_speed_m_s": info.wave_speed, "acoustic_transit_s": g.length / info.wave_speed,
                    "residence_time_s": info.volume / abs(q_in) if abs(q_in) > NO_FLOW_M3S else None,
                    "segments": info.segments, "linepack_change_m3": pack,
                    "pressure_profile": [{"x_m": x, "p_pa": float(net.P[i])} for i, x in zip(info.node_idx, [k * g.length / info.segments for k in range(info.segments + 1)])],
                })
                if e.id in dyn.grid.cell_of_pipe:
                    cells = dyn.grid.cell_of_pipe[e.id]
                    stride = max(1, len(cells) // 40)
                    sel = cells[::stride]
                    x0 = dyn.grid.pos[cells[0]] - dyn.grid.dx[cells[0]] / 2
                    d["profile"] = {
                        "x_m": [float(dyn.grid.pos[c] - x0) for c in sel],
                        "t_k": [float(dyn.grid.T[c]) for c in sel],
                        "c": {cid: [float(dyn.grid.c[k, c]) for c in sel] for k, cid in enumerate(dyn.chem_ids)},
                    }
            else:
                li = lay.element_link.get(e.id)
                d["state"] = dyn.link_state(li) if li is not None else "no_flow"
                d["flow_m3s"] = float(net.Q[li]) if li is not None else None
                if isinstance(e, RestrictionElement):
                    d.update(self._restriction_static(e))
                    d["leaking"] = bool(e.capacity <= 0 and e.seat_leak_capacity > 0 and li is not None and abs(net.Q[li]) > 1e-12)
                elif isinstance(e, CheckValveElement):
                    d.update({"tag": e.tag, "cracking_pressure_pa": e.cracking_pressure, "open": d["state"] != "closed"})
                else:
                    d.update({"productivity_index_si": self.ipr.j})
            elements.append(d)

        q = self._q_dyn()
        any_closed = any(dyn.link_state(lay.element_link[e.id]) == "closed" for e in self.topology.path if isinstance(e, RestrictionElement))
        hyd_status = "failed" if dyn.failed else ("closed_in" if any_closed else "solved")
        h = self.hyd
        chems = []
        for c in dyn.circuits:
            qi = float(net.Q[c.inj_link])
            front = dyn.chemical_front(c)
            analysers = []
            for inst in self.instruments:
                if inst.type == "concentration" and inst.chemical == c.cfg.id:
                    cell = None
                    if inst.element and inst.element in dyn.grid.cell_of_pipe:
                        cell = dyn.grid.cell_at(inst.element, inst.distance_m or 0)
                    elif inst.node in dyn.grid.node_lookup:
                        lk = dyn.grid.node_lookup[inst.node]
                        cell = lk.cell if lk.cell is not None else min(lk.face or 0, dyn.grid.n - 1)
                    analysers.append({
                        "tag": inst.tag,
                        "distance_from_injection_m": None if cell is None else float(dyn.grid.pos[cell] - front["path_position_m"]),
                        "plug_flow_transit_s": None if cell is None else dyn.plug_flow_time(c.inj_node, cell),
                    })
            q_prod = float(F[min(front["injection_cell"] + 1, dyn.grid.n)])
            chems.append({
                "id": c.cfg.id, "name": c.cfg.name, "status": c.status, "pump_running": c.running,
                "discharge_pressure_pa": c.p_discharge, "static_pressure_pa": c.p_static,
                "supply_pressure_pa": c.p_supply, "injection_node": c.inj_node,
                "injection_node_name": self.topology.nodes[c.inj_node].name,
                "injection_flow_m3s": qi, "available_differential_pa": dyn.available_differential(c),
                "injection_point_pressure_pa": dyn.node_pressure(c.inj_node),
                "isolation_valve": c.cfg.isolation_valve, "control_valve": c.cfg.control_valve, "check_valve": c.cfg.check_valve,
                "pressure_transmitter": c.cfg.pressure_transmitter, "flow_transmitter": c.cfg.flow_transmitter,
                "total_injection_m3s": dyn.total_injection(c),
                "fully_mixed_concentration": (dyn.total_injection(c) / q_prod
                                              if q_prod > NO_FLOW_M3S and dyn.total_injection(c) > 0 else 0.0),
                "routes": [{
                    "id": r.cfg.id, "name": r.cfg.name, "valve": r.cfg.valve, "check_valve": r.cfg.check_valve,
                    "flow_transmitter": r.cfg.flow_transmitter, "injection_node": r.inj_node,
                    "injection_node_name": self.topology.nodes[r.inj_node].name, "status": r.status,
                    "flow_m3s": float(net.Q[r.link]), "cumulative_m3": r.cum_m3,
                } for r in c.routes],
                "cumulative_injected_m3": c.cum_injected_m3,
                "annulus_route": None if c.ann_link is None else {
                    "valve": c.cfg.annulus_valve, "check_valve": c.cfg.annulus_check_valve,
                    "flow_transmitter": c.cfg.annulus_flow_transmitter, "status": c.ann_status,
                    "flow_m3s": float(net.Q[c.ann_link]), "cumulative_m3": c.cum_to_annulus_m3,
                    "junction_pressure_pa": float(net.P[net.links[c.ann_link].dn]),
                },
                "in_production_line_m3": float(dyn.grid.inventory()[c.k]),
                "exported_m3": float(dyn.grid.out_boundary[c.k]),
                "front_distance_m": front["front_distance_m"],
                "analysers": analysers,
                "color": c.cfg.color, "display_unit": c.cfg.display_unit,
                "target_min": c.cfg.target_min, "target_max": c.cfg.target_max,
            })
        res = lay.reservoir
        snap = self._common_snapshot(include_static)
        snap.update({
            "model": DYNAMIC_MODEL_DESCRIPTION,
            "hydraulics": {
                "status": hyd_status, "q_m3s": q, "mass_flow_kg_s": None if q is None else q * props.rho,
                "driving_pressure_pa": h.driving_pressure if math.isfinite(h.driving_pressure) else None,
                "residual_pa": net.last_residual, "iterations": net.last_iterations,
                "message": dyn.failed or ("converged" if net.last_converged else "not fully converged"),
                "reservoir_inflow_m3s": float(net.Q[lay.element_link[self.topology.path[0].id]]),
                "max_pressure_rate_pa_s": dyn.max_rate_pa_s,
                "process_settling": self._settle_pending,
            },
            "steady_reference": {
                "status": h.status, "q_m3s": h.q if h.ok else None,
                "node_pressure_pa": {k: v for k, v in h.node_pressure.items()},
                "note": "Algebraic steady operating point of the production path for the CURRENT valve positions and "
                "boundaries (excludes injection streams). The dynamic state relaxes toward it.",
            },
            "reservoir_model": None if res is None else {
                "radii_m": res.radii, "kh_m3": res.kh, "permeability_m2": res.k, "diffusivity_m2_s": res.diffusivity,
                "pore_volume_m3": res.pore_volume,
                "pressure_profile_pa": [float(net.P[i]) for i in res.node_idx],
            },
            "annulus": None if dyn.t_ann is None else {"temperature_k": dyn.t_ann},
            "nodes": nodes,
            "elements": elements,
            "instruments": self._instrument_snapshot(),
            "diagnostics": [d.to_dict() for d in self.diagnostics],
            "chemicals": chems,
            "integrity": {"tests": self.integrity.snapshot(), "test_points": candidate_test_points(self)},
            "transport_balance": {
                cid: {"injected_m3": float(dyn.grid.injected[k]), "in_line_m3": float(dyn.grid.inventory()[k]),
                      "exported_m3": float(dyn.grid.out_boundary[k]), "to_reservoir_m3": float(dyn.grid.out_reservoir[k])}
                for k, cid in enumerate(dyn.chem_ids)
            },
        })
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


def explain_dynamic(engine: SimulationEngine, before: dict, after: dict, tag: str | None) -> str:
    """Valve has reached its position - describe the CURRENT (transient) state
    and the steady-state reference it is heading toward."""
    q0, q1 = before["q"], after["q"]
    ref = engine.hyd
    parts = [f"flow at the flowline {engine._fmt_q(q0)} -> {engine._fmt_q(q1)} so far"]
    if tag is not None:
        el = engine.restrictions[tag]
        for side, nid in (("upstream", el.from_node), ("downstream", el.to_node)):
            a, b = before["p"].get(nid), after["p"].get(nid)
            s = f"{side} {u.pa_to_bara(a):.1f} -> {u.pa_to_bara(b):.1f} bara" if a is not None and b is not None else f"{side} undetermined"
            if ref.ok and ref.node_pressure.get(nid) is not None and tag in engine._production_tags:
                s += f" (steady-state reference {u.pa_to_bara(ref.node_pressure[nid]):.1f} bara)"
            parts.append(s)
    text = "; ".join(parts) + "."
    if ref.ok and tag in engine._production_tags:
        text += (f" The VALVE has finished moving but the PROCESS has not necessarily settled: line-pack, wellbore storage and "
                 f"the reservoir pressure transient continue to evolve toward a steady flow of {engine._fmt_q(ref.q)}. "
                 "A separate event is logged when the process settles.")
    else:
        text += " Pressures in the connected volumes continue to evolve according to their mass balance."
    return text
