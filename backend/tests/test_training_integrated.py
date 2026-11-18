"""Exercise 7 played end to end as an intern would: every stage of the
integrated scenario (§7.1) is completed from the SIMULATION STATE, and the
resolved predictions / reviews are generated from what the run did.
This is also the integrated system test: production, multiphase flow,
MPFM, sanding, transport, erosion and the maintenance
recommendation all run on one shared simulation state."""

from __future__ import annotations

import warnings

import pytest

from app.scenarios.loader import get_scenario
from app.simulation.engine import SimulationEngine
from app.training.exercises.ex07_integrated import C1, C2, EXERCISE
from app.training.framework import TrainingSession

warnings.simplefilter("ignore", RuntimeWarning)


def _run_until(e: SimulationEngine, t: TrainingSession, step_id: str, chunk: float = 30.0, limit: float = 6 * 3600.0, action=None):
    assert t.current.id == step_id, (t.current.id, step_id)
    waited = 0.0
    while not t.update(e):
        if action is not None:
            action()
        e.advance(chunk)
        waited += chunk
        assert waited <= limit, f"{step_id} did not complete: {t.task_hint(e)}"
    t.advance()


@pytest.fixture(scope="module")
def played():
    e = SimulationEngine(get_scenario(EXERCISE.scenario_id))
    t = TrainingSession(EXERCISE)
    assert e.restrictions["PWV-101"].actuator.position_pct == 0  # starts shut in
    t.advance()  # intro
    e.start()
    _run_until(e, t, "t_start")
    e.set_black_oil(water_cut=0.35)
    _run_until(e, t, "t_fluid")
    e.command_valve("PWV-101", "open")
    e.set_time_scale(60.0)
    _run_until(e, t, "t_open")
    t.answer("q_mpfm", "a")
    t.advance()
    t.answer("p_risk", "a")
    t.advance()
    e.command_valve("CHK-101", "set_position", C1)
    _run_until(e, t, "t_c1")
    rev_choke = t.state(e)["current"]["review"]
    t.advance()
    t.answer("p_sand", "a")
    t.advance()
    e.command_valve("CHK-101", "set_position", C2)
    _run_until(e, t, "t_c2")
    rev_sand = t.state(e)["current"]["review"]
    t.advance()
    _run_until(e, t, "t_transport")
    rev_transport = t.state(e)["current"]["review"]
    t.advance()
    rev_erosion = t.state(e)["current"]["review"]
    t.advance()
    _run_until(e, t, "t_ff", action=lambda: e.sand_fast_forward(400))
    t.answer("q_first", "b")
    t.advance()
    _run_until(e, t, "t_inspect", action=lambda: e.sand_fast_forward(180), limit=1e9)
    rev_reco = t.state(e)["current"]["review"]
    t.advance()
    t.answer("q_range", "a")
    t.advance()
    t.answer("q_improve", "a")
    t.advance()
    return e, t, {"choke": rev_choke, "sand": rev_sand, "transport": rev_transport, "erosion": rev_erosion, "reco": rev_reco}


def test_every_stage_completes_from_the_simulation(played):
    e, t, _ = played
    st = t.state(e)
    assert st["current"]["kind"] == "summary" and st["finished"]
    assert all(s["status"] == "complete" for s in st["steps"])
    for key in ("base", "c1", "c2", "transport", "ff1", "insp"):
        assert key in t.observations


def test_production_and_mpfm_stage(played):
    _, t, _ = played
    b = t.observations["base"]
    assert b["rates"]["oil_sm3_d"] > 100 and b["rates"]["gas_sm3_d"] > 0 and b["rates"]["water_sm3_d"] > 0
    assert b["water_cut"] == pytest.approx(0.35)
    assert b["mpfm_quality"] == "GOOD"
    m, tr = b["mpfm_measured"], b["mpfm_true"]
    assert abs(m["oil_sm3_d"] - tr["oil_sm3_d"]) / tr["oil_sm3_d"] < 0.10


def test_sanding_follows_the_choke_and_drawdown(played):
    _, t, rev = played
    b, c1, c2 = t.observations["base"], t.observations["c1"], t.observations["c2"]
    assert b["risk_index"] <= 1.0 and (b["formation_kg_d"] or 0) == 0.0  # 30 %: below onset
    assert c1["risk_index"] > 1.0 and c1["formation_kg_d"] > 0  # 40 %: sanding
    assert c2["drawdown_bar"] > c1["drawdown_bar"] and c2["formation_kg_d"] > c1["formation_kg_d"]
    # the sand grows faster than the drawdown (excess over critical, (r-1)^n)
    assert c2["formation_kg_d"] / c1["formation_kg_d"] > c2["drawdown_bar"] / c1["drawdown_bar"]
    preds = {p["step_id"]: p for p in t.state()["summary"]["predictions"]}
    assert preds["p_risk"]["correct"] is True and preds["p_sand"]["correct"] is True
    assert "risk index" in rev["choke"]["text"] and rev["sand"]["table"]["rows"]


def test_transport_to_the_choke(played):
    _, t, rev = played
    c2, tr = t.observations["c2"], t.observations["transport"]
    assert tr["sim_time_s"] > c2["sim_time_s"]  # the new sand needed transit time
    assert tr["at_choke_kg_d"] == pytest.approx(tr["produced_kg_d"], rel=0.05)
    assert "minutes" in rev["transport"]["text"]
    assert rev["erosion"]["table"]["rows"]


def test_wear_inspection_and_recommendation(played):
    _, t, rev = played
    ff, insp = t.observations["ff1"], t.observations["insp"]
    assert ff["service_days"] >= 365 and ff["first_limit"] is not None
    assert insp["health"] in ("Inspection recommended", "Changeout assessment required", "Critical condition")
    assert insp["service_days"] > ff["service_days"]
    assert insp["recommendation"]["title"] and insp["recommendation"]["reasons"]
    assert "service days" in rev["reco"]["text"] and rev["reco"]["table"]["rows"]
    assert insp["confidence"].startswith("screening")
    q = {x["step_id"]: x for x in t.state()["summary"]["questions"]}
    assert q["q_range"]["correct"] and q["q_improve"]["correct"]
    assert q["q_first"]["correct_option"] in ("a", "b", "c", "d")


def test_exercise_is_listed_and_startable_through_the_api():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        ex = {x["id"]: x for x in client.get("/api/training/exercises").json()}
        assert "ex07_integrated" in ex and ex["ex07_integrated"]["step_count"] == len(EXERCISE.steps)
        sid = client.post("/api/sessions", json={"scenario_id": "xt_230xp22b_multiphase"}).json()["session_id"]
        r = client.post(f"/api/sessions/{sid}/training/start", json={"exercise_id": "ex07_integrated"})
        assert r.status_code == 200
        st = r.json()["state"]
        assert st["scenario"]["id"] == "training_integrated"
        assert st["sand_choke"]["health"]["category"] != "Unavailable"  # example inputs loaded with the scenario
