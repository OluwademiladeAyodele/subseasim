"""Three-phase black-oil model, multiphase correlations, steady and dynamic
multiphase solutions.

Where possible the checks are against INDEPENDENT references (published
charts, textbook closed-form limits), not the implementation's own formulas:
Standing-Katz Z chart, isentropic nozzle critical-pressure ratio, the
single-phase orifice and Darcy-Weisbach equations, published methane
viscosity, Standing's bubble-point equation evaluated by hand."""

from __future__ import annotations

import math
import warnings

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.scenarios.loader import get_scenario
from app.simulation.engine import SimulationEngine
from app.simulation.fluid_properties.black_oil import (
    BlackOilFluid,
    BlackOilParams,
    bubble_point,
    gas_viscosity_lge,
    z_factor_dak,
)
from app.simulation.multiphase.correlations import beggs_brill, flow_pattern, sachdeva_critical_ratio, sachdeva_mass_flow
from app.simulation.multiphase.steady import solve_steady

warnings.simplefilter("ignore", RuntimeWarning)
SCN = "xt_230xp22b_multiphase"
FLUID = BlackOilParams("test", api=35.0, gas_sg=0.75, gor_sm3_sm3=120.0, water_cut=0.30)


@pytest.fixture(scope="module")
def fluid():
    return BlackOilFluid(FLUID)


# ------------------------------------------------------------------ PVT
@pytest.mark.parametrize("tpr,ppr,z_chart", [(1.5, 2.0, 0.82), (1.2, 1.0, 0.78), (2.0, 5.0, 0.96), (1.3, 0.5, 0.92), (1.5, 0.01, 1.0)])
def test_dak_z_factor_against_standing_katz_chart(tpr, ppr, z_chart):
    """Standing-Katz (1942) chart readings, +-0.02."""
    assert float(z_factor_dak(ppr, tpr)[0]) == pytest.approx(z_chart, abs=0.02)


def test_bubble_point_matches_standing_hand_calculation():
    """Standing: Pb = 18.2 [(Rs/gg)^0.83 10^(0.00091 T - 0.0125 API) - 1.4] psia,
    Rs = 120 Sm3/Sm3 = 673.75 scf/STB, T = 203 F, API 35, gg 0.75 -> 2852 psia."""
    rs, t_f, api, gg = 120 * 5.614583, 203.0, 35.0, 0.75
    pb_psia = 18.2 * ((rs / gg) ** 0.83 * 10 ** (0.00091 * t_f - 0.0125 * api) - 1.4)
    assert float(np.atleast_1d(bubble_point(120.0, (t_f - 32) / 1.8 + 273.15, api, gg))[0]) == pytest.approx(pb_psia * 6894.757, rel=1e-6)
    assert pb_psia == pytest.approx(2852, rel=0.01)


def test_gas_viscosity_of_methane_at_low_pressure():
    """Methane at 1 atm, 20 C: 0.0110 cP (NIST); LGE accuracy ~ +-3 %."""
    rho = 101325 * 0.016043 / (8.314462 * 293.15)
    assert float(gas_viscosity_lge(rho, 293.15, 0.5539)) == pytest.approx(0.0110, rel=0.05)


def test_phase_split_and_component_mass_conservation(fluid):
    p = np.array([380e5, 197e5, 150e5, 100e5, 50e5, 10e5])
    t = np.full(p.shape, 340.0)
    s = fluid.state(p, t)
    # no free gas above the bubble point; free gas increases as pressure falls
    assert s.gvf[0] == 0 and s.gvf[1] == 0
    assert np.all(np.diff(s.gvf[1:]) > 0)
    # component masses per Sm3 stock-tank liquid are conserved through the flash
    total = fluid.mass_per_liquid_sc()
    assert np.allclose(s.mass, total, rtol=1e-12)
    # volume fractions sum to one
    assert np.allclose(s.vol_o / s.vol + s.vol_g / s.vol + s.vol_w / s.vol, 1.0)
    # oil shrinks as gas is liberated (Bo decreases below Pb)
    assert np.all(np.diff(s.bo[1:]) < 0)


def test_composition_round_trip(fluid):
    for gor, wc in [(0.0, 0.0), (50.0, 0.1), (120.0, 0.3), (600.0, 0.9)]:
        x = fluid.component_mass_fractions(gor, wc)
        g, w = fluid.composition_from_mass_fractions(*x)
        assert float(g) == pytest.approx(gor, abs=1e-9) and float(w) == pytest.approx(wc, abs=1e-12)
        assert sum(x) == pytest.approx(1.0)


def test_correlation_validity_is_reported(fluid):
    v = {x["correlation"]: x for x in fluid.validity(5e5, 400e5, 277.0, 368.0)}
    assert not v["Beggs-Robinson oil viscosity"]["in_range"]  # 4 C seabed outside 70-295 F
    assert v["Standing Rs / Pb / Bo"]["in_range"]


# ---------------------------------------------------------- correlations
def test_sachdeva_liquid_limit_is_the_orifice_equation():
    w, yc, crit = sachdeva_mass_flow(100e5, 60e5, 0.0, 800.0, 80.0, 1e-4, 1.27, 2300, 2500)
    assert float(w) == pytest.approx(1e-4 * math.sqrt(2 * 800 * 40e5), rel=1e-9)
    assert not bool(crit)


@pytest.mark.parametrize("k", [1.15, 1.27, 1.4])
def test_sachdeva_gas_limit_is_the_isentropic_critical_ratio(k):
    """Single-phase ideal gas: y_c = (2 / (k + 1))^(k / (k - 1))."""
    yc = sachdeva_critical_ratio(np.array([1.0]), 800.0, np.array([0.02]), k, np.array([1.0 + (1 - 1 / k) * k]))
    assert float(yc[0]) == pytest.approx((2 / (k + 1)) ** (k / (k - 1)), rel=1e-6)


def test_choked_flow_is_independent_of_downstream_pressure():
    w1, yc, c1 = sachdeva_mass_flow(100e5, 20e5, 0.05, 800.0, 80.0, 1e-4, 1.27, 2300, 2500)
    w2, _, c2 = sachdeva_mass_flow(100e5, 5e5, 0.05, 800.0, 80.0, 1e-4, 1.27, 2300, 2500)
    assert bool(c1) and bool(c2) and float(w1) == pytest.approx(float(w2), rel=1e-12)
    w3, _, c3 = sachdeva_mass_flow(100e5, 90e5, 0.05, 800.0, 80.0, 1e-4, 1.27, 2300, 2500)
    assert not bool(c3) and float(w3) < float(w1)


def test_beggs_brill_single_phase_limit_is_darcy_weisbach():
    v, rho, mu, d, eps = 2.0, 850.0, 5e-3, 0.1, 4.5e-5
    r = beggs_brill(np.array([v]), np.array([0.0]), rho, 1.0, mu, 1e-5, 0.02, d, np.array([0.0]), eps)
    re = rho * v * d / mu
    # Colebrook-White reference (independent of Churchill)
    f = 0.02
    for _ in range(50):
        f = (-2 * math.log10(eps / d / 3.7 + 2.51 / (re * math.sqrt(f)))) ** -2
    assert float(r["grad_friction"][0]) == pytest.approx(f * rho * v * v / (2 * d), rel=0.02)
    assert float(r["holdup"][0]) == 1.0 and float(r["friction_multiplier"][0]) == 1.0


def test_beggs_brill_holdup_and_patterns_are_physical():
    lam = np.array([0.005, 0.05, 0.3, 0.6, 0.9])
    for nfr in (0.01, 1.0, 100.0, 1000.0):
        pat, _, _ = flow_pattern(lam, np.full(lam.shape, nfr))
        assert set(np.unique(pat)) <= {0, 1, 2, 3}
    vsl, vsg = np.array([0.5, 0.5, 0.5]), np.array([0.5, 0.5, 0.5])
    up = beggs_brill(vsl, vsg, 800.0, 80.0, 1e-3, 1.5e-5, 0.02, 0.1, np.array([math.pi / 2, 0.0, -math.pi / 2]), 4.5e-5)
    hl = up["holdup"]
    assert np.all((hl > 0) & (hl <= 1))
    assert hl[0] >= 0.5 and hl[0] > hl[2]  # uphill holds back liquid, downhill drains it
    nos = beggs_brill(vsl, vsg, 800.0, 80.0, 1e-3, 1.5e-5, 0.02, 0.1, np.array([math.pi / 2] * 3), 4.5e-5, "no_slip")
    assert np.allclose(nos["holdup"], 0.5)


# --------------------------------------------------------------- steady
@pytest.fixture(scope="module")
def engine_steady():
    return SimulationEngine(get_scenario(SCN), mode="steady")


def test_steady_solution_converges_and_conserves_component_mass(engine_steady):
    e = engine_steady
    r = e.mp_steady
    assert r.ok and r.w > 0
    rep = e.snapshot(False)["multiphase"]
    a, b = rep["rates_reservoir"], rep["rates_arrival"]
    for k in ("oil_mass_kg_s", "gas_mass_kg_s", "water_mass_kg_s"):
        assert a[k] == pytest.approx(b[k], rel=1e-12)
    assert a["oil_mass_kg_s"] + a["gas_mass_kg_s"] + a["water_mass_kg_s"] == pytest.approx(a["mass_kg_s"], rel=1e-12)
    assert a["gas_sm3_d"] == pytest.approx(a["oil_sm3_d"] * 120.0, rel=1e-12)
    assert a["water_sm3_d"] / a["liquid_sm3_d"] == pytest.approx(0.30, rel=1e-12)
    # pressures decrease monotonically along the producing path; arrival at the boundary
    ps = [n["p_pa"] for n in rep["nodes"]]
    assert all(x >= y - 1.0 for x, y in zip(ps, ps[1:]))
    assert ps[-1] == pytest.approx(e.p_boundary)


def test_steady_choke_opening_changes_the_operating_point(engine_steady):
    e = SimulationEngine(get_scenario(SCN), mode="steady")
    q0, p_tree0 = e.hyd.q, e.hyd.node_pressure["N_PMV_PWV"]
    e.restrictions["CHK-101"].actuator.position_pct = 70.0
    e.restrictions["CHK-101"].actuator.commanded_pct = 70.0
    e.recompute()
    assert e.hyd.q > q0 * 1.3 and e.hyd.node_pressure["N_PMV_PWV"] < p_tree0 - 10e5


def test_steady_reservoir_pressure_changes_production():
    e = SimulationEngine(get_scenario(SCN), mode="steady")
    q0 = e.hyd.q
    e.set_boundary(reservoir_pressure_pa=330e5)
    assert e.hyd.q < q0 * 0.9


def test_beggs_brill_and_no_slip_both_solve_and_differ(engine_steady):
    e = engine_steady
    T = e._node_temperatures()
    a = solve_steady(e.topology, e.bo, e.ipr.p_res, e.p_boundary, e.ipr.j, e.rho_ref, T, 120, 0.3, "beggs_brill")
    b = solve_steady(e.topology, e.bo, e.ipr.p_res, e.p_boundary, e.ipr.j, e.rho_ref, T, 120, 0.3, "no_slip")
    assert a.ok and b.ok
    assert a.node_pressure["N_BH"] != b.node_pressure["N_BH"]


# -------------------------------------------------------------- dynamic
@pytest.fixture(scope="module")
def engine_dyn():
    e = SimulationEngine(get_scenario(SCN))
    e.start()
    return e


def test_dynamic_initial_state_is_steady_and_close_to_the_march(engine_dyn):
    e = engine_dyn
    d = e.dyn
    q_dyn = float(d.net.Q[d.layout.element_link[e.topology.path[0].id]])
    assert q_dyn == pytest.approx(e.hyd.q, rel=0.03)
    for nid in ("N_BH", "N_PMV_PWV", "N_DC"):
        assert d.node_pressure(nid) == pytest.approx(e.hyd.node_pressure[nid], abs=3e5)
    p0 = d.node_pressure("N_PMV_PWV")
    e.advance(120)
    assert abs(d.node_pressure("N_PMV_PWV") - p0) < 0.2e5
    assert d.net.last_converged


def test_dynamic_component_mass_balance_through_transients(engine_dyn):
    e = engine_dyn
    e.command_valve("CHK-101", "set_position", 55)
    e.advance(900)
    e.command_valve("PWV-101", "close")
    e.advance(600)
    e.command_valve("PWV-101", "open")
    e.set_black_oil(water_cut=0.5, producing_gor_sm3_sm3=90)
    e.advance(1200)
    mb = e.dyn.mp.mass_balance()
    for comp in ("oil", "gas", "water"):
        assert mb[comp]["in_kg"] > 1000
        assert abs(mb[comp]["residual_kg"]) < 1e-6 * mb[comp]["in_kg"], (comp, mb[comp])


def test_dynamic_composition_change_travels_with_the_fluid():
    e = SimulationEngine(get_scenario(SCN))
    e.start()
    e.set_black_oil(water_cut=0.6)
    e.advance(300)
    rep = e.snapshot(False)["multiphase"]
    wc = {n["node"]: n["water_cut"] for n in rep["nodes"]}
    assert wc["N_BH"] == pytest.approx(0.6, abs=0.01)  # new fluid already at the sandface
    assert wc["N_ARR"] == pytest.approx(0.3, abs=0.01)  # not yet at the manifold
    assert rep["rates_reservoir"]["water_cut"] == pytest.approx(0.6)


def test_dynamic_choke_response_and_flow_transmitter_reads_in_situ_volume():
    e = SimulationEngine(get_scenario(SCN))
    e.start()
    e.advance(30)
    d = e.dyn
    w0 = e.snapshot(False)["multiphase"]["rates_arrival"]["oil_sm3_d"]
    ft0 = e.readings["FT-101"].value
    # in-situ volume at the choke outlet exceeds the reference (reservoir) volume: gas has come out of solution
    q_ref = float(d.net.Q[d.prod_out_link["N_DC"]])
    assert ft0 > 1.5 * q_ref
    e.command_valve("CHK-101", "set_position", 70)
    e.advance(1800)
    rep = e.snapshot(False)["multiphase"]
    assert rep["rates_arrival"]["oil_sm3_d"] > 1.3 * w0
    assert e.readings["FT-101"].value > ft0
    assert any(p["pattern"] in ("intermittent", "segregated", "distributed", "transition") for p in rep["pipes"])


def test_single_phase_mode_is_preserved_and_switchable():
    e = SimulationEngine(get_scenario(SCN))
    assert e.fluid_model == "black_oil"
    e.set_fluid_model("single_phase")
    assert e.fluid_model == "single_phase" and e.bo is None and e.dyn.mp is None
    assert e.snapshot(False)["multiphase"] is None
    e.set_fluid_model("black_oil")
    assert e.dyn.mp is not None


def test_dynamic_step_cost_is_acceptable(engine_dyn):
    import time

    e = engine_dyn
    t = time.perf_counter()
    e.advance(60)
    assert (time.perf_counter() - t) / 60 < 0.05  # < 50 ms per 1 s step (typically ~5 ms)


def test_api_black_oil_and_fluid_model_endpoints():
    with TestClient(app) as client:
        sid = client.post("/api/sessions", json={"scenario_id": SCN}).json()["session_id"]
        r = client.put(f"/api/sessions/{sid}/black-oil", json={"water_cut": 0.45, "producing_gor_sm3_sm3": 100})
        assert r.status_code == 200
        mp = r.json()["state"]["multiphase"]
        assert mp["params"]["water_cut"] == pytest.approx(0.45) and mp["params"]["producing_gor_sm3_sm3"] == 100
        assert client.put(f"/api/sessions/{sid}/black-oil", json={"water_cut": 1.5}).status_code == 422
        assert client.put(f"/api/sessions/{sid}/fluid", json={"density_kg_m3": 800}).status_code == 422
        r = client.post(f"/api/sessions/{sid}/fluid-model", json={"model": "single_phase"})
        assert r.status_code == 200 and r.json()["state"]["multiphase"] is None
        assert client.put(f"/api/sessions/{sid}/black-oil", json={"water_cut": 0.2}).status_code == 409
