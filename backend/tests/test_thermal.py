import math

import pytest

from app.core import units as u
from app.simulation.components.elements import PipeElement
from app.simulation.flowline.pipe import PipeGeometry
from app.simulation.fluid_properties.constant_liquid import ConstantPropertyLiquid
from app.simulation.inflow.ipr import LinearIPR
from app.simulation.solver.integration import implicit_euler_cell, substeps
from app.simulation.thermodynamics.thermal import ThermalModel
from app.simulation.topology.topology import Node, SeriesTopology
from app.simulation.components.elements import InflowElement

FLUID = ConstantPropertyLiquid("test", 850.0, 0.005, 2000.0, 0.0, 0.0)


def single_pipe(cells: int, u_val: float = 5.0, t_amb: float = 277.15, t_res: float = 368.15):
    ipr = LinearIPR(3e7, 1e-8, t_res)
    geom = PipeGeometry(5000.0, 0.15, 4.5e-5, 0.0)
    nodes = [Node("RES", "r", 0), Node("A", "a", 0), Node("B", "b", 0)]
    els = [InflowElement("IPR", "ipr", "RES", "A", ipr=ipr),
           PipeElement("P", "p", "A", "B", geometry=geom, overall_htc=u_val, ambient_in=t_amb, ambient_out=t_amb, thermal_cells=cells)]
    topo = SeriesTopology.build(nodes, els, "RES", "B")
    return ThermalModel(topo, FLUID, t_res, t_amb), geom


def test_steady_state_converges_to_plug_flow_exponential():
    q = 0.015
    model, geom = single_pipe(cells=400)
    temps = model.step(q, {}, None)
    mdot_cp = FLUID.rho * q * FLUID.cp
    ua = 5.0 * math.pi * geom.diameter * geom.length
    expected = 277.15 + (368.15 - 277.15) * math.exp(-ua / mdot_cp)
    assert temps["B"] == pytest.approx(expected, abs=0.05)


def test_tanks_in_series_exact_discrete_solution():
    q, n = 0.015, 7
    model, geom = single_pipe(cells=n)
    temps = model.step(q, {}, None)
    adv = FLUID.rho * q * FLUID.cp
    loss = 5.0 * math.pi * geom.diameter * geom.length / n
    expected = 277.15 + (368.15 - 277.15) * (adv / (adv + loss)) ** n
    assert temps["B"] == pytest.approx(expected, rel=1e-12)


def test_zero_flow_steady_state_is_ambient():
    model, _ = single_pipe(cells=10)
    model.step(0.015, {}, None)
    temps = model.step(0.0, {}, None)
    assert temps["B"] == pytest.approx(277.15)


def test_cooldown_is_monotonic_and_bounded():
    model, _ = single_pipe(cells=10)
    model.step(0.015, {}, None)
    t_prev = model.node_temperature["B"]
    for _ in range(50):
        t = model.step(0.0, {}, 600.0)["B"]
        assert 277.15 - 1e-9 <= t <= t_prev + 1e-9
        t_prev = t


def test_implicit_euler_stable_for_huge_steps():
    t = implicit_euler_cell(350.0, 350.0, 280.0, cap=1e6, adv=0.0, loss=10.0, dt=1e12)
    assert t == pytest.approx(280.0, abs=1e-3)
    assert implicit_euler_cell(350.0, 300.0, 280.0, 1e6, 5.0, 5.0, 0.0) == 350.0


def test_lumped_cooldown_time_constant():
    """Stagnant cell: T - Ta decays with tau = rho cp D / (4 U)."""
    model, geom = single_pipe(cells=1)
    model.cells["P"][:] = 368.15
    tau = FLUID.rho * FLUID.cp * geom.diameter / (4 * 5.0)
    dt = tau / 2000
    for _ in range(2000):
        model.step(0.0, {}, dt)
    expected = 277.15 + (368.15 - 277.15) * math.exp(-1.0)
    assert model.cells["P"][0] == pytest.approx(expected, rel=2e-3)


def test_throttling_temperature_rise(engine):
    dp = u.bar_to_pa_delta(50)
    t = 350.0
    rise = engine.thermal.throttling_temperature_rise(dp, t)
    f = engine.fluid
    assert rise == pytest.approx((1 - f.beta * t) * dp / (f.rho * f.cp))
    # base case: temperature downstream of choke exceeds upstream by the throttling rise
    temps = engine.thermal.node_temperature
    dp_choke = engine.hyd.element_dp["CHOKE"]
    assert temps["N_DC"] - temps["N_UC"] == pytest.approx(engine.thermal.throttling_temperature_rise(dp_choke, temps["N_UC"]))


def test_valve_command_does_not_step_temperature(engine):
    """Temperature must not jump when a valve closes - it decays thermally."""
    t0 = engine.thermal.node_temperature["N_ARR"]
    a = engine.restrictions["PWV-101"].actuator
    a.position_pct = a.commanded_pct = 0.0
    engine.recompute()
    assert engine.thermal.node_temperature["N_ARR"] == pytest.approx(t0)


def test_substeps():
    assert substeps(10.0, 5.0) == [5.0, 5.0]
    assert substeps(11.0, 5.0) == pytest.approx([11 / 3] * 3)
    assert substeps(0.0, 5.0) == []
    with pytest.raises(ValueError):
        substeps(1.0, 0.0)
