"""Engineering-behaviour reference tests on the base scenario."""

import pytest

from app.core import units as u
from app.scenarios.loader import get_scenario
from app.simulation.engine import SimulationEngine


def set_choke(engine, pct):
    a = engine.restrictions["CHK-101"].actuator
    a.position_pct = a.commanded_pct = pct
    engine.recompute()


def set_valve(engine, tag, pct):
    a = engine.restrictions[tag].actuator
    a.position_pct = a.commanded_pct = pct
    engine.recompute()


def q(engine):
    return engine.hyd.q


def test_base_case_operating_point(engine):
    assert engine.hyd.status == "solved"
    assert engine.hyd.q > 0
    assert engine.diagnostics == []
    # pressure decreases monotonically along the path in the flow direction? Not required in general
    # (hydrostatics), but every node must be above the boundary for this upward-flowing well.
    for nid, p in engine.hyd.node_pressure.items():
        assert p >= engine.p_boundary - 1.0, nid


@pytest.mark.parametrize("tag", ["SCSSV-101", "PMV-101", "PWV-101", "CHK-101"])
def test_closing_the_only_path_gives_zero_flow(engine, tag):
    set_valve(engine, tag, 0.0)
    assert engine.hyd.status == "closed_in"
    assert engine.hyd.q == 0.0
    assert engine.readings["FT-101"].value == 0.0


def test_closed_valve_pressures_follow_boundary_conditions(engine):
    set_valve(engine, "PWV-101", 0.0)
    p = engine.hyd.node_pressure
    rho = engine.props.rho
    nodes = engine.topology.nodes
    # reservoir side: static column from P_res (no drawdown)
    assert p["N_BH"] == pytest.approx(engine.ipr.p_res)
    dz = nodes["N_PMV_PWV"].elevation - nodes["N_BH"].elevation
    assert p["N_PMV_PWV"] == pytest.approx(engine.ipr.p_res - rho * u.G * dz)
    # boundary side: static from P_boundary
    dz2 = nodes["N_ARR"].elevation - nodes["N_UC"].elevation
    assert p["N_UC"] == pytest.approx(engine.p_boundary + rho * u.G * dz2)
    # differential across the closed valve equals the net static driving pressure
    assert engine.hyd.element_dp["PWV"] == pytest.approx(engine.hyd.driving_pressure)


def test_closing_valve_does_not_change_pressure_without_physical_cause(engine):
    """Closing an already-isolated downstream valve changes nothing."""
    set_valve(engine, "PWV-101", 0.0)
    before = dict(engine.hyd.node_pressure)
    set_choke(engine, 0.0)  # choke downstream of a closed PWV
    after = engine.hyd.node_pressure
    for n in ("N_BH", "N_TREE", "N_PMV_PWV", "N_ARR"):
        assert after[n] == pytest.approx(before[n])


def test_trapped_section_retains_pressure(engine):
    set_valve(engine, "PWV-101", 0.0)
    trapped_value = engine.hyd.node_pressure["N_PMV_PWV"]
    set_valve(engine, "PMV-101", 0.0)
    assert engine.hyd.node_state["N_PMV_PWV"] == "trapped"
    assert engine.hyd.node_pressure["N_PMV_PWV"] == pytest.approx(trapped_value)
    assert any(d.code == "TRAPPED_SECTION" for d in engine.diagnostics)


def test_trapped_section_without_history_is_undetermined():
    cfg = get_scenario("base_single_phase")
    for e in cfg.elements:
        if e.id in ("PMV", "PWV"):
            e.initial_position_pct = 0.0
    eng = SimulationEngine(cfg)
    assert eng.hyd.node_pressure["N_PMV_PWV"] is None
    # the transmitters are not on this node, but a differential across PMV is undetermined
    assert eng.hyd.element_dp["PMV"] is None


def test_flow_increases_monotonically_with_choke_opening(engine):
    flows = []
    for pct in (5, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100):
        set_choke(engine, pct)
        flows.append(q(engine))
    assert all(b > a for a, b in zip(flows, flows[1:]))


def test_choke_opening_is_not_proportional_to_flow(engine):
    set_choke(engine, 100)
    qmax = q(engine)
    set_choke(engine, 50)
    assert q(engine) / qmax != pytest.approx(0.5, abs=0.05)


def test_choke_differential_falls_as_choke_opens(engine):
    dps = []
    for pct in (20, 40, 60, 80, 100):
        set_choke(engine, pct)
        dps.append(engine.hyd.element_dp["CHOKE"])
    assert all(b < a for a, b in zip(dps, dps[1:]))


def test_flow_responds_to_boundary_conditions(engine):
    q0 = q(engine)
    engine.set_boundary(reservoir_pressure_pa=engine.ipr.p_res + u.bar_to_pa_delta(20))
    q_up = q(engine)
    assert q_up > q0
    engine.set_boundary(reservoir_pressure_pa=engine.ipr.p_res - u.bar_to_pa_delta(20))
    assert q(engine) == pytest.approx(q0)
    engine.set_boundary(downstream_pressure_pa=engine.p_boundary + u.bar_to_pa_delta(20))
    assert q(engine) < q0


def test_flow_responds_to_fluid_properties(engine):
    q0 = q(engine)
    engine.set_fluid(viscosity=engine.fluid.mu * 10)
    assert q(engine) < q0  # more friction
    engine.set_fluid(viscosity=engine.fluid.mu / 10)
    engine.set_fluid(density=900.0)
    assert q(engine) < q0  # more hydrostatic head and restriction loss


def test_flow_responds_to_productivity_index(engine):
    q0 = q(engine)
    engine.set_boundary(productivity_index_si=engine.ipr.j * 2)
    assert q(engine) > q0


def test_insufficient_drive_gives_reverse_flow_warning(engine):
    # Downstream pressure higher than reservoir pressure minus hydrostatic head
    engine.set_boundary(downstream_pressure_pa=u.bara_to_pa(200))
    assert engine.hyd.q < 0
    assert any(d.code == "REVERSE_FLOW" for d in engine.diagnostics)


def test_below_bubble_point_is_flagged(engine):
    engine.set_boundary(downstream_pressure_pa=u.bara_to_pa(20))
    assert any(d.code == "BELOW_BUBBLE_POINT" for d in engine.diagnostics)


def test_static_column_that_cannot_reach_the_tree_is_invalid(engine):
    set_valve(engine, "PWV-101", 0.0)
    engine.set_boundary(reservoir_pressure_pa=u.bara_to_pa(150))  # < rho g H (~210 bar)
    assert any(d.code == "NEGATIVE_ABSOLUTE_PRESSURE" for d in engine.diagnostics)
    assert engine.readings["PT-101"].status == "BAD"
    assert engine.readings["PT-101"].value is None
