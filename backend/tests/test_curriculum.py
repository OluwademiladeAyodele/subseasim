"""The intern curriculum: every guided exercise is played to the end as an
intern would operate the workstation, every task completes from the
simulation state, every prediction resolves from the run, and every review
renders from the recorded readings. Also checks the physics each exercise
teaches (directions of the pressure responses)."""

from __future__ import annotations

import warnings

import pytest

from app.scenarios.loader import get_scenario
from app.simulation.engine import SimulationEngine
from app.training.framework import TrainingSession
from app.training.registry import EXERCISES

warnings.simplefilter("ignore", RuntimeWarning)


def _actions(e: SimulationEngine) -> dict:
    v = e.command_valve
    return {
        # Ex 1
        "ex01_familiarisation": {"t_start": e.start, "t_speed": lambda: e.set_time_scale(60.0), "t_sv": lambda: v("SV-101", "open"),
                                 "t_sv0": lambda: v("SV-101", "close")},
        # Ex 2
        "ex02_startup": {"t_start": e.start, "t_scssv": lambda: v("SCSSV-101", "open"), "t_pmv": lambda: v("PMV-101", "open"),
                         "t_pwv": lambda: v("PWV-101", "open"), "t_meoh": lambda: v("CIV-301", "open"),
                         "t_c10": lambda: v("CHK-101", "set_position", 10), "t_c20": lambda: v("CHK-101", "set_position", 20),
                         "t_c30": lambda: v("CHK-101", "set_position", 30), "t_meoh_off": lambda: v("CIV-301", "close")},
        # Ex 4
        "ex04_shutin": {"t_start": e.start, "t_chk": lambda: v("CHK-101", "set_position", 0), "t_pwv": lambda: v("PWV-101", "close"),
                        "t_pmv": lambda: v("PMV-101", "close"), "t_scssv": lambda: v("SCSSV-101", "close"), "t_bu": lambda: None},
        # Ex 5
        "ex05_chemicals": {"t_start": e.start, "t_inj": lambda: v("CIV-301", "open"), "t_arr": lambda: None,
                           "t_meter": lambda: v("CIMV-301", "set_position", 100), "t_ch50": lambda: v("CHK-101", "set_position", 50),
                           "t_stop": lambda: (v("CIV-301", "close"), v("CHK-101", "set_position", 30))},
        # Ex 6
        "ex06_annulus": {"t_start": e.start, "t_amv": lambda: v("AMV-101", "open"), "t_bleed": lambda: v("AWV-101", "open"),
                         "t_close": lambda: (v("AWV-101", "close"), v("AMV-101", "close")), "t_after": lambda: None},
        # Ex 8
        "ex08_leaktest": {"t_start": e.start, "t_stop": lambda: v("CHK-101", "set_position", 0), "t_pmv": lambda: v("PMV-101", "close"),
                          "t_bleed": lambda: v("CHK-101", "set_position", 20),
                          "t_trap": lambda: (v("PWV-101", "close"), v("CHK-101", "set_position", 0)),
                          "t_test": lambda: e.start_integrity_test(type="inflow", test_node="N_PMV_PWV", transmitter="PT-104",
                                                                   valve="PMV-101")},
        # Ex 9
        "ex09_hydraulics": {"t_start": e.start, "t_one": lambda: e.command_selector("HSV-101", "close"),
                            "t_restore1": lambda: e.command_selector("HSV-101", "open"),
                            "t_trip": lambda: e.set_hydraulic_supply("LP", False), "t_lp": lambda: e.set_hydraulic_supply("LP", True),
                            "t_back": lambda: (v("PMV-101", "open"), v("PWV-101", "open"))},
    }


def play(exercise_id: str, chunk: float = 30.0, limit_s: float = 6 * 3600.0):
    ex = EXERCISES[exercise_id]
    e = SimulationEngine(get_scenario(ex.scenario_id))
    t = TrainingSession(ex)
    acts = _actions(e)[exercise_id]
    reviews = {}
    while t.current.kind != "summary":
        s = t.current
        if s.kind == "task":
            acts[s.id]()
            waited = 0.0
            while not t.update(e):
                e.advance(chunk)
                waited += chunk
                assert waited <= limit_s, f"{exercise_id}/{s.id} never completed: {s.condition_hint(e) if s.condition_hint else ''}"
        elif s.kind in ("question", "prediction"):
            t.answer(s.id, s.options[0].id)
        elif s.kind == "review":
            reviews[s.id] = t.state(e)["current"]["review"]
        t.advance()
    return e, t, reviews


NEW = ["ex01_familiarisation", "ex02_startup", "ex04_shutin", "ex05_chemicals", "ex06_annulus", "ex08_leaktest", "ex09_hydraulics"]


@pytest.fixture(scope="module")
def runs():
    return {x: play(x) for x in NEW}


def test_the_curriculum_has_nine_numbered_exercises_on_the_tree_workstation():
    nums = sorted(x.number for x in EXERCISES.values())
    assert nums == list(range(1, 10))
    for x in EXERCISES.values():
        e = SimulationEngine(get_scenario(x.scenario_id))
        assert e.snapshot(True).get("schematic"), f"{x.id} does not run on the tree workstation"
        assert x.objectives and x.steps[-1].kind == "summary"


@pytest.mark.parametrize("exercise_id", NEW)
def test_every_exercise_completes_with_resolved_predictions_and_rendered_reviews(runs, exercise_id):
    e, t, reviews = runs[exercise_id]
    st = t.state(e)
    assert st["finished"] and all(s["status"] == "complete" for s in st["steps"])
    for p in st["summary"]["predictions"]:
        assert p["correct"] is not None, f"{exercise_id}: prediction {p['step_id']} unresolved"
    for q in st["summary"]["questions"]:
        assert q["correct_option"] is not None, f"{exercise_id}: question {q['step_id']} unresolved"
    for rid, r in reviews.items():
        assert r["text"] and "n/a" not in r["text"], f"{exercise_id}/{rid}: {r['text'][:200]}"


# ------------------------------------------------------- the physics taught
def test_startup_pressures(runs):
    _, t, _ = runs["ex02_startup"]
    o = t.observations
    assert abs(o["pmv"]["PT-104"] - o["pmv"]["PT-101"]) < 2  # cavity equalised with the bore
    assert o["pwv"]["PDT-101"] > 50  # the closed choke holds the differential
    assert o["c10"]["FT-101"] > 0 and o["c10"]["PT-102"] < o["pwv"]["PT-102"]  # flow starts, wellhead pressure falls
    assert o["c30"]["FT-101"] > o["c20"]["FT-101"] > o["c10"]["FT-101"]
    assert o["c30"]["PT-001"] < o["c10"]["PT-001"]  # more drawdown
    assert o["meoh"]["FT-301"] > 0


def test_shutin_pressures(runs):
    _, t, _ = runs["ex04_shutin"]
    o = t.observations
    assert o["chk0"]["FT-101"] < 5 and o["chk0"]["PT-102"] > o["flow"]["PT-102"] and o["chk0"]["PT-103"] < o["flow"]["PT-103"]
    assert o["bu"]["PT-001"] > o["scssv0"]["PT-001"] > o["flow"]["PT-001"]  # build-up
    assert o["pmv0"]["PT-104"] > o["pmv0"]["PT-103"] + 20  # trapped cavity pressure


def test_chemical_transport_and_rate(runs):
    _, t, _ = runs["ex05_chemicals"]
    o = t.observations
    assert o["arr"]["sim_time_s"] - o["inj"]["sim_time_s"] > 300  # transport delay to 2.5 km
    assert o["meter"]["FT-301"] > o["arr"]["FT-301"]  # metering valve opened
    assert o["ch50"]["FT-301"] > o["meter"]["FT-301"] and o["ch50"]["PT-104"] < o["meter"]["PT-104"]  # lower tree pressure


def test_annulus_bleed(runs):
    _, t, _ = runs["ex06_annulus"]
    o = t.observations
    assert abs(o["amv"]["PT-402"] - o["amv"]["PT-401"]) < 2
    assert abs(o["bleed"]["PT-401"] - o["bleed"]["PT-404"]) < 3 and o["bleed"]["PT-401"] < o["base"]["PT-401"] - 20


def test_leaking_pmv_fails_its_inflow_test(runs):
    _, t, _ = runs["ex08_leaktest"]
    assert t.observations["test"]["test"]["phase"] == "failed"
    assert t.observations["test"]["test"]["result"]["change_bar"] > t.observations["test"]["test"]["max_change_bar"]


def test_tight_pmv_passes_the_same_test():
    from app.training.exercises import ex08_leaktest as m

    orig = m.EXERCISE.scenario_id
    m.EXERCISE.scenario_id = "xt_230xp22b"
    try:
        _, t, _ = play("ex08_leaktest")
    finally:
        m.EXERCISE.scenario_id = orig
    assert t.observations["test"]["test"]["phase"] == "passed"


def test_hydraulics_fail_safe(runs):
    _, t, _ = runs["ex09_hydraulics"]
    o = t.observations
    assert o["one"]["valves"]["PMV-101"] == 100 and o["one"]["valves"]["PWV-101"] == 100  # A/B redundancy
    tr = o["trip"]["valves"]
    assert tr["PMV-101"] == 0 and tr["PWV-101"] == 0 and tr["SCSSV-101"] == 100
    assert tr["CHK-101"] == pytest.approx(o["base"]["valves"]["CHK-101"])  # choke fails as-is
    assert o["back"]["FT-101"] > 100
