"""Numerical verification against closed-form solutions."""

import math

import numpy as np
import pytest

from app.core import units as u
from app.simulation.flowline.pipe import PipeGeometry
from app.simulation.hydraulics.network import solve_hydraulics
from app.simulation.hydraulics.properties import FlowProperties
from app.simulation.inflow.ipr import LinearIPR
from tests.conftest import make_topology

RHO, MU = 850.0, 0.005
PROPS = FlowProperties(RHO, MU)


def test_ipr_plus_restriction_matches_quadratic_solution():
    p_res, p_b = u.bara_to_pa(300), u.bara_to_pa(100)
    j = u.pi_m3d_per_bar_to_si(20)
    ipr = LinearIPR(p_res, j, 350.0)
    topo = make_topology(ipr, choke_cv=40.0)
    c = u.cv_to_capacity(40.0)
    # (p_res - p_b) = Q/J + rho Q^2 / (2 C^2)
    a, b, dlt = RHO / (2 * c * c), 1 / j, p_res - p_b
    q_exact = (-b + math.sqrt(b * b + 4 * a * dlt)) / (2 * a)
    res = solve_hydraulics(topo, p_res, p_b, PROPS)
    assert res.status == "solved"
    assert res.q == pytest.approx(q_exact, rel=1e-10)


def test_ipr_plus_laminar_pipe_matches_linear_solution():
    mu = 1.0  # very viscous -> laminar
    props = FlowProperties(RHO, mu)
    p_res, p_b = u.bara_to_pa(150), u.bara_to_pa(100)
    j = u.pi_m3d_per_bar_to_si(5)
    geom = PipeGeometry(length=2000.0, diameter=0.1, roughness=1e-5, dz=0.0)
    topo = make_topology(LinearIPR(p_res, j, 350.0), pipe=geom)
    r_hp = 128 * mu * geom.length / (math.pi * geom.diameter**4)
    q_exact = (p_res - p_b) / (1 / j + r_hp)
    res = solve_hydraulics(topo, p_res, p_b, props)
    re = RHO * (res.q / geom.area) * geom.diameter / mu
    assert re < 1000  # confirm laminar regime for the reference to apply
    assert res.q == pytest.approx(q_exact, rel=2e-3)


def test_hydrostatic_column_static_pressure():
    """Closed outlet: pressure at the top of a vertical liquid column = P_res - rho g H."""
    p_res = u.bara_to_pa(300)
    h = 1500.0
    geom = PipeGeometry(length=h, diameter=0.1, roughness=1e-5, dz=h)
    topo = make_topology(LinearIPR(p_res, u.pi_m3d_per_bar_to_si(10), 350.0), pipe=geom, valve_k=0.2, valve_pos=0.0, z_out=h)
    res = solve_hydraulics(topo, p_res, u.bara_to_pa(50), PROPS)
    assert res.status == "closed_in" and res.q == 0.0
    assert res.node_pressure["A"] == pytest.approx(p_res)  # no drawdown at zero flow
    assert res.node_pressure["P1"] == pytest.approx(p_res - RHO * u.G * h)
    assert res.node_pressure["V2"] == pytest.approx(u.bara_to_pa(50))


def test_pressure_budget_closes_and_mass_is_conserved():
    p_res, p_b = u.bara_to_pa(300), u.bara_to_pa(80)
    geom = PipeGeometry(length=3000.0, diameter=0.1, roughness=4.5e-5, dz=1000.0)
    topo = make_topology(LinearIPR(p_res, u.pi_m3d_per_bar_to_si(15), 350.0), pipe=geom, valve_k=0.2, choke_cv=60, choke_pos=50, z_out=1000.0)
    res = solve_hydraulics(topo, p_res, p_b, PROPS)
    total = sum(res.element_dp.values())
    assert total == pytest.approx(p_res - p_b, abs=1.0)
    # series path: each element's dp evaluated with the same Q reproduces the node pressures
    nodes = topo.node_order
    for i, e in enumerate(topo.path):
        assert res.node_pressure[nodes[i]] - res.node_pressure[nodes[i + 1]] == pytest.approx(e.dp(res.q, PROPS), abs=1.0)


def test_solver_converges_over_wide_parameter_sweep():
    rng = np.random.default_rng(12345)
    for _ in range(300):
        p_res = u.bara_to_pa(rng.uniform(50, 800))
        p_b = u.bara_to_pa(rng.uniform(1, 400))
        j = u.pi_m3d_per_bar_to_si(10 ** rng.uniform(-1, 3))
        geom = PipeGeometry(length=rng.uniform(10, 20000), diameter=rng.uniform(0.05, 0.4), roughness=4.5e-5, dz=0.0)
        props = FlowProperties(rng.uniform(600, 1100), 10 ** rng.uniform(-4, 0))
        topo = make_topology(LinearIPR(p_res, j, 350.0), pipe=geom, choke_cv=rng.uniform(5, 500), choke_pos=rng.uniform(0.5, 100))
        res = solve_hydraulics(topo, p_res, p_b, props)
        assert res.status == "solved", res.message
        assert abs(res.residual) <= max(1.0, 1e-8 * max(p_res, p_b))
        assert np.sign(res.q) == np.sign(p_res - p_b)


@pytest.mark.parametrize("pos", [1e-12, 1e-8, 1e-4, 0.01])
def test_nearly_closed_restriction_still_converges(pos):
    """Regression: an almost-closed choke gives a tiny but well-resolved flow."""
    p_res, p_b = u.bara_to_pa(300), u.bara_to_pa(100)
    ipr = LinearIPR(p_res, u.pi_m3d_per_bar_to_si(20), 350.0)
    topo = make_topology(ipr, choke_cv=100.0, choke_pos=pos)
    res = solve_hydraulics(topo, p_res, p_b, PROPS)
    assert res.status == "solved", res.message
    c = topo.element("CHOKE").capacity
    # nearly all of the driving pressure appears across the choke
    q_restriction_only = c * math.sqrt(2 * (p_res - p_b) / RHO)
    assert res.q == pytest.approx(q_restriction_only, rel=1e-3)
