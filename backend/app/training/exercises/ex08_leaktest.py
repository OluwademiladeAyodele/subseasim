"""Exercise 8 - Leak (inflow) test of the production master valve.

PMV-101 has a small seat leak the trainee does not know about. The trainee
stops the flow, closes PMV-101, bleeds the tree cavity to flowline pressure,
traps it, and runs an inflow test from the Integrity tests page. The result,
the build-up and the leak rate all come from the simulation.
"""

from __future__ import annotations

from typing import Any

from app.training.exercises.common import Held, at, capture as base_capture, fmt, is_closed, running, travel_hint
from app.training.framework import ExerciseDefinition, Obs, Option, Step


def _test(e) -> Any:
    tests = [t for t in e.integrity.tests if t.type == "inflow" and t.valve == "PMV-101"]
    return tests[-1] if tests else None


def capture(e) -> dict:
    out = base_capture(e)
    t = _test(e)
    out["test"] = None if t is None else {"phase": t.phase, "result": dict(t.result), "message": t.message,
                                          "max_change_bar": t.max_change_bar, "duration_s": t.duration_s}
    return out


_stop = Held(lambda e: at(e, "CHK-101", 0.0), 300)
_pmv = Held(lambda e: at(e, "CHK-101", 0.0) and is_closed(e, "PMV-101"), 60)


def _bled(e) -> bool:
    p104, p103 = e.readings["PT-104"].value, e.readings["PT-103"].value
    return (running(e) and is_closed(e, "PMV-101") and e.restrictions["CHK-101"].actuator.position_pct >= 5
            and p104 is not None and p103 is not None and p104 - p103 < 5e5)


_trap = Held(lambda e: is_closed(e, "PMV-101") and is_closed(e, "PWV-101"), 60)


def _done(e) -> bool:
    t = _test(e)
    return t is not None and t.phase in ("passed", "failed")


def _test_hint(e) -> str:
    t = _test(e)
    if t is None:
        return ("Integrity tests page: start an INFLOW test on the tree cavity (transmitter PT-104), barrier PMV-101. Keep PMV-101 "
                "and PWV-101 closed.")
    if t.phase in ("aborted",):
        return "The test was aborted (isolation lost?). Close PMV-101 and PWV-101 and start it again."
    return f"Test {t.phase}: {t.message or ''} Use 60x - 300x."


def _p_result(obs: Obs) -> str | None:
    t = (obs.get("test") or {}).get("test")
    if not t or t["phase"] not in ("passed", "failed"):
        return None
    return "a" if t["phase"] == "passed" else "b"


def _p_result_explain(obs: Obs) -> str:
    t = obs["test"]["test"]
    r = t["result"]
    return (f"During the {r.get('hold_duration_s', 0) / 60:.0f}-minute hold the trapped cavity went from {fmt(r.get('p_start_bara'))} to "
            f"{fmt(r.get('p_end_bara'))} bara ({r.get('change_bar', 0):+.2f} bar, limit {t['max_change_bar']:g} bar): "
            f"{'PASS' if t['phase'] == 'passed' else 'FAIL'}. The only way into the cavity is across the closed PMV seat (or "
            f"thermal expansion of the trapped fluid): apparent volume change {r.get('apparent_leak_l_per_min', 0):+.4f} L/min, of which "
            f"thermal {r.get('thermal_contribution_l_per_min', 0):+.4f} L/min - net leak {r.get('net_leak_l_per_min', 0):+.4f} L/min.")


def _review(obs: Obs, preds: dict) -> dict:
    v = preds.get("p_result")
    lead = f"Your prediction: '{v['choice_text']}'. Result: '{v['correct_text']}'. " if v and v["correct"] is not None else ""
    b, tr = obs["bled"], obs["trap"]
    text = (lead + _p_result_explain(obs) + f" The test worked because you created a differential across PMV-101 in the direction "
            f"it must seal: well pressure below it (PT-101 {fmt(tr['PT-101'])} bara) and the cavity bled down to {fmt(b['PT-104'])} "
            "bara above it. The acceptance limit here is an ILLUSTRATIVE training value; real limits come from the company's "
            "barrier-test procedure.")
    return {"text": text}


EXERCISE = ExerciseDefinition(
    id="ex08_leaktest",
    number=8,
    title="Exercise 8 - Leak test of the production master valve",
    scenario_id="training_leaking_pmv",
    objectives=[
        "Prepare an inflow (leak) test of PMV-101: stop flow, close the barrier, bleed and trap the cavity.",
        "Run the test from the Integrity tests page and read the build-up, the leak rate and the thermal correction.",
        "Decide what a failed barrier test means for operations.",
    ],
    initial_configuration=["Tree workstation, single-phase producer flowing at CHK-101 30 %.",
                           "One tree valve may not seal perfectly - the test will tell."],
    instructions=["Operate the valves on the Christmas tree; start the test on the Integrity tests page.",
                  "Use 60x - 300x while the test stabilises and holds (about 20 minutes of simulation time)."],
    expected_observations=["The cavity bleeds to flowline pressure through PWV and the choke.",
                           "With PMV and PWV closed, any cavity pressure rise comes from the PMV seat or from heating."],
    capture=capture,
    steps=[
        Step("intro", "info", "1 - Why test a barrier?",
             "Tree valves are well barriers. They are tested regularly by giving them a differential in the direction they must seal "
             "and watching for leakage. For PMV-101: the well pressure below it, a bled-down cavity above it, PWV-101 closed to trap "
             "the cavity. If PT-104 rises, fluid is crossing the PMV seat."),
        Step("t_start", "task", "Start the simulation", "Press START.",
             condition=running, condition_hint=lambda e: "Press START in the top bar.", record_as="base"),
        Step("t_stop", "task", "2 - Stop the flow",
             "Close CHK-101 (0 %).",
             condition=_stop, condition_hint=lambda e: travel_hint(e, "CHK-101", 0, "set it to 0 %") if not at(e, "CHK-101", 0)
             else f"Hold ({_stop.remaining(e):.0f} s left).", record_as="stopped"),
        Step("t_pmv", "task", "3 - Close the barrier under test",
             "Close PMV-101.",
             condition=_pmv, condition_hint=lambda e: travel_hint(e, "PMV-101", 0, "close it"), record_as="pmv"),
        Step("t_bleed", "task", "4 - Bleed the cavity",
             "With PMV-101 closed and PWV-101 open, open CHK-101 to about 20 % so the tree cavity bleeds to the flowline. The task "
             "completes when PT-104 is within 5 bar of PT-103.",
             condition=_bled, condition_hint=lambda e: "Open CHK-101 to about 20 % (PMV-101 closed, PWV-101 open)." if running(e)
             else "Press RESUME.", record_as="bled"),
        Step("t_trap", "task", "5 - Trap the cavity",
             "Close PWV-101, then close the choke again.",
             condition=_trap, condition_hint=lambda e: travel_hint(e, "PWV-101", 0, "close it"), record_as="trap"),
        Step("p_result", "prediction", "Predict the result",
             "PMV-101 is the barrier under test. What do you expect?",
             options=[Option("a", "PASS - no significant build-up in the cavity"), Option("b", "FAIL - the cavity pressure builds up")],
             correct=_p_result, explanation=_p_result_explain),
        Step("t_test", "task", "6 - Run the inflow test",
             "Integrity tests page: start an INFLOW test, test volume 'Tree cavity' (PT-104), barrier PMV-101. Wait for the result.",
             condition=_done, condition_hint=_test_hint, record_as="test"),
        Step("r_test", "review", "Review: the barrier test", review=_review),
        Step("q_next", "question", "After a failed test",
             "PMV-101 failed its inflow test. What is the right next step?",
             options=[Option("a", "Record it, repeat the test to confirm, and do not count PMV-101 as a barrier until it is repaired"),
                      Option("b", "Ignore it - the leak is small"), Option("c", "Open the valve faster next time")],
             correct="a", explanation="A barrier that fails its test no longer counts as a barrier: confirm, report, and plan the "
                                      "repair; operations continue only with the remaining verified barriers."),
        Step("q_bleed", "question", "Why bleed first?",
             "Why was the cavity bled down before the test?",
             options=[Option("a", "To put a differential across PMV-101 in the direction it must seal"),
                      Option("b", "To cool the valve"), Option("c", "Bleeding is not needed")],
             correct="a", explanation="Without a differential there is nothing to drive a leak, and the test proves nothing."),
        Step("summary", "summary", "Performance summary"),
    ],
)
