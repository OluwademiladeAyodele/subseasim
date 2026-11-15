"""Smoke test: every user-facing function on every scenario in both models.

Guards against the failure mode "the simulation silently stops responding":
an exception inside the simulation tick, a non-JSON-serialisable snapshot
(NaN/Infinity breaks the browser's JSON.parse), or a command that is
accepted but has no effect.
"""

from __future__ import annotations

import json
import math

import pytest

from app.core import units as u
from app.scenarios.loader import list_scenarios
from app.simulation.components.elements import CommandRejected
from app.simulation.engine import SimulationEngine

SCENARIOS = [s.id for s in list_scenarios()]


def _json_ok(obj) -> None:
    # Browsers reject NaN / Infinity in JSON: the snapshot must be strict JSON.
    json.dumps(obj, allow_nan=False)


def _all_finite_positions(e: SimulationEngine) -> None:
    for r in e.restrictions.values():
        assert math.isfinite(r.actuator.position_pct)


@pytest.mark.parametrize("scenario", SCENARIOS)
@pytest.mark.parametrize("mode", ["dynamic", "steady"])
def test_every_valve_responds_and_snapshots_stay_valid(scenario, mode):
    e = SimulationEngine(next(s for s in list_scenarios() if s.id == scenario), mode=mode)
    _json_ok(e.snapshot())
    e.start()
    e.set_time_scale(600.0)
    e.advance(5.0)
    for tag, r in list(e.restrictions.items()):
        if not r.available:
            continue
        a = r.actuator
        start = a.position_pct
        target_cmd = "close" if start > 50 else "open"
        e.command_valve(tag, target_cmd)
        e.advance(a.time_to_target() + 2.0)
        assert a.position_pct != start or a.commanded_pct == start, f"{tag} did not move"
        _json_ok(e.snapshot(include_static=False))
        if r.supports_intermediate:
            e.command_valve(tag, "set_position", 37.5)
            e.advance(a.time_to_target() + 2.0)
            assert a.position_pct == pytest.approx(37.5)
        # restore
        e.command_valve(tag, "open" if start >= 50 else "close")
        e.advance(a.time_to_target() + 2.0)
        _all_finite_positions(e)
    e.advance(1800.0)
    snap = e.snapshot()
    _json_ok(snap)
    assert snap["status"] == "running", f"simulation stopped: {[ev.message for ev in e.events.all()[-3:]]}"


@pytest.mark.parametrize("scenario", [s for s in SCENARIOS if s.startswith(("dyn_", "subsea"))])
def test_chemicals_integrity_conditions_and_lifecycle(scenario):
    e = SimulationEngine(next(s for s in list_scenarios() if s.id == scenario))
    e.start()
    # chemical pumps: stop/start/setpoint, open every isolation valve
    for c in e.dyn.circuits:
        e.set_pump(c.cfg.id, running=False)
        e.set_pump(c.cfg.id, running=True, discharge_pressure_pa=c.p_discharge + 10e5)
        e.command_valve(c.cfg.isolation_valve, "open")
    e.advance(600.0)
    assert any(c.status == "injecting" for c in e.dyn.circuits)
    _json_ok(e.snapshot())
    # every integrity preset: either starts or is rejected with a clear reason
    for p in e.scenario.integrity_tests:
        try:
            e.start_integrity_test(type=p.type, name=p.name, test_node=p.test_node, transmitter=p.pressure_transmitter, valve=p.valve,
                                   stabilisation_s=60, duration_s=120, max_change_bar=p.max_change_bar,
                                   stroke_tolerance_pct=p.stroke_tolerance_pct)
        except CommandRejected as exc:
            assert str(exc)
            continue
        e.advance(400.0)
        assert e.integrity.tests[-1].phase in ("passed", "failed", "aborted")
        _json_ok(e.snapshot(include_static=False))
    # boundary / fluid changes
    e.set_boundary(reservoir_pressure_pa=u.bara_to_pa(400), downstream_pressure_pa=u.bara_to_pa(70),
                   reservoir_temperature_k=u.c_to_k(90), productivity_index_si=u.pi_m3d_per_bar_to_si(15))
    e.set_fluid(density=870, viscosity=6e-3)
    e.advance(900.0)
    _json_ok(e.snapshot())
    assert e.status == "running"
    # lifecycle + mode switch
    e.pause()
    t = e.time_s
    e.advance(100)
    assert e.time_s == t
    e.resume()
    e.set_mode("steady")
    e.start()
    e.command_valve("CHK-101", "set_position", 45)
    e.advance(300)
    assert e.restrictions["CHK-101"].actuator.position_pct == pytest.approx(45)
    e.set_mode("dynamic")
    e.reset()
    assert e.status == "ready" and e.time_s == 0
    _json_ok(e.snapshot())


def test_api_session_end_to_end_with_websocket():
    """REST commands + WebSocket stream through the real ASGI app."""
    from fastapi.testclient import TestClient

    from app.main import app
    from app.sessions import manager

    with TestClient(app) as c:
        sid = c.post("/api/sessions", json={"scenario_id": "subsea_dynamic_base"}).json()["session_id"]
        with c.websocket_connect(f"/ws/sessions/{sid}") as ws:
            init = ws.receive_json()
            assert init["type"] == "init" and init["state"]["layout"]
            assert c.post(f"/api/sessions/{sid}/lifecycle", json={"action": "start"}).status_code == 200
            r = c.post(f"/api/sessions/{sid}/valves/PWV-101", json={"command": "close"})
            assert r.status_code == 200
            msg = ws.receive_json()  # broadcast after the command
            assert msg["type"] == "update"
            s = manager.sessions[sid]
            s.engine.advance(40.0)
            v = next(e for e in c.get(f"/api/sessions/{sid}").json()["state"]["elements"] if e.get("tag") == "PWV-101")
            assert v["position_pct"] == 0.0
            # unknown session -> clear 404 (frontend recovers from it)
            assert c.post("/api/sessions/nope/valves/PWV-101", json={"command": "open"}).status_code == 404
        manager.sessions.clear()
