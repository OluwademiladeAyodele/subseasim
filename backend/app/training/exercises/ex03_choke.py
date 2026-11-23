"""Exercise 3 - Choke operation.

All explanatory text is generated from the observations recorded from THIS
simulation run; nothing is pre-written as a fixed numerical result.
"""

from __future__ import annotations

from typing import Any

from app.core import units as u
from app.simulation.components.elements import ChokeElement, PipeElement, ValveElement
from app.simulation.engine import SimulationEngine
from app.training.framework import ExerciseDefinition, Obs, Option, Step

CHOKE_TAG = "CHK-101"
REQUIRED_TAGS = ("CHK-101", "FT-101", "PT-001", "PT-101", "PT-102", "PT-103", "PDT-101", "PT-201", "TT-102", "TT-103")
#: Position tolerance for "choke has reached the target" [% of travel].
POSITION_TOL_PCT = 0.05

BUDGET_LABELS = {
    "drawdown": "Reservoir drawdown (P_res - P_wf)",
    "tubing_hydrostatic": "Tubing hydrostatic head",
    "tubing_friction": "Tubing friction",
    "isolation_valves": "Isolation valves (SCSSV, PMV, PWV)",
    "choke": "Production choke",
    "flowline_hydrostatic": "Flowline elevation",
    "flowline_friction": "Flowline friction",
}


def _val(engine: SimulationEngine, tag: str) -> float | None:
    return engine.readings[tag].value


def capture(engine: SimulationEngine) -> dict[str, Any]:
    chk = engine.restrictions[CHOKE_TAG]
    h = engine.hyd
    rho = engine.props.rho
    budget = {k: 0.0 for k in BUDGET_LABELS}
    for e in engine.topology.path:
        dp = h.element_dp.get(e.id) or 0.0
        if e.kind == "inflow":
            budget["drawdown"] += dp
        elif isinstance(e, PipeElement):
            hyd_dp = rho * u.G * e.geometry.dz
            key = "tubing" if e.role == "tubing" else "flowline"
            budget[f"{key}_hydrostatic"] += hyd_dp
            budget[f"{key}_friction"] += dp - hyd_dp
        elif isinstance(e, ChokeElement):
            budget["choke"] += dp
        elif isinstance(e, ValveElement):
            budget["isolation_valves"] += dp

    def bara(tag):
        v = _val(engine, tag)
        return None if v is None else u.pa_to_bara(v)

    def degc(tag):
        v = _val(engine, tag)
        return None if v is None else u.k_to_c(v)

    q = _val(engine, "FT-101")
    dp = _val(engine, "PDT-101")
    return {
        "sim_time_s": engine.time_s,
        "choke_pct": chk.actuator.position_pct,
        "choke_capacity_m2": chk.capacity,
        "q_m3d": None if q is None else u.m3s_to_m3d(q),
        "p_bh_bara": bara("PT-001"),
        "p_tree_bara": bara("PT-101"),
        "p_uc_bara": bara("PT-102"),
        "p_dc_bara": bara("PT-103"),
        "p_arr_bara": bara("PT-201"),
        "choke_dp_bar": None if dp is None else u.pa_to_bar_delta(dp),
        "t_uc_c": degc("TT-102"),
        "t_dc_c": degc("TT-103"),
        "driving_bar": u.pa_to_bar_delta(h.driving_pressure),
        "budget_bar": {k: u.pa_to_bar_delta(v) for k, v in budget.items()},
        "reservoir_pressure_bara": u.pa_to_bara(engine.ipr.p_res),
        "downstream_pressure_bara": u.pa_to_bara(engine.p_boundary),
    }


# ----------------------------------------------------------------- conditions
BARRIERS = ("SCSSV-101", "PMV-101", "PWV-101")


def _isolation_open(e: SimulationEngine) -> bool:
    """The production barriers are fully open (annulus, swab and chemical valves are not part of the flow path)."""
    return all(e.restrictions[t].actuator.position_pct == 100.0 for t in BARRIERS if t in e.restrictions)


def _choke_at(target: float):
    def cond(e: SimulationEngine) -> bool:
        a = e.restrictions[CHOKE_TAG].actuator
        return (
            e.status == "running" and _isolation_open(e) and e.hyd.ok
            and abs(a.commanded_pct - target) <= POSITION_TOL_PCT
            and abs(a.position_pct - target) <= POSITION_TOL_PCT
        )
    return cond


def _choke_hint(target: float):
    def hint(e: SimulationEngine) -> str:
        a = e.restrictions[CHOKE_TAG].actuator
        if e.status != "running":
            return "Start or resume the simulation - valve travel only progresses while simulation time runs."
        if not _isolation_open(e):
            return "All isolation valves (SCSSV-101, PMV-101, PWV-101) must be fully open for this task."
        if abs(a.commanded_pct - target) > POSITION_TOL_PCT:
            return f"Select {CHOKE_TAG} on the schematic and set its position to {target:g} %."
        return (f"{CHOKE_TAG} is travelling: {a.position_pct:.1f} % -> {a.commanded_pct:.1f} % "
                f"(about {a.time_to_target():.0f} s of simulation time remaining).")
    return hint


# ------------------------------------------------------------- resolvers
def _ratio(obs: Obs, a: str, b: str, key: str) -> float | None:
    try:
        x, y = obs[a][key], obs[b][key]
    except KeyError:
        return None
    if x in (None, 0) or y is None:
        return None
    return y / x


def _p1_correct(obs: Obs) -> str | None:
    r = _ratio(obs, "c20", "c40", "q_m3d")
    if r is None:
        return None
    if r <= 1.0:
        return "d"
    if r < 1.8:
        return "b"
    if r <= 2.2:
        return "a"
    return "c"


def _p1_explain(obs: Obs) -> str:
    c20, c40 = obs["c20"], obs["c40"]
    rq = c40["q_m3d"] / c20["q_m3d"]
    rc = c40["choke_capacity_m2"] / c20["choke_capacity_m2"]
    return (
        f"Measured: FT-101 went from {c20['q_m3d']:.0f} to {c40['q_m3d']:.0f} m3/d (x{rq:.2f}). "
        f"The choke's flow capacity rose by x{rc:.2f} (equal-percentage characteristic), but flow rose by "
        f"less than that because the choke is in series with the reservoir inflow, the tubing and the flowline."
    )


def _p2_correct(obs: Obs) -> str | None:
    try:
        a, b = obs["c40"]["choke_dp_bar"], obs["c80"]["choke_dp_bar"]
    except KeyError:
        return None
    if a is None or b is None:
        return None
    if abs(b - a) <= 0.05 * abs(a):
        return "c"
    return "a" if b > a else "b"


def _p2_explain(obs: Obs) -> str:
    a, b = obs["c40"], obs["c80"]
    return (
        f"PDT-101 went from {a['choke_dp_bar']:.1f} to {b['choke_dp_bar']:.1f} bar. Opening the choke lowers its "
        "resistance, so even though more fluid passes, much less pressure is needed to push it through. The pressure "
        "no longer consumed by the choke is taken up by extra drawdown and friction at the higher rate."
    )


def _q3_correct(obs: Obs) -> str | None:
    try:
        a, b = obs["c20"]["p_uc_bara"], obs["c80"]["p_uc_bara"]
    except KeyError:
        return None
    if a is None or b is None:
        return None
    if abs(b - a) <= 1.0:
        return "c"
    return "a" if b < a else "b"


def _q3_explain(obs: Obs) -> str:
    a, b = obs["c20"], obs["c80"]
    return (
        f"PT-102 went from {a['p_uc_bara']:.1f} to {b['p_uc_bara']:.1f} bara. With higher flow the well draws down "
        f"more (PT-001 {a['p_bh_bara']:.1f} -> {b['p_bh_bara']:.1f} bara) and tubing friction rises, so less pressure "
        "is left at the tree. Upstream choke pressure is a consequence of the operating point, not a fixed value."
    )


# ---------------------------------------------------------------- reviews
def _budget_table(obs: Obs, keys: list[str]) -> dict:
    cols = ["Pressure use [bar]"] + [f"Choke {obs[k]['choke_pct']:.0f} %" for k in keys]
    rows = []
    for bk, label in BUDGET_LABELS.items():
        rows.append([label] + [round(obs[k]["budget_bar"][bk], 2) for k in keys])
    rows.append(["Total = P_res - P_downstream"] + [round(sum(obs[k]["budget_bar"].values()), 2) for k in keys])
    rows.append(["Flow FT-101 [m3/d]"] + [round(obs[k]["q_m3d"], 1) for k in keys])
    return {"columns": cols, "rows": rows, "emphasis_rows": [len(rows) - 2, len(rows) - 1]}


def _review1(obs: Obs, preds: dict) -> dict:
    c20, c40 = obs["c20"], obs["c40"]
    b20, b40 = c20["budget_bar"], c40["budget_bar"]
    p = preds.get("p1")
    verdict = ""
    if p and p["correct"] is not None:
        verdict = (f"Your prediction was '{p['choice_text']}'. The simulation result corresponds to "
                   f"'{p['correct_text']}' - {'correct' if p['correct'] else 'not what you predicted'}. ")
    text = (
        verdict + _p1_explain(obs) + " "
        f"Where did the pressure go? Choke differential fell from {b20['choke']:.1f} to {b40['choke']:.1f} bar, while "
        f"drawdown rose from {b20['drawdown']:.1f} to {b40['drawdown']:.1f} bar and tubing friction from "
        f"{b20['tubing_friction']:.1f} to {b40['tubing_friction']:.1f} bar. The hydrostatic head "
        f"({b20['tubing_hydrostatic'] + b20['flowline_hydrostatic']:.1f} bar) does not depend on flow. "
        "The available pressure (reservoir minus downstream) is shared among all series elements."
    )
    return {"text": text, "table": _budget_table(obs, ["c20", "c40"])}


def _review2(obs: Obs, preds: dict) -> dict:
    c20, c40, c80 = obs["c20"], obs["c40"], obs["c80"]
    p = preds.get("p2")
    verdict = ""
    if p and p["correct"] is not None:
        verdict = (f"Your prediction was '{p['choice_text']}'; the simulation shows '{p['correct_text']}'. ")
    r1 = c40["q_m3d"] / c20["q_m3d"]
    r2 = c80["q_m3d"] / c40["q_m3d"]
    share80 = 100 * c80["budget_bar"]["choke"] / sum(c80["budget_bar"].values())
    share20 = 100 * c20["budget_bar"]["choke"] / sum(c20["budget_bar"].values())
    text = (
        verdict + _p2_explain(obs) + " "
        f"Doubling the opening from 20 to 40 % gave x{r1:.2f} flow; doubling again from 40 to 80 % gave only x{r2:.2f}. "
        f"At 20 % the choke consumed {share20:.0f} % of the available pressure and controlled the rate; at 80 % it "
        f"consumes only {share80:.0f} %, so the rate is now limited mainly by the reservoir inflow and pipe friction - "
        "further opening has diminishing effect. This is why choke opening is not proportional to flow."
    )
    return {"text": text, "table": _budget_table(obs, ["c20", "c40", "c80"])}


# -------------------------------------------------------------- definition
EXERCISE = ExerciseDefinition(
    id="ex03_choke_operation",
    number=3,
    title="Exercise 3 - Choke operation",
    scenario_id="ex03_choke_operation",
    objectives=[
        "Operate the production choke and read its position, commanded position and travel.",
        "Relate choke opening to flow rate (FT-101) and choke differential pressure (PDT-101).",
        "Explain why flow is not proportional to choke opening, using a pressure budget.",
        "Interpret how upstream and downstream pressures respond to choke changes.",
    ],
    initial_configuration=[
        "Tree workstation, illustrative single-phase oil producer in the quasi-steady model (scenario 'Exercise 3 - Choke operation').",
        "SCSSV-101, PMV-101 and PWV-101 fully open.",
        "CHK-101 at 20 % opening (generic equal-percentage characteristic, full stroke 180 s).",
        "Reservoir 380 bara / 95 degC, PI 20 (m3/d)/bar; flowline arrival held at 60 bara.",
    ],
    instructions=[
        "Use the schematic to select CHK-101 and the component panel to change its position.",
        "Valve travel takes simulation time - use the speed control (10x) if you want to wait less.",
        "Make each prediction BEFORE performing the operation; it is compared with the result afterwards.",
        "Do not change boundary conditions during this exercise; if you do, explanations will use the values you set.",
    ],
    expected_observations=[
        "Flow increases when the choke opens, but not in proportion to the opening.",
        "Choke differential pressure falls as the choke opens.",
        "Pressure upstream of the choke falls and pressure downstream rises slightly as flow increases.",
        "Temperatures change slowly (thermal transient) - not instantly with the choke.",
    ],
    capture=capture,
    steps=[
        Step("intro", "info", "Introduction",
             "In this exercise you will open the production choke in two stages and investigate how flow rate and "
             "pressures respond. The model is a steady-state single-phase liquid model: at each instant the flow is "
             "the rate at which reservoir inflow balances the total resistance of the production path."),
        Step("start", "task", "Start the simulation",
             "Press START in the top bar. Simulation time will begin to run.",
             condition=lambda e: e.status == "running",
             condition_hint=lambda e: "Press START (or RESUME) in the top bar."),
        Step("t20", "task", "Record the baseline at 20 %",
             "Confirm CHK-101 is at 20 % and all isolation valves are open. The baseline readings are recorded "
             "automatically when the conditions are met.",
             condition=_choke_at(20.0), condition_hint=_choke_hint(20.0), record_as="c20"),
        Step("p1", "prediction", "Predict: open the choke from 20 % to 40 %",
             "The choke opening will double. What will happen to the production flow rate (FT-101)?",
             options=[Option("a", "Roughly double (between 1.8x and 2.2x)"),
                      Option("b", "Increase, but by less than 1.8x"),
                      Option("c", "Increase by more than 2.2x"),
                      Option("d", "Stay the same or decrease")],
             correct=_p1_correct, explanation=_p1_explain),
        Step("t40", "task", "Open the choke to 40 %",
             "Select CHK-101 and set its position to 40 %. Watch the actual position travel toward the commanded "
             "position and observe FT-101, PT-102, PT-103 and PDT-101.",
             condition=_choke_at(40.0), condition_hint=_choke_hint(40.0), record_as="c40"),
        Step("r1", "review", "Review: 20 % -> 40 %", review=_review1),
        Step("p2", "prediction", "Predict: open the choke from 40 % to 80 %",
             "What will happen to the choke differential pressure (PDT-101)?",
             options=[Option("a", "It will increase"), Option("b", "It will decrease"),
                      Option("c", "It will stay about the same (within 5 %)")],
             correct=_p2_correct, explanation=_p2_explain),
        Step("t80", "task", "Open the choke to 80 %",
             "Set CHK-101 to 80 % and wait for it to reach position.",
             condition=_choke_at(80.0), condition_hint=_choke_hint(80.0), record_as="c80"),
        Step("r2", "review", "Review: diminishing returns and the pressure budget", review=_review2),
        Step("q1", "question", "Why is flow not proportional to choke opening?",
             "Select the best explanation.",
             options=[
                 Option("a", "The choke is one of several resistances in series with reservoir inflow, tubing and flowline; "
                             "as it opens, more of the available pressure is consumed elsewhere."),
                 Option("b", "The choke characteristic is linear, so the difference is numerical error."),
                 Option("c", "Reservoir pressure drops whenever the choke is opened."),
                 Option("d", "The temperature rise across the choke reduces the flow."),
             ],
             correct="a",
             explanation="In this model reservoir pressure is a fixed boundary (depletion over months is not modelled) "
                         "and temperature does not affect the constant-property liquid's flow. The non-proportional response "
                         "comes from the nonlinear choke characteristic AND the series resistances - see the pressure budget."),
        Step("q2", "question", "Choke differential measurement",
             "Which pair of transmitters gives the pressure differential across CHK-101?",
             options=[Option("a", "PT-102 and PT-103"), Option("b", "PT-001 and PT-101"),
                      Option("c", "PT-101 and PT-201"), Option("d", "TT-102 and TT-103")],
             correct="a",
             explanation="PT-102 is immediately upstream and PT-103 immediately downstream of the choke; PDT-101 is their difference."),
        Step("q3", "question", "Upstream choke pressure",
             "Comparing 20 % with 80 %, how did the pressure upstream of the choke (PT-102) change in your run?",
             options=[Option("a", "It fell"), Option("b", "It rose"), Option("c", "It stayed the same (within 1 bar)")],
             correct=_q3_correct, explanation=_q3_explain),
        Step("summary", "summary", "Performance summary"),
    ],
)
