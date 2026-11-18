"""Scenario comparison: the consequences of alternative operating choices,
calculated with the SAME models as the live session.

Every case runs on a STEADY TWIN of the session: a separate engine in the
steady model, given the session's current state (valve and choke positions,
boundary conditions, fluid, sand / choke inputs and the trim's accumulated
wear). The variant's changes are applied to the twin, the steady operating
point is solved, and choke wear is integrated over the horizon at that
operating point (quasi-steady). The live session is never touched.

Why steady: after an operating change the dynamic model approaches steady
state over hours of simulated time (the reservoir transient), which would
cost minutes of computing per case and still drift. Comparing settled
steady operating points is the standard way to compare operating options;
the transient itself is studied in the live session.

Trim-material variants represent a NEW trim of that material, so they start
from zero wear; every other case starts from the current trim's wear.
"""

from __future__ import annotations

import copy
from contextlib import contextmanager

from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Annotated

from app.simulation.components.elements import CommandRejected
from app.simulation.engine import SimulationEngine
from app.simulation.sand import erosion as er

MAX_VARIANTS = 6
WEAR_STATE = ("dd_base", "plug_base", "body_loss", "outlet_loss", "service_s", "cum", "log", "cv_track", "_last_log",
              "_dd_at_replacement", "_plug_at_replacement", "replacement_days", "det")


class Variant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: Annotated[str, Field(min_length=1, max_length=60)]
    choke_pct: Annotated[float, Field(ge=0, le=100)] | None = None
    reservoir_pressure_bara: Annotated[float, Field(gt=1, le=2000)] | None = None
    downstream_pressure_bara: Annotated[float, Field(gt=1, le=1000)] | None = None
    water_cut: Annotated[float, Field(ge=0, le=0.99)] | None = None
    gor_sm3_sm3: Annotated[float, Field(gt=0, le=5000)] | None = None
    #: Produced sand rate imposed as a measured value [kg/d].
    sand_rate_kg_d: Annotated[float, Field(ge=0, le=1e5)] | None = None
    #: Median grain size [um]; D10 and D90 are scaled by the same ratio (same spread).
    d50_um: Annotated[float, Field(gt=1, le=5000)] | None = None
    #: Trim material key (a NEW trim of this material: starts from zero wear).
    trim_material: str | None = None

    @model_validator(mode="after")
    def _known_material(self):
        if self.trim_material is not None and er.material(self.trim_material, []) is None:
            raise ValueError(f"unknown trim material '{self.trim_material}' (library: {', '.join(er.MATERIALS)})")
        return self

    def changes(self) -> list[str]:
        out = []
        for k, unit in (("choke_pct", "%"), ("reservoir_pressure_bara", "bara"), ("downstream_pressure_bara", "bara"),
                        ("water_cut", ""), ("gor_sm3_sm3", "Sm3/Sm3"), ("sand_rate_kg_d", "kg/d"), ("d50_um", "um"), ("trim_material", "")):
            v = getattr(self, k)
            if v is not None:
                out.append(f"{k} = {v:g} {unit}".strip() if isinstance(v, (int, float)) else f"{k} = {v}")
        return out


class StudyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    variants: Annotated[list[Variant], Field(min_length=1, max_length=MAX_VARIANTS)]
    horizon_days: Annotated[float, Field(ge=0, le=3650)] = 365.0
    base_label: Annotated[str, Field(min_length=1, max_length=60)] = "Current operation"


# --------------------------------------------------------------- the twin
@contextmanager
def _one_solve(tw: SimulationEngine):
    """Apply several changes with ONE steady solve at the end (each setter
    would otherwise re-solve the multiphase steady state)."""
    tw.recompute = lambda: None  # type: ignore[method-assign]
    try:
        yield
    finally:
        del tw.recompute  # back to the class method
        tw.recompute()
        if tw.sand is not None:
            tw.sand._update_rates_only()


def steady_twin(src: SimulationEngine) -> SimulationEngine:
    """A steady-model engine carrying the source session's current state."""
    sc = src.scenario
    scen = sc.model_copy(update={"dynamics": sc.dynamics.model_copy(update={"mode": "steady"}), "fluid_model": src.fluid_model})
    tw = SimulationEngine(scen, src.settings)
    with _one_solve(tw):
        _carry_state(src, tw)
    return tw


def _carry_state(src: SimulationEngine, tw: SimulationEngine) -> None:
    tw.set_boundary(reservoir_pressure_pa=src.ipr.p_res, productivity_index_si=src.ipr.j, reservoir_temperature_k=src.ipr.t_res,
                    downstream_pressure_pa=src.p_boundary)
    if src.bo is not None and tw.bo is not None:
        p = src.bo.params
        tw.set_black_oil(producing_gor_sm3_sm3=src.mp_gor, water_cut=src.mp_wc, oil_api=p.api, gas_specific_gravity=p.gas_sg,
                         water_salinity_wt_pct=p.water_salinity_wt_pct, correlation=src.mp_correlation)
    for tag, el in src.restrictions.items():
        if tag in tw.restrictions:
            a = tw.restrictions[tag].actuator
            a.position_pct = a.commanded_pct = el.actuator.position_pct
    si = src.sand_inputs
    if si is not None:
        tw.set_sand_inputs(si.model_copy(deep=True), "copied from the session", origin=src.sand_inputs_origin)
        _copy_wear(src, tw)


def _copy_wear(src: SimulationEngine, tw: SimulationEngine) -> None:
    if src.sand is None or tw.sand is None:
        return
    for k in WEAR_STATE:
        if hasattr(src.sand, k):
            setattr(tw.sand, k, copy.deepcopy(getattr(src.sand, k)))


def _apply(tw: SimulationEngine, v: Variant) -> str:
    """Apply a variant (one steady solve); returns what the wear starts from."""
    with _one_solve(tw):
        return _apply_changes(tw, v)


def _apply_changes(tw: SimulationEngine, v: Variant) -> str:
    start = "current trim wear"
    if v.reservoir_pressure_bara is not None or v.downstream_pressure_bara is not None:
        tw.set_boundary(reservoir_pressure_pa=None if v.reservoir_pressure_bara is None else v.reservoir_pressure_bara * 1e5,
                        downstream_pressure_pa=None if v.downstream_pressure_bara is None else v.downstream_pressure_bara * 1e5)
    if (v.water_cut is not None or v.gor_sm3_sm3 is not None) and tw.bo is not None:
        tw.set_black_oil(producing_gor_sm3_sm3=v.gor_sm3_sm3, water_cut=v.water_cut)
    if v.choke_pct is not None:
        ch = tw.restrictions.get("CHK-101") or next((el for el in tw.restrictions.values() if el.kind == "choke"), None)
        if ch is None:
            raise CommandRejected("no production choke in this scenario")
        target = ch.validate_command("set_position", v.choke_pct)  # actuator step quantisation
        ch.actuator.position_pct = ch.actuator.commanded_pct = target
    if tw.sand is not None and (v.sand_rate_kg_d is not None or v.d50_um is not None or v.trim_material is not None):
        inp = tw.sand_inputs.model_copy(deep=True)
        if v.sand_rate_kg_d is not None:
            inp.sand.mode = "measured"
            inp.sand.measured_value, inp.sand.measured_unit = v.sand_rate_kg_d, "kg_d"
            inp.sand.measurements = []  # the imposed value, not the history
        if v.d50_um is not None and inp.sand.d50_um:
            r = v.d50_um / inp.sand.d50_um
            inp.sand.d50_um = v.d50_um
            inp.sand.d10_um = inp.sand.d10_um * r if inp.sand.d10_um else None
            inp.sand.d90_um = inp.sand.d90_um * r if inp.sand.d90_um else None
        if v.trim_material is not None:
            inp.choke.trim_material = v.trim_material
        wear = None if v.trim_material is not None else {k: copy.deepcopy(getattr(tw.sand, k)) for k in WEAR_STATE if hasattr(tw.sand, k)}
        tw.set_sand_inputs(inp, f"variant {v.label}", origin=tw.sand_inputs_origin)
        if wear is not None:
            for k, val in wear.items():
                setattr(tw.sand, k, val)
        else:
            start = "new trim (zero wear)"
    return start


def metrics(tw: SimulationEngine) -> dict:
    s = tw.snapshot(False)
    mp = s.get("multiphase") or {}
    sc = s.get("sand_choke") or {}
    sand = sc.get("sand") or {}
    on = sand.get("onset") or {}
    cav = sc.get("cavitation") or {}
    ev = sc.get("erosional_velocity") or {}
    crit = {c["key"]: c for c in sc.get("criteria") or []}
    first = crit.get(sc.get("first_limit") or "") or {}
    gov = crit.get(sc.get("governing") or "") or {}
    hole = crit.get("hole") or {}
    ra = mp.get("rates_arrival") or {}
    ch = next((el for el in tw.restrictions.values() if el.kind == "choke"), None)
    ratios = [r["ratio"] for r in ev.get("locations") or [] if r.get("available")]
    return {
        "choke_pct": ch.actuator.position_pct if ch else None,
        "reservoir_pressure_bara": tw.ipr.p_res / 1e5,
        "water_cut": tw.mp_wc if tw.bo is not None else None,
        "gor_sm3_sm3": tw.mp_gor if tw.bo is not None else None,
        "oil_sm3_d": ra.get("oil_sm3_d"), "gas_sm3_d": ra.get("gas_sm3_d"), "water_sm3_d": ra.get("water_sm3_d"),
        "choke_p1_bara": cav.get("p1_bara"), "choke_p2_bara": cav.get("p2_bara"), "choke_dp_bar": cav.get("dp_bar"),
        "drawdown_bar": on.get("drawdown_bar"), "critical_drawdown_bar": on.get("critical_drawdown_bar"), "risk_index": on.get("risk_index"),
        "sand_produced_kg_d": sand.get("produced_kg_d"), "sand_at_choke_kg_d": sand.get("at_choke_kg_d"),
        "jet_velocity_m_s": (sc.get("velocities") or {}).get("u_jet"),
        "hole_rate_mm_y": hole.get("rate_per_year"),
        "first_limit": first.get("label"), "life_p10_days": (first.get("life_days") or {}).get("p10"),
        "life_p50_days": (first.get("life_days") or {}).get("p50"), "life_p90_days": (first.get("life_days") or {}).get("p90"),
        "governing": gov.get("label"), "governing_consumed": gov.get("consumed"),
        "service_days": sc.get("service_days"), "health": (sc.get("health") or {}).get("category"),
        "cavitation_risk": cav.get("risk"), "cavitation_regime": cav.get("regime"),
        "api14e_max_ratio": max(ratios) if ratios else None,
        "confidence": (sc.get("confidence") or {}).get("category"),
    }


def run_study(src: SimulationEngine, req: StudyRequest):
    """Generator (background job): yields (progress, message); returns the result."""
    cases = [("base", req.base_label, None)] + [(f"v{i + 1}", v.label, v) for i, v in enumerate(req.variants)]
    n = len(cases)
    out = []
    yield 0.0, "building the steady twin of the session"
    base = steady_twin(src)
    for i, (cid, label, v) in enumerate(cases):
        yield i / n, f"{label}: solving the steady operating point"
        tw = copy.deepcopy(base)
        start = "current trim wear" if v is None else _apply(tw, v)
        m0 = metrics(tw)  # at the start of the horizon
        if req.horizon_days > 0 and tw.sand is not None:
            for frac, _msg in tw.sand_fast_forward_steps(req.horizon_days):
                yield (i + 0.2 + 0.8 * frac) / n, f"{label}: wear over {req.horizon_days:g} days"
        m1 = metrics(tw)
        out.append({"id": cid, "label": label, "changes": [] if v is None else v.changes(), "wear_start": start,
                    "now": m0, "after_horizon": m1})
    return {"message": f"compared {n} cases over {req.horizon_days:g} days", "horizon_days": req.horizon_days,
            "scenario_id": src.scenario.id, "sim_time_s": src.time_s, "cases": out,
            "method": ("Each case: steady twin of the session (same models: black-oil PVT, multiphase flow, sanding, DNV-RP-O501 "
                       "erosion, cavitation and API 14E screening), the variant applied, the steady operating point solved, wear "
                       "integrated quasi-steadily over the horizon. Trim-material variants start from a new trim."),
            "limitations": ["Steady operating points: transients between settings are not included (study them in the live session).",
                            "Operating conditions are held constant over the horizon (no depletion, water-cut or sand-rate trends).",
                            "Chemical-injection variants are not offered: injection is modelled in the dynamic model only.",
                            "The same model limitations as the live session apply (see each model document)."]}
