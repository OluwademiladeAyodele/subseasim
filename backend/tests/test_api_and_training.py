import pytest
from fastapi.testclient import TestClient

from app.core import units as u
from app.main import app
from app.scenarios.loader import get_scenario
from app.sessions import Session
from app.simulation.engine import SimulationEngine
from app.training.exercises.ex03_choke import REQUIRED_TAGS
from app.training.framework import TrainingError, TrainingSession
from app.training.registry import get_exercise


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _new(client, scenario="base_single_phase"):
    r = client.post("/api/sessions", json={"scenario_id": scenario})
    assert r.status_code == 201
    return r.json()["session_id"]


def test_health_and_scenarios(client):
    assert client.get("/api/health").json()["simulated"] is True
    ids = {s["id"] for s in client.get("/api/scenarios").json()}
    assert {"base_single_phase", "ex03_choke_operation"} <= ids
    assert client.get("/api/scenarios/nope").status_code == 404


def test_session_valve_and_boundary_flow(client):
    sid = _new(client)
    st = client.get(f"/api/sessions/{sid}").json()["state"]
    q0 = st["hydraulics"]["q_m3s"]
    r = client.post(f"/api/sessions/{sid}/valves/CHK-101", json={"command": "set_position", "position_pct": 60})
    assert r.status_code == 200
    chk = next(e for e in r.json()["state"]["elements"] if e.get("tag") == "CHK-101")
    assert chk["commanded_pct"] == 60 and chk["position_pct"] == 30  # not running yet
    r = client.put(f"/api/sessions/{sid}/boundary", json={"reservoir_pressure_pa": u.bara_to_pa(400)})
    assert r.json()["state"]["hydraulics"]["q_m3s"] > q0


def test_invalid_inputs(client):
    sid = _new(client)
    assert client.post(f"/api/sessions/{sid}/valves/PMV-101", json={"command": "set_position", "position_pct": 50}).status_code == 409
    assert client.post(f"/api/sessions/{sid}/valves/CHK-101", json={"command": "set_position", "position_pct": 150}).status_code == 422
    assert client.post(f"/api/sessions/{sid}/valves/NOPE", json={"command": "open"}).status_code == 404
    assert client.put(f"/api/sessions/{sid}/boundary", json={"reservoir_pressure_pa": -5}).status_code == 422
    assert client.put(f"/api/sessions/{sid}/boundary", json={"bogus": 1}).status_code == 422
    assert client.put(f"/api/sessions/{sid}/fluid", json={"density_kg_m3": 5}).status_code == 422
    assert client.post(f"/api/sessions/{sid}/lifecycle", json={"action": "pause"}).status_code == 409
    assert client.post(f"/api/sessions/{sid}/speed", json={"time_scale": 3}).status_code == 422
    assert client.get("/api/sessions/unknown").status_code == 404


def test_websocket_init_and_update(client):
    sid = _new(client)
    with client.websocket_connect(f"/ws/sessions/{sid}") as ws:
        init = ws.receive_json()
        assert init["type"] == "init" and "layout" in init["state"] and init["samples"]
        client.post(f"/api/sessions/{sid}/lifecycle", json={"action": "start"})
        upd = ws.receive_json()
        assert upd["type"] == "update" and upd["state"]["status"] == "running"
        assert any(e["message"] == "Simulation started" for e in upd["events"])


def test_sessions_are_isolated(client):
    a, b = _new(client), _new(client)
    client.post(f"/api/sessions/{a}/valves/PWV-101", json={"command": "close"})
    sb = client.get(f"/api/sessions/{b}").json()["state"]
    pwv = next(e for e in sb["elements"] if e.get("tag") == "PWV-101")
    assert pwv["commanded_pct"] == 100


# --------------------------------------------------------------- training
def _drive_choke(session: Session, target: float):
    session.engine.command_valve("CHK-101", "set_position", target)
    for _ in range(400):
        session.engine.advance(1.0)
        session.update_training()
        if session.training.current.id in session.training.completed:
            return
    raise AssertionError("task did not complete")


def test_exercise3_tags_exist_in_its_scenario():
    eng = SimulationEngine(get_scenario(get_exercise("ex03_choke_operation").scenario_id))
    known = set(eng.restrictions) | {i.tag for i in eng.instruments}
    assert set(REQUIRED_TAGS) <= known


def test_exercise3_full_run_uses_simulation_results():
    s = Session("t", SimulationEngine(get_scenario("base_single_phase")))
    s.start_training("ex03_choke_operation")
    tr = s.training
    tr.advance()  # intro
    with pytest.raises(TrainingError):
        tr.advance()  # start task incomplete
    s.engine.start()
    s.update_training()
    tr.advance()
    s.update_training()  # baseline at 20 % is met immediately
    assert "c20" in tr.observations
    tr.advance()
    tr.answer("p1", "b")
    tr.advance()
    _drive_choke(s, 40.0)
    tr.advance()
    review = tr.state()["current"]["review"]
    q20, q40 = tr.observations["c20"]["q_m3d"], tr.observations["c40"]["q_m3d"]
    assert f"{q20:.0f}" in review["text"] and f"{q40:.0f}" in review["text"]
    # budget closes: sum of uses == P_res - P_down
    total_row = review["table"]["rows"][-2]
    assert total_row[1] == pytest.approx(380 - 60, abs=0.01)
    tr.advance()
    tr.answer("p2", "b")
    tr.advance()
    _drive_choke(s, 80.0)
    tr.advance()
    tr.advance()  # review 2
    assert tr.answer("q1", "a")["correct"] is True
    tr.advance()
    assert tr.answer("q2", "c")["correct"] is False
    tr.advance()
    resp = tr.answer("q3", "a")
    # correct answer resolved from data: PT-102 fell between 20 % and 80 %
    assert tr.observations["c80"]["p_uc_bara"] < tr.observations["c20"]["p_uc_bara"]
    assert resp["correct"] is True
    tr.advance()
    st = tr.state()
    assert st["current"]["kind"] == "summary" and st["finished"]
    assert st["score"]["questions_correct"] == 2 and st["score"]["questions_total"] == 3
    assert st["score"]["predictions_resolved"] == 2
    # p2: choke dP fell from 40 -> 80 %
    p2 = next(p for p in st["summary"]["predictions"] if p["step_id"] == "p2")
    assert p2["correct_option"] == "b" and p2["correct"] is True


def test_training_rejects_out_of_sequence_answers():
    tr = TrainingSession(get_exercise("ex03_choke_operation"))
    with pytest.raises(TrainingError):
        tr.answer("q1", "a")


def test_training_api(client):
    sid = _new(client)
    ids = [x["id"] for x in client.get("/api/training/exercises").json()]
    assert ids[0] == "ex01_familiarisation" and "ex03_choke_operation" in ids and len(ids) == 9
    r = client.post(f"/api/sessions/{sid}/training/start", json={"exercise_id": "ex03_choke_operation"})
    assert r.status_code == 200
    body = r.json()
    assert body["state"]["scenario"]["id"] == "ex03_choke_operation"
    assert body["training"]["current"]["id"] == "intro"
    assert client.post(f"/api/sessions/{sid}/training/advance").json()["training"]["current"]["id"] == "start"
    assert client.post(f"/api/sessions/{sid}/training/advance").status_code == 409
    assert client.post(f"/api/sessions/{sid}/training/start", json={"exercise_id": "nope"}).status_code == 404
