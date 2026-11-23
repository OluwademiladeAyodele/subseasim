"""Exercise 4 - Well shut-in and pressure build-up.

From steady production the trainee shuts the well in, in the correct order
(choke, wing, master, SCSSV), and follows what every transmitter does: the
wellhead pressure rising as flow stops, the downstream side falling to the
flowline, the trapped cavity, and the bottom-hole build-up from the reservoir.
"""

from __future__ import annotations

from app.training.exercises.common import Held, at, capture, fmt, is_closed, running, table, travel_hint
from app.training.framework import ExerciseDefinition, Obs, Option, Step

TOL = 2.0
_chk = Held(lambda e: at(e, "CHK-101", 0.0), 600)
_pwv = Held(lambda e: at(e, "CHK-101", 0.0) and is_closed(e, "PWV-101"), 120)
_pmv = Held(lambda e: is_closed(e, "PWV-101") and is_closed(e, "PMV-101"), 120)
_scssv = Held(lambda e: is_closed(e, "PMV-101") and is_closed(e, "SCSSV-101"), 60)
_bu = Held(lambda e: is_closed(e, "SCSSV-101") and is_closed(e, "PMV-101"), 3600)


def _hint(h: Held, tag: str, target: float, what: str):
    def hint(e):
        if running(e) and at(e, tag, target):
            return f"Hold: recorded after {h.seconds / 60:.0f} min of simulation time ({h.remaining(e):.0f} s left). Use 60x or 300x."
        return travel_hint(e, tag, target, what)
    return hint


def _p_chk(obs: Obs) -> str | None:
    if "flow" not in obs or "chk0" not in obs:
        return None
    d = obs["chk0"]["PT-102"] - obs["flow"]["PT-102"]
    return "a" if d > TOL else "b" if d < -TOL else "c"


def _p_chk_explain(obs: Obs) -> str:
    f, c = obs["flow"], obs["chk0"]
    return (f"PT-102 went from {fmt(f['PT-102'])} to {fmt(c['PT-102'])} bara and flow from {fmt(f['FT-101'], 0)} to "
            f"{fmt(c['FT-101'], 0)} m3/d. With no flow there is no drawdown and no friction loss, so the wellhead approaches the "
            f"shut-in pressure (reservoir pressure minus the hydrostatic head of the fluid column). Downstream, PT-103 fell from "
            f"{fmt(f['PT-103'])} to {fmt(c['PT-103'])} bara, the flowline pressure.")


def _p_bu(obs: Obs) -> str | None:
    if "scssv0" not in obs or "bu" not in obs:
        return None
    d = obs["bu"]["PT-001"] - obs["scssv0"]["PT-001"]
    return "a" if d > 0.5 else "b" if d < -0.5 else "c"


def _p_bu_explain(obs: Obs) -> str:
    s, b = obs["scssv0"], obs["bu"]
    return (f"PT-001 went from {fmt(s['PT-001'])} to {fmt(b['PT-001'])} bara in one hour: the reservoir keeps feeding the near-well "
            "region after the well stops, so the bottom-hole pressure builds up toward the reservoir pressure - quickly at first, "
            "then ever more slowly. This pressure build-up is what well-test engineers analyse.")


def _review_chk(obs: Obs, preds: dict) -> dict:
    v = preds.get("p_chk")
    lead = f"Your prediction: '{v['choice_text']}'. Result: '{v['correct_text']}'. " if v and v["correct"] is not None else ""
    f, c = obs["flow"], obs["chk0"]
    text = (lead + _p_chk_explain(obs) + f" The bottom-hole pressure PT-001 rose from {fmt(f['PT-001'])} to {fmt(c['PT-001'])} bara "
            "as the drawdown disappeared. The choke now holds the full differential "
            f"(PDT-101 {fmt(c['PDT-101'])} bar) and the gate valves can be closed with no flow through them.")
    return {"text": text}


def _review_all(obs: Obs, preds: dict) -> dict:
    v = preds.get("p_bu")
    lead = f"Your prediction: '{v['choice_text']}'. Result: '{v['correct_text']}'. " if v and v["correct"] is not None else ""
    p, b = obs["pmv0"], obs["bu"]
    text = (lead + _p_bu_explain(obs) + f" Between the closed PMV and PWV the cavity keeps a TRAPPED pressure (PT-104 {fmt(p['PT-104'])} "
            f"-> {fmt(b['PT-104'])} bara): it does not bleed away by itself. Before any valve is opened again, the operator checks the "
            "differential across it - opening a gate valve against a large trapped differential damages it.")
    t = table(obs, [("flow", "Producing"), ("chk0", "Choke closed"), ("pwv0", "PWV-101 closed"), ("pmv0", "PMV-101 closed"),
                    ("scssv0", "SCSSV-101 closed"), ("bu", "After 1 h build-up")],
              [("FT-101", "FT-101 m3/d", 0), ("PT-001", "PT-001 bara", 1), ("PT-101", "PT-101 bara", 1), ("PT-104", "PT-104 bara", 1),
               ("PT-102", "PT-102 bara", 1), ("PT-103", "PT-103 bara", 1)])
    return {"text": text, "table": t}


EXERCISE = ExerciseDefinition(
    id="ex04_shutin",
    number=4,
    title="Exercise 4 - Well shut-in and pressure build-up",
    scenario_id="xt_230xp22b",
    objectives=[
        "Shut a producing well in, in the correct order: choke, wing valve (PWV), master valve (PMV), SCSSV.",
        "Explain why flow is stopped with the choke before the gate valves are closed.",
        "Read the wellhead pressure rise, the downstream fall to flowline pressure and the trapped cavity pressure.",
        "Recognise the bottom-hole pressure build-up after shut-in.",
    ],
    initial_configuration=["Tree workstation, single-phase producer, flowing at CHK-101 30 %; all barriers open."],
    instructions=["Operate the valves from the Christmas tree or the Valves page; use 60x / 300x while waiting.",
                  "Make each prediction before you act."],
    expected_observations=["Closing the choke stops flow: PT-102 rises, PT-103 falls, PT-001 rises.",
                           "The cavity between PMV and PWV keeps a trapped pressure.", "PT-001 keeps building up slowly."],
    capture=capture,
    steps=[
        Step("intro", "info", "1 - Shutting a well in",
             "The well is producing. You will shut it in as an operator would for a planned shutdown: first stop the flow with the "
             "choke, then close the gate valves from the outside in. Watch PT-102 (upstream of the choke), PT-103 (downstream), "
             "PT-104 (tree cavity), PT-001 (bottom hole) and FT-101."),
        Step("t_start", "task", "Start the simulation",
             "Press START. The producing state is recorded.",
             condition=running, condition_hint=lambda e: "Press START in the top bar.", record_as="flow"),
        Step("q_order", "question", "The shut-in order",
             "In which order are the valves closed for a planned shut-in?",
             options=[Option("a", "Choke, PWV, PMV, SCSSV"), Option("b", "SCSSV, PMV, PWV, choke"), Option("c", "PMV first, then the rest")],
             correct="a",
             explanation="The reverse of start-up: stop the flow with the throttling device, then close the isolation valves "
                         "with no flow through them, from the outside in."),
        Step("p_chk", "prediction", "Predict: close the choke",
             "When CHK-101 closes and the flow stops, what will the pressure upstream of the choke (PT-102) do?",
             options=[Option("a", "Rise toward the shut-in wellhead pressure"), Option("b", "Fall"), Option("c", "Stay the same")],
             correct=_p_chk, explanation=_p_chk_explain),
        Step("t_chk", "task", "2 - Close the choke",
             "Set CHK-101 to 0 % (it takes about three minutes to stroke) and hold.",
             condition=_chk, condition_hint=_hint(_chk, "CHK-101", 0, "set it to 0 %"), record_as="chk0"),
        Step("r_chk", "review", "Review: stopping the flow", review=_review_chk),
        Step("t_pwv", "task", "3 - Close the wing valve",
             "Close PWV-101.",
             condition=_pwv, condition_hint=_hint(_pwv, "PWV-101", 0, "close it"), record_as="pwv0"),
        Step("t_pmv", "task", "4 - Close the master valve",
             "Close PMV-101.",
             condition=_pmv, condition_hint=_hint(_pmv, "PMV-101", 0, "close it"), record_as="pmv0"),
        Step("t_scssv", "task", "5 - Close the SCSSV",
             "Close SCSSV-101, the downhole safety valve.",
             condition=_scssv, condition_hint=_hint(_scssv, "SCSSV-101", 0, "close it"), record_as="scssv0"),
        Step("p_bu", "prediction", "Predict: the next hour",
             "Over the next hour, what will the bottom-hole pressure PT-001 do?",
             options=[Option("a", "Keep rising slowly (build-up)"), Option("b", "Fall"), Option("c", "Stay exactly the same")],
             correct=_p_bu, explanation=_p_bu_explain),
        Step("t_bu", "task", "6 - Watch the build-up",
             "Keep the well shut in for one hour of simulation time (300x makes this 12 s). Watch PT-001 on the Trends page.",
             condition=_bu, condition_hint=lambda e: f"Shut in: {_bu.remaining(e):.0f} s of simulation time left." if running(e)
             else "Press RESUME.", record_as="bu"),
        Step("r_all", "review", "Review: the shut-in well", review=_review_all),
        Step("q_trapped", "question", "Trapped pressure",
             "PT-104 still reads a high pressure with PMV and PWV closed. What must be done before opening PWV-101 again?",
             options=[Option("a", "Check the differential across PWV-101 and equalise (or bleed) it before opening"),
                      Option("b", "Nothing - the pressure will disappear by itself"), Option("c", "Close the SCSSV again")],
             correct="a", explanation="Trapped pressure stays until it is bled off or equalised; opening against it damages the valve "
                                      "and causes a pressure surge."),
        Step("q_choke", "question", "Why the choke first?",
             "Why is the flow stopped with the choke before the gate valves are closed?",
             options=[Option("a", "Gate valves are not designed to cut flow: closing them under flow erodes the gate and seat"),
                      Option("b", "The choke closes faster"), Option("c", "It does not matter")],
             correct="a", explanation="Gate valves isolate; the choke throttles. Closing a gate valve under flow damages its sealing faces "
                                      "(and in an emergency they still close, accepting that damage)."),
        Step("summary", "summary", "Performance summary"),
    ],
)
