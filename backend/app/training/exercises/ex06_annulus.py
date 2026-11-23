"""Exercise 6 - Annulus monitoring and bleed-off.

The trainee reads the A-annulus pressure, lines up the annulus master and
wing valves, bleeds the annulus to the service line and watches what the
pressure does afterwards (thermal effects or a barrier leak).
"""

from __future__ import annotations

from app.training.exercises.common import Held, capture, fmt, is_closed, is_open, running, table, travel_hint
from app.training.framework import ExerciseDefinition, Obs, Option, Step

TOL = 2.0
_amv = Held(lambda e: is_open(e, "AMV-101") and is_closed(e, "AWV-101"), 120)
_bleed = Held(lambda e: is_open(e, "AMV-101") and is_open(e, "AWV-101"), 600)
_closed = Held(lambda e: is_closed(e, "AWV-101") and is_closed(e, "AMV-101"), 60)
_after = Held(lambda e: is_closed(e, "AWV-101") and is_closed(e, "AMV-101"), 7200)


def _hint(h: Held, ok, what: str):
    def hint(e):
        if not running(e):
            return "Press START / RESUME."
        if ok(e):
            return f"Hold: recorded after {h.seconds / 60:.0f} min of simulation time ({h.remaining(e):.0f} s left)."
        return what
    return hint


def _p_amv(obs: Obs) -> str | None:
    if "amv" not in obs:
        return None
    a = obs["amv"]
    return "a" if abs(a["PT-402"] - a["PT-401"]) <= TOL else "c"


def _p_amv_explain(obs: Obs) -> str:
    b, a = obs["base"], obs["amv"]
    return (f"With AMV-101 open, PT-402 (between AMV and AWV) and PT-401 (the annulus below AMV) read the same: {fmt(a['PT-401'])} and "
            f"{fmt(a['PT-402'])} bara (before: {fmt(b['PT-401'])} and {fmt(b['PT-402'])} bara). Opening a valve between two volumes "
            "equalises them.")


def _p_bleed(obs: Obs) -> str | None:
    if "bleed" not in obs:
        return None
    x = obs["bleed"]
    return "a" if abs(x["PT-401"] - x["PT-404"]) <= 3.0 else "c" if abs(x["PT-401"] - obs["amv"]["PT-401"]) <= TOL else "b"


def _p_bleed_explain(obs: Obs) -> str:
    a, x = obs["amv"], obs["bleed"]
    return (f"Opening AWV-101 connected the annulus to the service line: PT-401 fell from {fmt(a['PT-401'])} to {fmt(x['PT-401'])} bara, "
            f"the service-line pressure (PT-404 {fmt(x['PT-404'])} bara). A bleed takes the annulus down to the pressure of whatever "
            "it is opened to - here the service line, not zero.")


def _p_after(obs: Obs) -> str | None:
    if "closed" not in obs or "after" not in obs:
        return None
    d = obs["after"]["PT-401"] - obs["closed"]["PT-401"]
    return "a" if d > 1.0 else "b" if d < -1.0 else "c"


def _p_after_explain(obs: Obs) -> str:
    c, f = obs["closed"], obs["after"]
    d = f["PT-401"] - c["PT-401"]
    why = ("A rise in an isolated annulus comes from heating of the trapped fluid (annular pressure build-up) or from a LEAK across a "
           "barrier. If it builds back again and again at a steady temperature, it is sustained casing pressure and must be "
           "investigated." if d > 1.0 else
           "A fall in an isolated annulus comes from cooling and contraction of the trapped fluid after the bleed - it is not a leak. "
           "A leak would make it build back up." if d < -1.0 else
           "No significant change: no thermal effect and no sign of a leak over this period.")
    return f"Over two hours isolated, PT-401 went from {fmt(c['PT-401'])} to {fmt(f['PT-401'])} bara ({d:+.1f} bar). " + why


def _review(obs: Obs, preds: dict) -> dict:
    v = preds.get("p_after")
    lead = f"Your prediction: '{v['choice_text']}'. Result: '{v['correct_text']}'. " if v and v["correct"] is not None else ""
    t = table(obs, [("base", "Start (AMV closed)"), ("amv", "AMV-101 open"), ("bleed", "AWV-101 open (bleed)"),
                    ("closed", "AWV, AMV closed"), ("after", "2 h later")],
              [("PT-401", "PT-401 bara", 1), ("PT-402", "PT-402 bara", 1), ("PT-404", "PT-404 bara", 1), ("TT-104", "TT-104 degC", 1)])
    return {"text": lead + _p_after_explain(obs), "table": t}


EXERCISE = ExerciseDefinition(
    id="ex06_annulus",
    number=6,
    title="Exercise 6 - Annulus monitoring and bleed-off",
    scenario_id="xt_230xp22b",
    objectives=[
        "Read the A-annulus pressure and explain why it is monitored.",
        "Line up and bleed the annulus through AMV-101 and AWV-101 to the service line.",
        "Interpret the annulus pressure after the bleed: thermal effect or barrier leak.",
    ],
    initial_configuration=["Tree workstation, single-phase producer flowing; A-annulus at about 80 bara.",
                           "AMV-101, AWV-101 and XOV-101 closed; SLV-101 open to the service line."],
    instructions=["Operate the annulus valves on the left of the tree or on the Valves page.", "Use 300x for the two-hour watch."],
    expected_observations=["Opening AMV equalises PT-402 with PT-401.", "Opening AWV bleeds the annulus to the service-line pressure.",
                           "After isolation the annulus pressure changes only with temperature - or with a leak."],
    capture=capture,
    steps=[
        Step("intro", "info", "1 - The A-annulus",
             "The A-annulus is the space between the production tubing and the production casing. Its pressure is a barrier "
             "indicator: an annulus that keeps pressuring up can mean a leak in the tubing or casing. On the tree it is reached through "
             "the annulus master valve (AMV-101) and the annulus wing valve (AWV-101), which lead to the service line."),
        Step("t_start", "task", "Start the simulation", "Press START.",
             condition=running, condition_hint=lambda e: "Press START in the top bar.", record_as="base"),
        Step("q_tx", "question", "Which transmitter?",
             "With AMV-101 closed, which transmitter reads the A-annulus itself?",
             options=[Option("a", "PT-401 (below AMV)"), Option("b", "PT-402 (between AMV and AWV)"), Option("c", "PT-404 (service line)")],
             correct="a", explanation="PT-401 sits below AMV-101 and always sees the annulus; PT-402 only sees it when AMV-101 is open."),
        Step("p_amv", "prediction", "Predict: open AMV-101",
             "AWV-101 stays closed. When you open AMV-101, PT-402 will:",
             options=[Option("a", "Equalise with PT-401"), Option("b", "Fall to the service-line pressure"), Option("c", "Not change")],
             correct=_p_amv, explanation=_p_amv_explain),
        Step("t_amv", "task", "2 - Open the annulus master valve",
             "Open AMV-101 (AWV-101 closed).",
             condition=_amv, condition_hint=_hint(_amv, lambda e: is_open(e, "AMV-101") and is_closed(e, "AWV-101"),
                                                 "Open AMV-101 and keep AWV-101 closed."), record_as="amv"),
        Step("p_bleed", "prediction", "Predict: bleed through AWV-101",
             "When you open AWV-101, the annulus pressure PT-401 will fall to about:",
             options=[Option("a", "The service-line pressure (PT-404)"), Option("b", "Zero (atmospheric)"), Option("c", "It will not change")],
             correct=_p_bleed, explanation=_p_bleed_explain),
        Step("t_bleed", "task", "3 - Bleed the annulus",
             "Open AWV-101 and watch PT-401 and PT-402 fall.",
             condition=_bleed, condition_hint=_hint(_bleed, lambda e: is_open(e, "AMV-101") and is_open(e, "AWV-101"),
                                                   "Open AWV-101 (AMV-101 open)."), record_as="bleed"),
        Step("t_close", "task", "4 - Isolate the annulus",
             "Close AWV-101, then AMV-101.",
             condition=_closed, condition_hint=_hint(_closed, lambda e: is_closed(e, "AWV-101") and is_closed(e, "AMV-101"),
                                                    "Close AWV-101 and AMV-101."), record_as="closed"),
        Step("p_after", "prediction", "Predict: two hours later",
             "With the annulus isolated and the well producing, what will PT-401 do over the next two hours?",
             options=[Option("a", "Rise"), Option("b", "Fall"), Option("c", "Stay the same (within 1 bar)")],
             correct=_p_after, explanation=_p_after_explain),
        Step("t_after", "task", "5 - Watch the isolated annulus",
             "Keep the annulus isolated for two hours of simulation time (300x).",
             condition=_after, condition_hint=lambda e: f"Isolated: {_after.remaining(e):.0f} s of simulation time left." if running(e)
             else "Press RESUME.", record_as="after"),
        Step("r_ann", "review", "Review: annulus behaviour", review=_review),
        Step("q_scp", "question", "Sustained casing pressure",
             "An annulus bled to 20 bara builds back to 80 bara within days, again and again, while the well flows at a steady "
             "temperature. What does it suggest?",
             options=[Option("a", "Communication across a barrier (a leak) - report and investigate"),
                      Option("b", "Normal thermal expansion"), Option("c", "A faulty pressure transmitter, nothing else")],
             correct="a", explanation="Repeated build-up at constant temperature cannot be thermal expansion: it is sustained casing "
                                      "pressure, a sign that fluid crosses a barrier."),
        Step("summary", "summary", "Performance summary"),
    ],
)
