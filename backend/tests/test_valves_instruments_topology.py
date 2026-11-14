import math

import pytest

from app.core import units as u
from app.scenarios.loader import get_scenario, list_scenarios
from app.simulation.build import build_system
from app.simulation.components.elements import CommandRejected, InflowElement
from app.simulation.engine import SimulationEngine
from app.simulation.inflow.ipr import LinearIPR
from app.simulation.instruments.instruments import Instrument, measure
from app.simulation.topology.topology import Node, SeriesTopology, TopologyError
from app.simulation.valves.actuator import Actuator


# ------------------------------------------------------------- actuator
def test_actuator_travel_rate():
    a = Actuator(100.0, 100.0, 30.0)
    a.commanded_pct = 0.0
    a.step(15.0)
    assert a.position_pct == pytest.approx(50.0) and a.is_moving
    assert a.time_to_target() == pytest.approx(15.0)
    a.step(100.0)
    assert a.position_pct == 0.0 and not a.is_moving
    with pytest.raises(ValueError):
        Actuator(0, 0, 0)


# -------------------------------------------------------------- commands
def test_isolation_valve_rejects_intermediate_position(engine):
    with pytest.raises(CommandRejected):
        engine.command_valve("PMV-101", "set_position", 50.0)
    assert engine.events.all()[-1].category == "rejected"


def test_choke_accepts_intermediate_and_validates_range(engine):
    engine.command_valve("CHK-101", "set_position", 45.0)
    assert engine.restrictions["CHK-101"].actuator.commanded_pct == 45.0
    with pytest.raises(CommandRejected):
        engine.command_valve("CHK-101", "set_position", 120.0)
    with pytest.raises(CommandRejected):
        engine.command_valve("CHK-101", "set_position", None)


def test_unknown_tag_and_unavailable_valve():
    with pytest.raises(CommandRejected):
        SimulationEngine(get_scenario("base_single_phase")).command_valve("XV-999", "open")
    cfg = get_scenario("base_single_phase")
    for e in cfg.elements:
        if e.id == "PWV":
            e.available = False
    eng = SimulationEngine(cfg)
    assert eng.restrictions["PWV-101"].supported_commands() == []
    with pytest.raises(CommandRejected):
        eng.command_valve("PWV-101", "close")


def test_commanded_vs_actual_position_and_travel(engine):
    engine.start()
    engine.command_valve("PWV-101", "close")
    a = engine.restrictions["PWV-101"].actuator
    assert a.commanded_pct == 0.0 and a.position_pct == 100.0
    q0 = engine.hyd.q
    engine.advance(15.0)
    assert a.position_pct == pytest.approx(50.0)
    assert 0 < engine.hyd.q <= q0  # partially stroked gate valve still passes flow
    engine.advance(20.0)
    assert a.position_pct == 0.0 and engine.hyd.q == 0.0


def test_valve_does_not_move_while_paused(engine):
    engine.start()
    engine.pause()
    engine.command_valve("PWV-101", "close")
    engine.advance(100.0)
    assert engine.restrictions["PWV-101"].actuator.position_pct == 100.0
    assert engine.time_s == 0.0


# ----------------------------------------------------------- instruments
def _inst(kind="pressure", lo=0.0, hi=1e7):
    return Instrument("PT-X", kind, "x", "A", None, None, lo, hi)


def test_ideal_measurement_and_range_clamp():
    r = measure(_inst(), True, {"A": 5e6}, {}, 0.0)
    assert r.value == r.pv == 5e6 and r.status == "GOOD"
    r = measure(_inst(hi=1e6), True, {"A": 5e6}, {}, 0.0)
    assert r.value == 1e6 and r.pv == 5e6 and r.status == "OUT_OF_RANGE_HIGH"
    r = measure(_inst(lo=1e6), True, {"A": 5e5}, {}, 0.0)
    assert r.status == "OUT_OF_RANGE_LOW"


def test_no_value_substituted_on_failure_or_undetermined():
    assert measure(_inst(), False, {"A": 5e6}, {}, 0.0).value is None
    r = measure(_inst(), True, {"A": None}, {}, 0.0)
    assert r.value is None and r.status == "UNDETERMINED"
    r = measure(_inst(), True, {"A": math.nan}, {}, 0.0)
    assert r.status == "BAD"


def test_instruments_consistent_with_model(engine):
    r = engine.readings
    p = engine.hyd.node_pressure
    assert r["PT-102"].value == pytest.approx(p["N_UC"])
    assert r["PDT-101"].value == pytest.approx(r["PT-102"].value - r["PT-103"].value)
    assert r["PDT-101"].value == pytest.approx(engine.hyd.element_dp["CHOKE"])
    assert r["FT-101"].value == pytest.approx(engine.hyd.q)
    assert r["PT-201"].value == pytest.approx(engine.p_boundary)
    assert r["TT-001"].value == pytest.approx(engine.ipr.t_res)


# --------------------------------------------------------------- topology
def _nodes(*ids):
    return [Node(i, i, 0.0) for i in ids]


def _ipr(a="RES", b="A"):
    return InflowElement("IPR", "ipr", a, b, ipr=LinearIPR(1e7, 1e-8, 300.0))


def test_topology_rejects_broken_branched_or_unknown():
    with pytest.raises(TopologyError):
        SeriesTopology.build(_nodes("RES", "A", "B"), [_ipr()], "RES", "B")  # broken path
    with pytest.raises(TopologyError):
        SeriesTopology.build(_nodes("RES", "A"), [_ipr(b="Z")], "RES", "A")  # unknown node
    with pytest.raises(TopologyError):
        SeriesTopology.build(_nodes("RES", "A", "B"),
                             [_ipr(), InflowElement("IPR2", "i", "RES", "B", ipr=LinearIPR(1e7, 1e-8, 300.0))], "RES", "A")
    with pytest.raises(TopologyError):
        SeriesTopology.build(_nodes("RES", "A", "C"), [_ipr()], "RES", "A")  # unused node


# ---------------------------------------------------------------- scenarios
def test_all_scenarios_build_and_solve():
    for cfg in list_scenarios():
        built = build_system(cfg)
        assert built.topology.path[0].kind == "inflow"
        eng = SimulationEngine(cfg)
        assert eng.hyd.ok


def test_scenario_inheritance_overrides_choke():
    ex = get_scenario("ex03_choke_operation")
    base = get_scenario("base_single_phase")
    chk = {e.id: e for e in ex.elements}["CHOKE"]
    assert chk.initial_position_pct == 20
    assert ex.reservoir == base.reservoir


def test_unique_tags_and_units():
    eng = SimulationEngine(get_scenario("base_single_phase"))
    tags = list(eng.restrictions) + [i.tag for i in eng.instruments]
    assert len(tags) == len(set(tags))
    pt = next(i for i in eng.instruments if i.tag == "PT-101")
    assert pt.range_max == pytest.approx(u.bara_to_pa(690))
