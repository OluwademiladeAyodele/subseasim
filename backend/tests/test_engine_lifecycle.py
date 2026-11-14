import pytest

from app.scenarios.loader import get_scenario
from app.simulation.components.elements import CommandRejected
from app.simulation.engine import InvalidOperatingInput, SimulationEngine


def test_lifecycle_transitions(engine):
    assert engine.status == "ready"
    with pytest.raises(CommandRejected):
        engine.pause()
    engine.start()
    with pytest.raises(CommandRejected):
        engine.start()
    engine.pause()
    engine.resume()
    engine.advance(10.0)
    assert engine.time_s == pytest.approx(10.0)
    engine.reset()
    assert engine.status == "ready" and engine.time_s == 0.0
    cats = [e.category for e in engine.events.all()]
    assert "lifecycle" in cats


def test_time_does_not_advance_unless_running(engine):
    engine.advance(100.0)
    assert engine.time_s == 0.0


def test_result_independent_of_tick_partitioning():
    """Simulation time, not call frequency, determines the result."""
    a = SimulationEngine(get_scenario("base_single_phase"))
    b = SimulationEngine(get_scenario("base_single_phase"))
    for e in (a, b):
        e.start()
        e.command_valve("PWV-101", "close")
    a.advance(600.0)
    for _ in range(600):
        b.advance(1.0)
    assert a.time_s == pytest.approx(b.time_s)
    assert a.hyd.q == b.hyd.q == 0.0
    ta, tb = a.thermal.node_temperature["N_ARR"], b.thermal.node_temperature["N_ARR"]
    assert ta == pytest.approx(tb, abs=0.05)  # implicit Euler, different step sizes


def test_outcome_event_after_valve_travel(engine):
    engine.start()
    engine.command_valve("PWV-101", "close")
    engine.advance(5.0)
    assert not any(e.category == "outcome" for e in engine.events.all())
    engine.advance(40.0)
    outcomes = [e for e in engine.events.all() if e.category == "outcome"]
    assert len(outcomes) == 1
    assert "-> 0 m3/d" in outcomes[0].message


def test_training_rule_warning_on_opening_against_differential(engine):
    engine.start()
    engine.command_valve("PWV-101", "close")
    engine.advance(60.0)
    engine.command_valve("PWV-101", "open")
    warnings = [e for e in engine.events.all() if e.category == "training_rule"]
    assert warnings and "TRAINING RULE" in warnings[-1].message


def test_history_samples_come_from_engine(engine):
    engine.start()
    engine.advance(5.0)
    samples = engine.history.all()
    assert samples[-1]["inst:FT-101"] == engine.readings["FT-101"].value
    assert samples[-1]["pos:CHK-101"] == engine.restrictions["CHK-101"].actuator.position_pct
    assert all(s["t"] <= engine.time_s for s in samples)


def test_invalid_boundary_rejected(engine):
    with pytest.raises(InvalidOperatingInput):
        engine.set_boundary(reservoir_pressure_pa=-1.0)
    with pytest.raises(InvalidOperatingInput):
        engine.set_boundary(productivity_index_si=0.0)


def test_time_scale_validation(engine):
    engine.set_time_scale(10.0)
    with pytest.raises(CommandRejected):
        engine.set_time_scale(7.0)


def test_snapshot_is_complete(engine):
    s = engine.snapshot()
    assert s["hydraulics"]["status"] == "solved"
    assert {n["id"] for n in s["nodes"]} == set(engine.topology.node_order)
    chk = next(e for e in s["elements"] if e.get("tag") == "CHK-101")
    assert chk["supported_commands"] == ["open", "close", "set_position"]
    pmv = next(e for e in s["elements"] if e.get("tag") == "PMV-101")
    assert pmv["supported_commands"] == ["open", "close"]
    assert "layout" in s and "layout" not in engine.snapshot(include_static=False)
