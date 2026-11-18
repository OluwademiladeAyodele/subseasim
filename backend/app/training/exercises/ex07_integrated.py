"""Exercise 7 - Integrated production, sand and choke health.

The 14-stage integrated scenario of the engineering specification (§7.1):

 1 load a three-phase well            8 change the reservoir drawdown
 2 configure reservoir / fluid        9 sand production follows the sanding model
 3 start production                  10 follow the sand transport
 4 open the production valves        11 monitor choke erosion
 5 adjust the choke                  12 review cumulative wear
 6 oil / gas / water on the MPFM     13 receive the inspection recommendation
 7 sand reaches the choke             14 review uncertainty and the maintenance explanation

Every task is judged from the SIMULATION STATE, predictions and data
questions are resolved from what this run actually did, and every review
text is generated from the recorded observations. Nothing numerical is
pre-written.
"""

from __future__ import annotations

from typing import Any

from app.core import units as u
from app.simulation.components.elements import ValveElement
from app.simulation.engine import SimulationEngine
from app.training.framework import ExerciseDefinition, Obs, Option, Step

CHOKE = "CHK-101"
PWV = "PWV-101"
WC_TARGET = 0.35
C1, C2 = 40.0, 65.0  # choke openings [%]
SETTLED_PA_S = 300.0  # fast pressure transients settled
INSPECT_CATS = ("Inspection recommended", "Changeout assessment required", "Critical condition")


def _tag(e: SimulationEngine, tag: str) -> str:
    a = e.scenario.tag_aliases.get(tag)
    return f"{a.tag} ({tag})" if a and a.tag != tag else tag


def _step_tol(e: SimulationEngine) -> float:
    ch = e.restrictions[CHOKE]
    return (100.0 / ch.steps if getattr(ch, "steps", None) else 0.1) / 2 + 1e-6


# ------------------------------------------------------------- capture
def capture(e: SimulationEngine) -> dict[str, Any]:
    snap = e.snapshot(False)
    mp = snap.get("multiphase") or {}
    m = snap.get("mpfm") or {}
    sc = snap.get("sand_choke") or {}
    sand = sc.get("sand") or {}
    on = sand.get("onset") or {}
    crit = {c["key"]: c for c in sc.get("criteria", [])}
    first = crit.get(sc.get("first_limit") or "", {})
    vel = sc.get("velocities") or {}
    return {
        "sim_time_s": e.time_s,
        "choke_pct": e.restrictions[CHOKE].actuator.position_pct,
        "water_cut": e.mp_wc if e.bo is not None else None,
        "rates": mp.get("rates_arrival"),
        "rates_sandface": mp.get("rates_reservoir"),
        "mpfm_quality": m.get("quality"),
        "mpfm_measured": m.get("measured"),
        "mpfm_true": m.get("true"),
        "mpfm_uncertainty": m.get("uncertainty_pct"),
        "risk_index": on.get("risk_index"),
        "drawdown_bar": on.get("drawdown_bar"),
        "critical_drawdown_bar": on.get("critical_drawdown_bar"),
        "formation_kg_d": sand.get("formation_kg_d"),
        "produced_kg_d": sand.get("produced_kg_d"),
        "at_choke_kg_d": sand.get("at_choke_kg_d"),
        "screen_passing": (sand.get("screen") or {}).get("passing_fraction"),
        "jet_velocity_m_s": vel.get("u_jet"),
        "critical_flow": vel.get("critical_flow"),
        "service_days": sc.get("service_days"),
        "health": (sc.get("health") or {}).get("category"),
        "confidence": (sc.get("confidence") or {}).get("category"),
        "recommendation": sc.get("recommendation"),
        "first_limit": sc.get("first_limit"),
        "first_label": first.get("label"),
        "first_life": first.get("life_days"),
        "first_consumed": first.get("consumed"),
        "criteria": {k: {"label": c["label"], "used": c["used"], "allowance": c["allowance"], "unit": c["unit"],
                         "rate_per_year": c["rate_per_year"], "consumed": c["consumed"], "life_days": c["life_days"]}
                     for k, c in crit.items()},
        "rows": (sc.get("erosion") or {}).get("rows"),
        "uncertainty": sc.get("uncertainty_components"),
        "cv_tracking": sc.get("cv_tracking"),
        "cum_choke_kg": (sc.get("cumulative") or {}).get("choke_kg"),
    }


# ---------------------------------------------------------- conditions
def _running(e):
    return e.status == "running"


def _iso_open(e):
    return all(r.actuator.position_pct >= 100.0 for r in e.restrictions.values()
               if isinstance(r, ValveElement) and r.tag in ("SCSSV-101", "PMV-101", PWV))


def _flowing(e):
    return e.dyn is not None and e.dyn.mp is not None and e.hyd is not None and _iso_open(e) and \
        float(e.dyn.net.Q[e.dyn.layout.element_link[e.topology.path[0].id]]) > 1e-4


def _settled(e):
    return e.dyn is not None and e.dyn.max_rate_pa_s < SETTLED_PA_S


def _choke_at(target: float):
    def cond(e):
        a = e.restrictions[CHOKE].actuator
        tol = _step_tol(e)
        return (_running(e) and _flowing(e) and not a.is_moving and abs(a.commanded_pct - target) <= tol
                and abs(a.position_pct - target) <= tol and _settled(e))
    return cond


def _choke_hint(target: float):
    def hint(e):
        a = e.restrictions[CHOKE].actuator
        if not _running(e):
            return "Start or resume the simulation."
        if abs(a.commanded_pct - target) > _step_tol(e):
            return f"Select {_tag(e, CHOKE)} on the Christmas tree page and set it to {target:g} % (the stepping actuator lands on the nearest step)."
        if a.is_moving:
            return f"{_tag(e, CHOKE)} travelling {a.position_pct:.1f} -> {a.commanded_pct:.1f} %."
        return f"Waiting for the fast pressure transient to settle (max dP/dt {e.dyn.max_rate_pa_s / 1e5 * 60:.2f} bar/min)."
    return hint


def _baseline(e):
    m = e.mpfm
    return _running(e) and _flowing(e) and _settled(e) and m is not None and m.quality == "GOOD" and m.reading is not None


def _baseline_hint(e):
    if not _flowing(e):
        return f"Open {_tag(e, PWV)} (SCSSV and PMV are already open) - production starts when the wing valve is open."
    if e.mpfm is None or e.mpfm.quality != "GOOD":
        return f"Waiting for MPFM-201 to report GOOD (now {e.mpfm.quality if e.mpfm else 'n/a'}) - flow must reach the manifold."
    return "Waiting for the start-up pressure transient to settle."


def _transported(e):
    s = e.sand
    if s is None or not s.rates or not _running(e):
        return False
    src = s.last_source
    prod = (src["produced_kg_s"] or 0.0) if src else 0.0
    return prod > 0 and abs(s.rates.get("m_sand_choke", 0.0) - prod) <= 0.05 * prod


def _transport_hint(e):
    s = e.sand
    if s is None or not s.rates:
        return "Waiting for the sand model."
    src = s.last_source
    prod = (src["produced_kg_s"] or 0.0) * 86400
    return f"Sand at the choke {s.rates.get('m_sand_choke', 0) * 86400:.1f} kg/d of {prod:.1f} kg/d produced - the new sand is still on its way up the well."


def _ff_done(min_days: float):
    def cond(e):
        s = e.sand
        return s is not None and s.service_s / 86400 >= min_days
    return cond


def _inspect(e):
    s = e.sand
    return s is not None and s.snapshot()["health"]["category"] in INSPECT_CATS


def _inspect_hint(e):
    s = e.sand
    if s is None:
        return "Sand model unavailable."
    snap = s.snapshot()
    gov = next((c for c in snap["criteria"] if c["key"] == snap.get("governing")), None)
    used = f"{gov['label']} {gov['consumed'] * 100:.0f} % consumed" if gov and gov.get("consumed") is not None else "no wear yet"
    return f"Health: {snap['health']['category']} ({used}). Fast-forward on the Choke health page until an inspection is recommended."


# -------------------------------------------------------- resolvers
def _mpfm_within(obs: Obs) -> str | None:
    b = obs.get("base")
    if not b or not b["mpfm_measured"] or not b["mpfm_true"] or not b["mpfm_uncertainty"]:
        return None
    m, t, uo = b["mpfm_measured"]["oil_sm3_d"], b["mpfm_true"]["oil_sm3_d"], b["mpfm_uncertainty"]["oil_sm3_d"]
    return "a" if abs(m - t) / t * 100 <= uo else "b"


def _mpfm_explain(obs: Obs) -> str:
    b = obs["base"]
    m, t, uo = b["mpfm_measured"], b["mpfm_true"], b["mpfm_uncertainty"]
    dev = (m["oil_sm3_d"] - t["oil_sm3_d"]) / t["oil_sm3_d"] * 100
    return (f"MPFM-201 measured {m['oil_sm3_d']:.0f} Sm3/d oil, {m['gas_sm3_d'] / 1000:.1f} kSm3/d gas and {m['water_sm3_d']:.0f} Sm3/d "
            f"water (WC {m['water_cut'] * 100:.1f} %); the simulated true oil rate was {t['oil_sm3_d']:.0f} Sm3/d, a difference of "
            f"{dev:+.1f} % against a stated uncertainty of +/- {uo['oil_sm3_d']:.1f} % (k=2). A meter reading is an estimate with "
            "an uncertainty, not the process value.")


def _risk_pred(obs: Obs) -> str | None:
    b, c = obs.get("base"), obs.get("c1")
    if not b or not c or b["risk_index"] is None or c["risk_index"] is None:
        return None
    if c["risk_index"] > 1.0 >= b["risk_index"]:
        return "a"
    if c["risk_index"] > b["risk_index"]:
        return "b"
    return "c"


def _risk_explain(obs: Obs) -> str:
    b, c = obs["base"], obs["c1"]
    return (f"Opening the choke from {b['choke_pct']:.0f} to {c['choke_pct']:.0f} % raised the production rate, so the drawdown "
            f"went from {b['drawdown_bar']:.1f} to {c['drawdown_bar']:.1f} bar against a critical drawdown of "
            f"{c['critical_drawdown_bar']:.1f} bar: risk index {b['risk_index']:.2f} -> {c['risk_index']:.2f}. Above 1 the "
            "perforation-tunnel walls fail and sand is produced.")


def _sand_pred(obs: Obs) -> str | None:
    c1, c2 = obs.get("c1"), obs.get("c2")
    if not c1 or not c2 or c1["formation_kg_d"] is None or c2["formation_kg_d"] is None:
        return None
    r_dd = c2["drawdown_bar"] / c1["drawdown_bar"]
    r_s = c2["formation_kg_d"] / c1["formation_kg_d"] if c1["formation_kg_d"] > 0 else float("inf")
    if r_s > r_dd * 1.05:
        return "a"
    if r_s >= r_dd * 0.95:
        return "b"
    return "c"


def _sand_explain(obs: Obs) -> str:
    c1, c2 = obs["c1"], obs["c2"]
    return (f"Drawdown rose x{c2['drawdown_bar'] / c1['drawdown_bar']:.2f} ({c1['drawdown_bar']:.0f} -> {c2['drawdown_bar']:.0f} bar) "
            f"but formation sand rose x{c2['formation_kg_d'] / c1['formation_kg_d']:.2f} ({c1['formation_kg_d']:.1f} -> "
            f"{c2['formation_kg_d']:.1f} kg/d): the sanding model scales with the EXCESS over the critical drawdown, "
            "(r - 1)^n, and with the liquid rate - so sand grows much faster than drawdown once onset is passed.")


FIRST_LIMIT_OPTIONS = {"hole": "a", "cv": "b", "plug": "c", "body": "d", "outlet": "d"}


def _first_limit(obs: Obs) -> str | None:
    f = obs.get("ff1", {}).get("first_limit")
    return FIRST_LIMIT_OPTIONS.get(f) if f else None


def _first_limit_explain(obs: Obs) -> str:
    f = obs["ff1"]
    life = f["first_life"]
    life_txt = f" P50 remaining life {life['p50']:.0f} days (P10 {life['p10']:.0f} - P90 {life['p90']:.0f})." if life else ""
    return (f"In this run the first criterion to reach its allowance is '{f['first_label']}' "
            f"({(f['first_consumed'] or 0) * 100:.0f} % consumed after {f['service_days']:.0f} service days).{life_txt} "
            "Cage-hole growth raises the open flow area, so the Cv increase at the normal opening is often the first limit.")


# ---------------------------------------------------------------- reviews
def _rates_table(obs: Obs, keys: list[tuple[str, str]]) -> dict:
    cols = ["Quantity"] + [lbl for _, lbl in keys]

    def row(label, f):
        return [label] + [f(obs[k]) for k, _ in keys]

    def r(x, d=1):
        return None if x is None else round(x, d)

    return {"columns": cols, "rows": [
        row("Choke opening [%]", lambda o: r(o["choke_pct"])),
        row("Oil at manifold [Sm3/d]", lambda o: r(o["rates"]["oil_sm3_d"], 0) if o["rates"] else None),
        row("Gas at manifold [kSm3/d]", lambda o: r(o["rates"]["gas_sm3_d"] / 1000) if o["rates"] else None),
        row("Water at manifold [Sm3/d]", lambda o: r(o["rates"]["water_sm3_d"], 0) if o["rates"] else None),
        row("Drawdown / critical [bar]", lambda o: f"{o['drawdown_bar']:.1f} / {o['critical_drawdown_bar']:.1f}" if o["drawdown_bar"] is not None else None),
        row("Sanding risk index", lambda o: r(o["risk_index"], 2)),
        row("Formation sand [kg/d]", lambda o: r(o["formation_kg_d"], 2)),
        row("Sand through screens [kg/d]", lambda o: r(o["produced_kg_d"], 2)),
        row("Sand at the choke [kg/d]", lambda o: r(o["at_choke_kg_d"], 2)),
        row("Choke jet velocity [m/s]", lambda o: r(o["jet_velocity_m_s"])),
    ]}


def _review_choke(obs: Obs, preds: dict) -> dict:
    b, c = obs["base"], obs["c1"]
    p = preds.get("p_risk")
    v = f"Your prediction: '{p['choice_text']}'. Result: '{p['correct_text']}'. " if p and p["correct"] is not None else ""
    text = (v + _risk_explain(obs) + f"\nOil at the manifold went from {b['rates']['oil_sm3_d']:.0f} to {c['rates']['oil_sm3_d']:.0f} "
            "Sm3/d; gas and water follow the same composition (GOR and water cut are set at the reservoir), so all three phases "
            "rise together. The choke jet velocity sets how hard sand will strike the trim.")
    return {"text": text, "table": _rates_table(obs, [("base", f"{b['choke_pct']:.0f} %"), ("c1", f"{c['choke_pct']:.0f} %")])}


def _review_sand(obs: Obs, preds: dict) -> dict:
    c1, c2 = obs["c1"], obs["c2"]
    p = preds.get("p_sand")
    v = f"Your prediction: '{p['choice_text']}'. Result: '{p['correct_text']}'. " if p and p["correct"] is not None else ""
    text = (v + _sand_explain(obs) + f"\nThe standalone screens pass {(c2['screen_passing'] or 0) * 100:.0f} % of the failed "
            "formation sand (the grains finer than the aperture / bridging factor); the rest stays behind the screens. "
            "The predictive rate coefficient is an ILLUSTRATIVE value here - in the field it must be calibrated with sand-trap "
            "or well-test sand sampling data.")
    return {"text": text, "table": _rates_table(obs, [("c1", f"{c1['choke_pct']:.0f} %"), ("c2", f"{c2['choke_pct']:.0f} %")])}


def _review_transport(obs: Obs, preds: dict) -> dict:
    c2, t = obs["c2"], obs["transport"]
    dt = (t["sim_time_s"] - c2["sim_time_s"]) / 60
    text = (f"After the drawdown change it took about {dt:.0f} minutes of simulated time until the sand arriving at the choke matched the "
            f"sand leaving the screens ({t['at_choke_kg_d']:.1f} of {t['produced_kg_d']:.1f} kg/d). Sand is carried by the production flow - "
            "it needs the fluid transit time up ~2.5 km of tubing, and it stops when the flow stops.")
    return {"text": text}


def _review_erosion(obs: Obs, preds: dict) -> dict:
    t = obs["transport"]
    rows = t.get("rows") or []
    eroding = [r for r in rows if (r.get("rate_mm_y") or 0) > 0]
    hole = (t.get("criteria") or {}).get("hole") or {}
    life = hole.get("life_days")
    text = (f"Sand reaches the trim at the jet velocity of {t['jet_velocity_m_s']:.0f} m/s"
            f"{' (critical flow)' if t.get('critical_flow') else ''}. The erosion rate scales with velocity^n and with the sand mass "
            f"rate. At this opening {len(eroding)} of {len(rows)} cage-hole rows are open and eroding; the fastest grows "
            f"{max((r['rate_mm_y'] or 0) for r in rows) if rows else 0:.3f} mm/year. "
            + (f"Cage-hole remaining life at today's conditions: P50 {life['p50']:.0f} days (P10 {life['p10']:.0f} - P90 {life['p90']:.0f}). "
               if life else "")
            + "Tungsten-carbide trims erode slowly; the same sand on a steel trim would wear it out many times faster.")
    table = {"columns": ["Hole row (axial mm)", "Diameter mm", "Count", "Growth rate mm/yr"],
             "rows": [[r["axial_position_mm"], r["diameter_mm"], r["count"], None if r["rate_mm_y"] is None else round(r["rate_mm_y"], 4)] for r in rows]}
    return {"text": text, "table": table}


def _review_reco(obs: Obs, preds: dict) -> dict:
    i = obs["insp"]
    rec = i["recommendation"] or {}
    text = (f"After {i['service_days']:.0f} service days the choke health became '{i['health']}'.\n\n{rec.get('text', '')}\n\n"
            "Suggested actions: " + "; ".join(rec.get("actions", [])) + ".\n\n" + rec.get("disclaimer", ""))
    crit = i.get("criteria") or {}
    table = {"columns": ["Criterion", "Used", "Allowance", "Consumed %", "Rate / yr"],
             "rows": [[c["label"], round(c["used"], 3), c["allowance"], None if c["consumed"] is None else round(c["consumed"] * 100, 1),
                       round(c["rate_per_year"], 3)] for c in crit.values()]}
    return {"text": text, "table": table}


# -------------------------------------------------------------- definition
EXERCISE = ExerciseDefinition(
    id="ex07_integrated",
    number=7,
    title="Exercise 7 - Integrated production, sand and choke health",
    scenario_id="training_integrated",
    objectives=[
        "Bring a three-phase well on line and read oil, gas and water rates on the MPFM at standard conditions.",
        "Relate choke opening and drawdown to the sanding risk (critical drawdown) and the sand rate.",
        "Follow sand from the formation through the screens to the choke.",
        "Interpret choke erosion, cumulative wear, remaining life and the uncertainty of the prediction.",
        "Explain a maintenance recommendation and what would improve its confidence.",
    ],
    initial_configuration=[
        "XT workstation three-phase well (GOR 120 Sm3/Sm3, 35 API) - SHUT IN: production wing valve closed.",
        "Choke at 30 %; SCSSV and PMV open; MPFM-201 on the manifold.",
        "Complete ILLUSTRATIVE sand / choke inputs (geomechanics, standalone screens, plug & cage tungsten-carbide trim).",
    ],
    instructions=[
        "Work on the Christmas tree, Multiphase flow, MPFM monitoring and Choke health pages.",
        "Use the speed control (60x) when waiting for flow, sand transport or pressure transients.",
        "Make each prediction BEFORE acting; it is resolved from what your simulation actually does.",
    ],
    expected_observations=[
        "All three phase rates appear at the MPFM once flow reaches the manifold, with a stated uncertainty.",
        "Sand starts when the drawdown exceeds the critical drawdown and grows faster than the drawdown.",
        "Sand reaches the choke only after the fluid transit time.",
        "Wear accumulates with sand and time; an inspection is recommended when the configured allowance fraction is reached.",
    ],
    capture=capture,
    steps=[
        Step("intro", "info", "1 - A three-phase production well",
             "You are operating a subsea well producing oil, gas and water. The well is SHUT IN: the production wing valve is "
             "closed. You will bring it on line, read the multiphase flow meter, take it past the sanding limit and follow the "
             "consequences for the production choke - all in one simulation."),
        Step("t_start", "task", "Start the simulation",
             "Press START in the top bar.",
             condition=lambda e: _running(e) and e.fluid_model == "black_oil",
             condition_hint=lambda e: "Press START (or RESUME)." if e.fluid_model == "black_oil" else "Select the three-phase fluid model."),
        Step("t_fluid", "task", "2 - Configure the reservoir fluid",
             "Recent samples show more water: set the WATER CUT to 35 % on the Conditions (or Multiphase flow) page and apply. "
             "Note the bubble point, GOR and oil gravity while you are there.",
             condition=lambda e: e.bo is not None and abs(e.mp_wc - WC_TARGET) < 0.005,
             condition_hint=lambda e: f"Water cut is {e.mp_wc * 100:.1f} % - set it to 35 %." if e.bo is not None else "Three-phase model required."),
        Step("t_open", "task", "3 & 4 - Start production: open the production valves",
             "Open the production wing valve (PWV-101). SCSSV-101 and PMV-101 are already open. The baseline is recorded when the "
             "flow has reached the manifold and MPFM-201 reports GOOD.",
             condition=_baseline, condition_hint=_baseline_hint, record_as="base"),
        Step("q_mpfm", "question", "6 - Read the MPFM",
             "Open MPFM monitoring. Is the measured OIL rate within the meter's stated uncertainty of the simulated true rate?",
             options=[Option("a", "Yes - the difference is inside the stated uncertainty"),
                      Option("b", "No - the difference exceeds the stated uncertainty")],
             correct=_mpfm_within, explanation=_mpfm_explain),
        Step("p_risk", "prediction", "Predict: open the choke to 40 %",
             "Opening the choke increases the rate and the drawdown. What happens to the sanding risk index (drawdown / critical drawdown)?",
             options=[Option("a", "It rises above 1 - sand production starts"), Option("b", "It rises but stays at or below 1"),
                      Option("c", "It falls")],
             correct=_risk_pred, explanation=_risk_explain),
        Step("t_c1", "task", "5 - Adjust the choke to 40 %",
             "Set CHK-101 to 40 % on the Christmas tree page and let the pressures settle.",
             condition=_choke_at(C1), condition_hint=_choke_hint(C1), record_as="c1"),
        Step("r_choke", "review", "Review: production and sanding risk", review=_review_choke),
        Step("p_sand", "prediction", "Predict: increase the drawdown",
             f"You will open the choke to {C2:g} %, increasing the drawdown. Compared with the drawdown increase, the formation sand rate will:",
             options=[Option("a", "Increase MORE than proportionally"), Option("b", "Increase in proportion"),
                      Option("c", "Increase LESS than proportionally (or not at all)")],
             correct=_sand_pred, explanation=_sand_explain),
        Step("t_c2", "task", f"8 - Change the drawdown: choke to {C2:g} %",
             f"Set CHK-101 to {C2:g} % and let the pressures settle.",
             condition=_choke_at(C2), condition_hint=_choke_hint(C2), record_as="c2"),
        Step("r_sand", "review", "9 - Review: sand production follows the sanding model", review=_review_sand),
        Step("t_transport", "task", "7 & 10 - Follow the sand transport",
             "The extra sand is now travelling up the tubing. The task completes when the sand arriving at the choke matches the "
             "sand passing the screens (Sand source panel on the Choke health page).",
             condition=_transported, condition_hint=_transport_hint, record_as="transport"),
        Step("r_transport", "review", "Review: sand transport", review=_review_transport),
        Step("r_erosion", "review", "11 - Monitor the choke erosion", review=_review_erosion),
        Step("t_ff", "task", "12 - Review cumulative wear",
             "On Choke health, fast-forward the operation by at least 365 days (quasi-steady at today's conditions) and look at the "
             "wear history against service days, sand mass and liquid produced.",
             condition=lambda e: e.sand is not None and e.sand.service_s / 86400 >= 365,
             condition_hint=lambda e: f"Trim service time {e.sand.service_s / 86400:.0f} days - fast-forward to at least 365." if e.sand else "",
             record_as="ff1"),
        Step("q_first", "question", "Which limit comes first?",
             "In your run, which wear criterion reaches its allowance first (see 'first limit' on Choke health)?",
             options=[Option("a", "Cage-hole enlargement"), Option("b", "Cv increase at the reference opening"),
                      Option("c", "Plug / seat edge loss"), Option("d", "Body or outlet wall loss")],
             correct=_first_limit, explanation=_first_limit_explain),
        Step("t_inspect", "task", "13 - Receive the inspection recommendation",
             "Keep fast-forwarding until the choke health reaches 'Inspection recommended' (the configured fraction of the allowance).",
             condition=_inspect, condition_hint=_inspect_hint, record_as="insp"),
        Step("r_reco", "review", "Review: the maintenance recommendation", review=_review_reco),
        Step("q_range", "question", "14 - Why a range and not a date?",
             "The Choke health page gives remaining life as P10 - P90 instead of a date. Why?",
             options=[
                 Option("a", "The erosion constant for this trim, the sand rate and the particle velocity are uncertain; until calibrated "
                             "by inspections the model is a screening estimate"),
                 Option("b", "The simulator cannot compute a single number"),
                 Option("c", "Choke erosion is random and cannot be predicted at all"),
             ],
             correct="a",
             explanation="Each input to the erosion estimate carries uncertainty (shown on the Confidence panel). The range narrows "
                         "when inspections calibrate the trim erosion factor and when the sand rate is measured instead of predicted."),
        Step("q_improve", "question", "What would most improve confidence?",
             "Which action would most improve the confidence of this choke-life prediction?",
             options=[
                 Option("a", "Record inspection measurements (hole sizes / Cv change) and use a measured sand rate"),
                 Option("b", "Run the simulator at a higher speed"),
                 Option("c", "Open the choke fully to make the wear visible faster"),
             ],
             correct="a",
             explanation="Inspection data calibrate the generic DNV-type erosion model to YOUR trim (the confidence category rises to "
                         "'calibrated'); a measured sand rate removes the largest uncertainty of the predictive sanding model. "
                         "A rising measured Cv at constant step is independent evidence of trim wear."),
        Step("summary", "summary", "Performance summary"),
    ],
)

__all__ = ["EXERCISE", "u"]
