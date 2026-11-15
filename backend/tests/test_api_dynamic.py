"""API tests for the dynamic-model endpoints (mode, chemical pumps, integrity)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.sessions import manager


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
    manager.sessions.clear()


def _new(client, scenario="subsea_dynamic_base"):
    r = client.post("/api/sessions", json={"scenario_id": scenario})
    assert r.status_code == 201
    return r.json()["session_id"], r.json()["state"]


def test_dynamic_snapshot_contents(client):
    sid, s = _new(client)
    assert s["mode"] == "dynamic"
    assert s["clock"]["fixed_step"] is True and 600.0 in s["clock"]["allowed_speeds"]
    assert {c["id"] for c in s["chemicals"]} == {"methanol", "corrosion_inhibitor", "biocide", "wax_inhibitor"}
    assert s["steady_reference"]["q_m3s"] > 0
    fl = next(e for e in s["elements"] if e["id"] == "FL-101")
    assert fl["wave_speed_m_s"] > 500 and fl["residence_time_s"] > 0 and "profile" in fl
    assert any(i["type"] == "concentration" for i in s["instruments"])
    assert s["integrity_presets"]


def test_mode_switch_endpoint(client):
    sid, _ = _new(client)
    r = client.post(f"/api/sessions/{sid}/mode", json={"mode": "steady"})
    assert r.status_code == 200 and r.json()["state"]["mode"] == "steady"
    pt = next(i for i in r.json()["state"]["instruments"] if i["tag"] == "PT-401")
    assert pt["status"] == "NOT_MODELLED"
    r = client.post(f"/api/sessions/{sid}/mode", json={"mode": "dynamic"})
    assert r.json()["state"]["mode"] == "dynamic"
    assert client.post(f"/api/sessions/{sid}/mode", json={"mode": "fast"}).status_code == 422


def test_pump_endpoint(client):
    sid, _ = _new(client)
    r = client.post(f"/api/sessions/{sid}/chemicals/methanol", json={"running": False})
    c = next(c for c in r.json()["state"]["chemicals"] if c["id"] == "methanol")
    assert c["pump_running"] is False and c["supply_pressure_pa"] == c["static_pressure_pa"]
    r = client.post(f"/api/sessions/{sid}/chemicals/methanol", json={"discharge_pressure_pa": 5e8})
    assert r.status_code == 422
    r = client.post(f"/api/sessions/{sid}/chemicals/methanol", json={"discharge_pressure_pa": 9e8})
    assert r.status_code == 422  # schema limit
    assert client.post(f"/api/sessions/{sid}/chemicals/nope", json={"running": True}).status_code == 409


def test_integrity_endpoints(client):
    sid, _ = _new(client)
    r = client.post(f"/api/sessions/{sid}/integrity/tests", json={"type": "pressure_hold", "transmitter": "PT-104"})
    assert r.status_code == 409 and "isolation NOT verified" in r.json()["detail"]
    r = client.post(f"/api/sessions/{sid}/integrity/tests", json={"type": "stroke", "valve": "PWV-101"})
    assert r.status_code == 200
    t = r.json()["state"]["integrity"]["tests"][-1]
    assert t["phase"] == "stroking"
    r = client.post(f"/api/sessions/{sid}/integrity/tests/{t['id']}/abort")
    assert r.status_code == 200
    assert r.json()["state"]["integrity"]["tests"][-1]["phase"] == "aborted"


def test_speed_600_allowed(client):
    sid, _ = _new(client)
    assert client.post(f"/api/sessions/{sid}/speed", json={"time_scale": 600}).status_code == 200


def test_full_server_evicts_unwatched_session_instead_of_refusing():
    from app.core.config import Settings
    from app.sessions import SessionLimitReached, SessionManager

    m = SessionManager(Settings(max_sessions=3))
    first = m.create("base_single_phase")
    m.create("base_single_phase")
    m.create("base_single_phase")
    newest = m.create("base_single_phase")  # full: LRU unwatched session is reclaimed
    assert len(m.sessions) == 3 and first.id not in m.sessions and newest.id in m.sessions
    for s in m.sessions.values():
        s.sockets.add(object())  # every remaining session is being watched
    with pytest.raises(SessionLimitReached, match="capacity"):
        m.create("base_single_phase")
