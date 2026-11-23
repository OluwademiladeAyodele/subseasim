"""Exercise 9 - Control hydraulics and loss of supply.

The trainee checks the A/B redundancy of the LP selector valves, trips the
LP hydraulic supply, watches the fail-safe valves close and production stop,
then restores the supply and brings the well back.
"""

from __future__ import annotations

from app.training.exercises.common import Held, capture as base_capture, fmt, is_closed, is_open, running, table, travel_hint
from app.training.framework import ExerciseDefinition, Obs, Option, Step


def capture(e) -> dict:
    out = base_capture(e)
    c = e.ctrl
    out["headers_bara"] = {h.id: h.p / 1e5 for h in c.headers.values()} if c else {}
    out["selectors"] = {s.tag: s.opening for s in c.selectors.values()} if c else {}
    return out


def _sel_closed(e, tag) -> bool:
    s = e.ctrl.selectors[tag]
    return s.opening <= 1e-6 and s.commanded == 0.0


def _sel_open(e, tag) -> bool:
    s = e.ctrl.selectors[tag]
    return s.opening >= 1 - 1e-6 and s.commanded == 1.0


_one = Held(lambda e: _sel_closed(e, "HSV-101"), 900)
_restore1 = Held(lambda e: _sel_open(e, "HSV-101"), 60)


def _tripped(e) -> bool:
    return running(e) and not e.ctrl.supplies["LP"].available and is_closed(e, "PMV-101") and is_closed(e, "PWV-101")


_lp_back = Held(lambda e: e.ctrl.supplies["LP"].available and e.ctrl.supply_ok("LP"), 60)


def _back(e) -> bool:
    r = e.readings.get("FT-101")
    return running(e) and is_open(e, "PMV-101") and is_open(e, "PWV-101") and r is not None and r.value is not None and r.value * 86400 > 100


def _p_one(obs: Obs) -> str | None:
    if "one" not in obs:
        return None
    v = obs["one"]["valves"]
    return "a" if v["PMV-101"] >= 99.9 and v["PWV-101"] >= 99.9 else "b"


def _p_one_explain(obs: Obs) -> str:
    h = obs["one"]["headers_bara"]
    return (f"With HSV-101 closed, the LP header of SCM A bled down to {fmt(h.get('LP-A'), 0)} bara, but SCM B's header stayed at "
            f"{fmt(h.get('LP-B'), 0)} bara. A valve actuator is powered by the HIGHER of the two headers, so PMV-101 and PWV-101 stayed "
            "open: the A/B redundancy works.")


def _p_trip(obs: Obs) -> str | None:
    if "trip" not in obs or "base" not in obs:
        return None
    v, b = obs["trip"]["valves"], obs["base"]["valves"]
    closed_ok = v["PMV-101"] <= 0.1 and v["PWV-101"] <= 0.1
    if not closed_ok:
        return None
    return "a" if v["SCSSV-101"] >= 99.9 and abs(v["CHK-101"] - b["CHK-101"]) < 0.5 else "b"


def _p_trip_explain(obs: Obs) -> str:
    v = obs["trip"]["valves"]
    return (f"After the LP trip PMV-101 and PWV-101 closed on their springs (fail-safe close); the choke stayed at {fmt(v['CHK-101'], 0)} % "
            f"(a stepping actuator fails as-is) and SCSSV-101 stayed at {fmt(v['SCSSV-101'], 0)} % because it runs on the HP supply. "
            f"Production stopped: FT-101 {fmt(obs['trip']['FT-101'], 0)} m3/d.")


def _review(obs: Obs, preds: dict) -> dict:
    v = preds.get("p_trip")
    lead = f"Your prediction: '{v['choice_text']}'. Result: '{v['correct_text']}'. " if v and v["correct"] is not None else ""
    text = (lead + _p_trip_explain(obs) + " A loss of hydraulic supply makes the tree go to its SAFE state by itself - that is the point "
            "of fail-safe-close actuators. Valves cannot be re-opened until the supply is back above its operating minimum.")
    t = table(obs, [("base", "Normal"), ("one", "HSV-101 closed"), ("trip", "LP supply tripped"), ("back", "Restored, re-opened")],
              [("valves.PMV-101", "PMV %", 0), ("valves.PWV-101", "PWV %", 0), ("valves.CHK-101", "Choke %", 0),
               ("valves.SCSSV-101", "SCSSV %", 0), ("FT-101", "FT-101 m3/d", 0)])
    return {"text": text, "table": t}


EXERCISE = ExerciseDefinition(
    id="ex09_hydraulics",
    number=9,
    title="Exercise 9 - Control hydraulics and loss of supply",
    scenario_id="xt_230xp22b",
    objectives=[
        "Explain how LP and HP hydraulic supplies reach the valve actuators through selector valves and SCM A / B headers.",
        "Check the A / B redundancy with one selector valve closed.",
        "Observe the fail-safe response to a loss of LP supply, then restore it and bring the well back on line.",
    ],
    initial_configuration=["Tree workstation, single-phase producer flowing at CHK-101 30 %.",
                           "LP (207 bara) and HP (517 bara) supplies available; all selector valves open."],
    instructions=["Click a selector valve or hydraulic panel on the tree to open the hydraulics panel (selector commands, HPU trip / "
                  "restore).", "Use 60x while waiting for headers to bleed down."],
    expected_observations=["One closed selector valve does not affect the valves (redundancy).",
                           "An LP trip closes PMV and PWV; the choke fails as-is; the SCSSV (HP) stays open."],
    capture=capture,
    steps=[
        Step("intro", "info", "1 - Hydraulics on a subsea tree",
             "The tree valves are opened hydraulically and closed by springs. The host's hydraulic power unit (HPU) sends an LP supply "
             "(tree valves, choke, injection valves) and an HP supply (the SCSSV) down the umbilical. Selector valves HSV-101 to "
             "HSV-104 route each supply to two subsea control modules, SCM A and SCM B, so one failure does not shut the well."),
        Step("t_start", "task", "Start the simulation", "Press START.",
             condition=running, condition_hint=lambda e: "Press START in the top bar.", record_as="base"),
        Step("p_one", "prediction", "Predict: close one selector valve",
             "You will close HSV-101 (LP to SCM A) only. What happens to PMV-101 and PWV-101?",
             options=[Option("a", "They stay open: SCM B still supplies LP"), Option("b", "They close")],
             correct=_p_one, explanation=_p_one_explain),
        Step("t_one", "task", "2 - Close HSV-101",
             "Click HSV-101 on the tree and close it. Watch the SCM A LP header (PT-611) bleed down for 15 minutes.",
             condition=_one, condition_hint=lambda e: "Close HSV-101 from the hydraulics panel." if not _sel_closed(e, "HSV-101")
             else f"Hold ({_one.remaining(e):.0f} s left).", record_as="one"),
        Step("t_restore1", "task", "Re-open HSV-101", "Open HSV-101 again.",
             condition=_restore1, condition_hint=lambda e: "Open HSV-101 from the hydraulics panel.", record_as="restore1"),
        Step("p_trip", "prediction", "Predict: lose the LP supply",
             "Now the HPU trips and the LP supply is lost. Which valves close?",
             options=[Option("a", "PMV and PWV (and the other LP fail-safe valves); the choke stays where it is; the SCSSV stays open"),
                      Option("b", "Every valve, including the SCSSV and the choke"), Option("c", "None")],
             correct=_p_trip, explanation=_p_trip_explain),
        Step("t_trip", "task", "3 - Trip the LP supply",
             "In the hydraulics panel press 'LP supply trip' and watch the headers bleed down and the valves close.",
             condition=_tripped, condition_hint=lambda e: "Press 'LP supply trip' in the hydraulics panel." if e.ctrl.supplies["LP"].available
             else "LP lost - the headers are bleeding down; PMV-101 and PWV-101 close when they fall below 110 bara.", record_as="trip"),
        Step("q_open", "question", "Re-opening",
             "While the LP supply is lost, can PWV-101 be opened from the workstation?",
             options=[Option("a", "No - there is no hydraulic pressure to open it"), Option("b", "Yes, normally")],
             correct="a", explanation="Opening commands are rejected while the supply is below its operating minimum; closing is always possible."),
        Step("t_lp", "task", "4 - Restore the LP supply",
             "Press 'LP supply restore' and wait for the headers to recharge.",
             condition=_lp_back, condition_hint=lambda e: "Press 'LP supply restore' in the hydraulics panel." if not e.ctrl.supplies["LP"].available
             else f"Recharging ({_lp_back.remaining(e):.0f} s).", record_as="lp"),
        Step("t_back", "task", "5 - Bring the well back",
             "Open PMV-101, then PWV-101 (the choke is still at its old position). The task completes when the well flows again.",
             condition=_back, condition_hint=lambda e: travel_hint(e, "PMV-101", 100, "open it") if not is_open(e, "PMV-101")
             else travel_hint(e, "PWV-101", 100, "open it"), record_as="back"),
        Step("r_trip", "review", "Review: fail-safe behaviour", review=_review),
        Step("q_hp", "question", "The SCSSV",
             "Which supply holds the SCSSV open?",
             options=[Option("a", "HP"), Option("b", "LP"), Option("c", "It needs no supply")],
             correct="a", explanation="The SCSSV sits deep in the well and needs the high-pressure supply to overcome the well pressure "
                                      "and its spring; losing HP closes it."),
        Step("summary", "summary", "Performance summary"),
    ],
)
