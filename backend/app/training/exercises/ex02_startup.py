"""Exercise 2 - Well start-up from shut-in.

The well starts fully shut in (SCSSV, PMV, PWV closed; choke closed). The
trainee opens the barriers in the correct order, protects the cold start
with methanol and brings the well on line with the choke in steps, watching
how each valve moves the pressures. Every task is judged from the
simulation; every review uses this run's readings.
"""

from __future__ import annotations

from app.training.exercises.common import Held, at, bins, capture, fmt, is_closed, is_open, running, table, travel_hint
from app.training.framework import ExerciseDefinition, Obs, Option, Step

PT_TOL_BAR = 2.0
_scssv = Held(lambda e: is_open(e, "SCSSV-101"), 120)
_pmv = Held(lambda e: is_open(e, "SCSSV-101") and is_open(e, "PMV-101"), 300)
_pwv = Held(lambda e: is_open(e, "PMV-101") and is_open(e, "PWV-101") and at(e, "CHK-101", 0.0), 120)


def _choke(target: float) -> Held:
    return Held(lambda e: is_open(e, "PWV-101") and at(e, "CHK-101", target), 600)


_c10, _c20, _c30 = _choke(10), _choke(20), _choke(30)


def _hint_held(h: Held, tag: str, target: float, what: str):
    def hint(e):
        if running(e) and at(e, tag, target):
            return f"Hold: observations are recorded after {h.seconds / 60:.0f} min of simulation time ({h.remaining(e):.0f} s left). Use 60x."
        return travel_hint(e, tag, target, what)
    return hint


def _meoh(e) -> bool:
    v = e.readings.get("FT-301")
    return running(e) and is_open(e, "CIV-301") and v is not None and v.value is not None and v.value * 86400 > 0.5


def _meoh_hint(e) -> str:
    if not is_open(e, "CIV-301"):
        return travel_hint(e, "CIV-301", 100, "open it (Chemicals page or the methanol line on the tree)")
    return "CIV-301 is open but FT-301 shows no injection yet - check that the methanol pump is running (Chemicals page)."


# ---------------------------------------------------------------- resolvers
def _p_pmv(obs: Obs) -> str | None:
    if "shut" not in obs or "pmv" not in obs:
        return None
    p = obs["pmv"]
    if abs(p["PT-104"] - p["PT-101"]) <= PT_TOL_BAR:
        return "a"
    return "c" if abs(p["PT-104"] - obs["shut"]["PT-104"]) <= PT_TOL_BAR else "b"


def _p_pmv_explain(obs: Obs) -> str:
    s, p = obs["shut"], obs["pmv"]
    move = "rose" if p["PT-104"] > s["PT-104"] + PT_TOL_BAR else "fell" if p["PT-104"] < s["PT-104"] - PT_TOL_BAR else "stayed"
    return (f"With PMV-101 closed, the tree cavity held a trapped pressure of {fmt(s['PT-104'])} bara. Opening PMV-101 connected it to the "
            f"tree bore below (PT-101 {fmt(p['PT-101'])} bara): PT-104 {move} to {fmt(p['PT-104'])} bara and the two now read the same - "
            "the shut-in wellhead pressure. A trapped cavity always equalises with the side you open it to; PWV-101 now holds the well back.")


def _p_choke(obs: Obs) -> str | None:
    if "pwv" not in obs or "c10" not in obs:
        return None
    d = obs["c10"]["PT-102"] - obs["pwv"]["PT-102"]
    return "a" if d < -PT_TOL_BAR else "b" if d > PT_TOL_BAR else "c"


def _p_choke_explain(obs: Obs) -> str:
    w, c = obs["pwv"], obs["c10"]
    return (f"Upstream of the choke the pressure went from {fmt(w['PT-102'])} bara (shut-in, no flow) to {fmt(c['PT-102'])} bara at 10 %: "
            f"once fluid flows, part of the reservoir pressure is used up by drawdown (bottom-hole {fmt(w['PT-001'])} -> "
            f"{fmt(c['PT-001'])} bara) and tubing friction, so the wellhead pressure FALLS. Flow rose to {fmt(c['FT-101'], 0)} m3/d.")


def _p_ramp(obs: Obs) -> str | None:
    try:
        r = obs["c30"]["FT-101"] / obs["c10"]["FT-101"]
    except (KeyError, TypeError, ZeroDivisionError):
        return None
    return bins(r, [2.7, 3.3], ["c", "b", "a"])


def _p_ramp_explain(obs: Obs) -> str:
    c10, c30 = obs["c10"], obs["c30"]
    r = c30["FT-101"] / c10["FT-101"]
    return (f"Flow went from {fmt(c10['FT-101'], 0)} to {fmt(c30['FT-101'], 0)} m3/d: {r:.2f} times for three times the opening. The "
            "choke is one resistance in series with the reservoir, tubing and flowline, and its characteristic is non-linear "
            f"(choke dP {fmt(c10['PDT-101'])} -> {fmt(c30['PDT-101'])} bar).")


def _review_open(obs: Obs, preds: dict) -> dict:
    s, w = obs["shut"], obs["pwv"]
    v = preds.get("p_pmv")
    lead = f"Your prediction: '{v['choice_text']}'. Result: '{v['correct_text']}'. " if v and v["correct"] is not None else ""
    text = (lead + _p_pmv_explain(obs) + f" Opening PWV-101 then equalised the wing with it, up to the choke (PT-102 {fmt(w['PT-102'])} bara), "
            f"while downstream of the closed choke PT-103 stayed at the flowline pressure ({fmt(w['PT-103'])} bara). The choke now holds "
            f"the whole differential ({fmt(w['PDT-101'])} bar) - exactly what it is designed for. The bottom-hole gauge PT-001 stayed near "
            f"the shut-in reservoir pressure ({fmt(s['PT-001'])} -> {fmt(w['PT-001'])} bara) because nothing is flowing yet.")
    t = table(obs, [("shut", "All closed"), ("scssv", "SCSSV-101 open"), ("pmv", "PMV-101 open"), ("pwv", "PWV-101 open (choke shut)")],
              [("PT-001", "PT-001 bara", 1), ("PT-101", "PT-101 bara", 1), ("PT-104", "PT-104 bara", 1), ("PT-102", "PT-102 bara", 1),
               ("PT-103", "PT-103 bara", 1), ("PDT-101", "PDT-101 bar", 1)])
    return {"text": text, "table": t}


def _review_ramp(obs: Obs, preds: dict) -> dict:
    v = preds.get("p_ramp")
    lead = f"Your prediction: '{v['choice_text']}'. Result: '{v['correct_text']}'. " if v and v["correct"] is not None else ""
    c10, c30 = obs["c10"], obs["c30"]
    text = (lead + _p_ramp_explain(obs) + f" Each step lowered the wellhead pressure (PT-102 {fmt(c10['PT-102'])} -> {fmt(c30['PT-102'])} "
            f"bara) and raised the drawdown at the sandface (PT-001 {fmt(c10['PT-001'])} -> {fmt(c30['PT-001'])} bara). Ramping in steps "
            "lets the flowline warm up and the pressures settle - and lets you stop if anything abnormal appears. "
            f"The tree temperature TT-104 went from {fmt(c10['TT-104'])} to {fmt(c30['TT-104'])} degC: at the start the flowing fluid "
            "is cold and at high pressure, which is why methanol was injected until the well warmed up.")
    t = table(obs, [("c10", "Choke 10 %"), ("c20", "Choke 20 %"), ("c30", "Choke 30 %")],
              [("FT-101", "FT-101 m3/d", 0), ("PT-001", "PT-001 bara", 1), ("PT-102", "PT-102 bara", 1), ("PT-103", "PT-103 bara", 1),
               ("PDT-101", "PDT-101 bar", 1), ("TT-104", "TT-104 degC", 1)])
    return {"text": text, "table": t}


EXERCISE = ExerciseDefinition(
    id="ex02_startup",
    number=2,
    title="Exercise 2 - Well start-up from shut-in",
    scenario_id="training_startup",
    objectives=[
        "Open the well barriers in the correct order: SCSSV, master (PMV), wing (PWV), then the choke.",
        "Explain why the choke - not a gate valve - takes the pressure differential when the well is brought on line.",
        "Protect a cold start with methanol injection into the tree.",
        "Read how each valve operation moves the cavity, wellhead, downstream and bottom-hole pressures.",
    ],
    initial_configuration=[
        "Tree workstation, single-phase oil producer, fully SHUT IN: SCSSV-101, PMV-101, PWV-101 closed, CHK-101 at 0 %.",
        "Methanol pump running, CIV-301 closed. LP and HP hydraulic supplies available.",
    ],
    instructions=[
        "Operate the valves from the Christmas tree (click a valve) or the Valves & actuators page.",
        "Use 60x speed while waiting: valves take tens of seconds to stroke and pressures take minutes to settle.",
        "Make each prediction BEFORE you act; it is resolved from what your simulation actually does.",
    ],
    expected_observations=[
            "Opening PMV-101 equalises the cavity (PT-104) with the shut-in wellhead pressure below it.",
        "With PWV-101 open and the choke shut, the choke holds the full differential (PDT-101).",
        "Cracking the choke starts flow: wellhead pressure falls, bottom-hole pressure falls (drawdown), flow rises.",
    ],
    capture=capture,
    steps=[
        Step("intro", "info", "1 - A shut-in subsea well",
             "The well is fully shut in. Look at the Christmas tree: the SCSSV deep in the tubing, the production master valve (PMV) and "
             "wing valve (PWV) on the tree, then the production choke (CHK-101). All four are closed. Note PT-001 (downhole), PT-101 "
             "(tree bore below PMV), PT-104 (tree cavity between PMV and PWV), PT-102 / PT-103 (either side of the choke)."),
        Step("t_start", "task", "Start the simulation",
             "Press START. The baseline of the shut-in well is recorded.",
             condition=running, condition_hint=lambda e: "Press START in the top bar.", record_as="shut"),
        Step("q_order", "question", "The start-up order",
             "In which order are the valves opened to bring a subsea well on line?",
             options=[Option("a", "SCSSV, PMV, PWV, then crack the choke"), Option("b", "Choke, PWV, PMV, then SCSSV"),
                      Option("c", "PWV, PMV, SCSSV, choke"), Option("d", "All at the same time")],
             correct="a",
             explanation="Open from the reservoir outward: the downhole safety valve first, then the tree master and wing valves "
                         "with no flow through them, and only then the choke, which is designed to throttle and take the differential."),
        Step("t_scssv", "task", "2 - Open the SCSSV",
             "Open SCSSV-101 (surface-controlled subsurface safety valve).",
             condition=_scssv, condition_hint=_hint_held(_scssv, "SCSSV-101", 100, "open it"), record_as="scssv"),
        Step("p_pmv", "prediction", "Predict: open the master valve",
             "PWV-101 stays closed. When you open PMV-101, what will the tree cavity pressure PT-104 do?",
             options=[Option("a", "Equalise with the tree bore below PMV (PT-101), up or down"),
                      Option("b", "Fall to the flowline pressure"), Option("c", "Stay at its trapped value")],
             correct=_p_pmv, explanation=_p_pmv_explain),
        Step("t_pmv", "task", "3 - Open the production master valve",
             "Open PMV-101 and watch PT-104 on the tree.",
             condition=_pmv, condition_hint=_hint_held(_pmv, "PMV-101", 100, "open it"), record_as="pmv"),
        Step("t_pwv", "task", "4 - Open the production wing valve",
             "Open PWV-101. The choke stays at 0 %: watch PT-102 (upstream of the choke) and PDT-101.",
             condition=_pwv, condition_hint=_hint_held(_pwv, "PWV-101", 100, "open it (keep the choke at 0 %)"), record_as="pwv"),
        Step("r_open", "review", "Review: opening the barriers", review=_review_open),
        Step("t_meoh", "task", "5 - Methanol for the cold start",
             "Hydrates can form when cold, high-pressure gas and water meet - exactly the conditions of a cold start. Open CIV-301 "
             "(methanol into the tree) and confirm injection on FT-301.",
             condition=_meoh, condition_hint=_meoh_hint, record_as="meoh"),
        Step("p_choke", "prediction", "Predict: crack the choke",
             "When you open CHK-101 to 10 %, what will the pressure upstream of the choke (PT-102) do?",
             options=[Option("a", "Fall"), Option("b", "Rise"), Option("c", "Stay the same")],
             correct=_p_choke, explanation=_p_choke_explain),
        Step("t_c10", "task", "6 - Crack the choke to 10 %",
             "Set CHK-101 to 10 % and hold for 10 minutes of simulation time.",
             condition=_c10, condition_hint=_hint_held(_c10, "CHK-101", 10, "set it to 10 %"), record_as="c10"),
        Step("t_c20", "task", "Ramp to 20 %",
             "Set CHK-101 to 20 % and hold.",
             condition=_c20, condition_hint=_hint_held(_c20, "CHK-101", 20, "set it to 20 %"), record_as="c20"),
        Step("p_ramp", "prediction", "Predict: 10 % -> 30 %",
             "At 30 % the choke is three times as open as at 10 %. Compared with 10 %, the flow FT-101 will be:",
             options=[Option("a", "More than 3.3 times"), Option("b", "About 3 times (2.7 - 3.3)"), Option("c", "Less than 2.7 times")],
             correct=_p_ramp, explanation=_p_ramp_explain),
        Step("t_c30", "task", "Ramp to 30 %",
             "Set CHK-101 to 30 % and hold.",
             condition=_c30, condition_hint=_hint_held(_c30, "CHK-101", 30, "set it to 30 %"), record_as="c30"),
        Step("r_ramp", "review", "Review: bringing the well on line", review=_review_ramp),
        Step("t_meoh_off", "task", "7 - Stop the methanol",
             "The well is flowing and warming up. Close CIV-301.",
             condition=lambda e: running(e) and is_closed(e, "CIV-301"),
             condition_hint=lambda e: travel_hint(e, "CIV-301", 0, "close it"), record_as="meoh_off"),
        Step("q_choke", "question", "Who takes the differential?",
             "Why is the well brought on line with the choke and not by opening PMV or PWV under flow?",
             options=[Option("a", "Gate valves are isolation valves: opening them against a large differential under flow erodes the "
                                   "gate and seats. The choke is designed to throttle."),
                      Option("b", "The choke opens faster."), Option("c", "PMV and PWV cannot be opened while the SCSSV is open.")],
             correct="a", explanation="Isolation (gate) valves are operated with no flow and as little differential as possible; "
                                      "the choke is the throttling device."),
        Step("q_meoh", "question", "Why methanol?",
             "Why is methanol injected during a cold start?",
             options=[Option("a", "It inhibits hydrate formation while the fluid is cold and at high pressure"),
                      Option("b", "It increases the reservoir pressure"), Option("c", "It cleans sand out of the choke")],
             correct="a", explanation="Methanol shifts the hydrate-formation curve to lower temperature until the flowline warms up."),
        Step("summary", "summary", "Performance summary"),
    ],
)
