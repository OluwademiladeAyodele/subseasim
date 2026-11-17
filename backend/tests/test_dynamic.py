"""Dynamic-simulation behaviour tests (Release 2).

Reference cases use analytical solutions where they exist (RC charging of
a lumped volume, acoustic wave travel time, plug-flow residence time,
exponential heat-loss profile); the rest check physically required
behaviour on the dynamic training scenarios. Tolerances are stated per test
and documented in docs/DYNAMIC_SIMULATION_MODEL.md (Verification).
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from app.core import units as u
from app.core.config import Settings
from app.scenarios.loader import get_scenario
from app.simulation.components.elements import CommandRejected
from app.simulation.dynamic.network import LINEAR, ORIFICE, PIPE, HNode, HydraulicNetwork, Link
from app.simulation.engine import SimulationEngine


def eng(scenario: str = "subsea_dynamic_base", **cfg_kw) -> SimulationEngine:
    e = SimulationEngine(get_scenario(scenario), Settings(**cfg_kw) if cfg_kw else Settings())
    e.start()
    return e


def bara(e: SimulationEngine, tag: str) -> float:
    return u.pa_to_bara(e.readings[tag].value)


def pv(e: SimulationEngine, tag: str) -> float:
    return e.readings[tag].pv


def run_until(e: SimulationEngine, t: float) -> None:
    e.advance(t - e.time_s)


# ============================================================ network level
class _FakeRestriction:
    def __init__(self, c: float):
        self.capacity = c
        self.seat_leak_capacity = 0.0


def test_lumped_volume_charges_with_rc_time_constant():
    """Tank (capacitance C) fed from a fixed pressure through a linear
    resistance R: P(t) = P1 + (P0 - P1) exp(-t / RC). Backward Euler with
    dt = tau/200 must match within 0.5 % of the step."""
    V, c_f = 10.0, 1e-9
    C = V * c_f
    R = 1e10  # Pa s / m3
    nodes = [HNode("SRC", "src", 0.0, "z", fixed=True, p_fixed=200e5), HNode("TANK", "tank", 0.0, "z", volume=V, capacitance=C)]
    links = [Link("R", 0, 1, LINEAR, "R", conductance=1.0 / R)]
    net = HydraulicNetwork(nodes, links)
    net.P = np.array([200e5, 100e5])
    tau = R * C
    dt = tau / 200
    for k in range(1, 401):
        net.solve(dt)
        if k in (100, 200, 400):
            exact = 200e5 + (100e5 - 200e5) * math.exp(-k * dt / tau)
            assert net.P[1] == pytest.approx(exact, abs=0.005 * 100e5)


def test_build_up_time_scales_with_volume_and_compliance():
    """Doubling the volume (or the compliance) doubles the time constant."""
    def t63(V, c):
        nodes = [HNode("SRC", "s", 0.0, "z", fixed=True, p_fixed=200e5), HNode("T", "t", 0.0, "z", volume=V, capacitance=V * c)]
        net = HydraulicNetwork(nodes, [Link("R", 0, 1, LINEAR, "R", conductance=1e-10)])
        net.P = np.array([200e5, 100e5])
        t = 0.0
        while net.P[1] < 100e5 + 0.632 * 100e5:
            net.solve(0.01)
            t += 0.01
        return t

    base = t63(10.0, 1e-9)
    assert t63(20.0, 1e-9) == pytest.approx(2 * base, rel=0.02)
    assert t63(10.0, 2e-9) == pytest.approx(2 * base, rel=0.02)


def _pipe_network(n_seg=40, L=4000.0, D=0.15, c_f=7e-10, rho=850.0):
    A = math.pi * D * D / 4
    nodes = [HNode("IN", "in", 0.0, "z", fixed=True, p_fixed=100e5)]
    for k in range(1, n_seg + 1):
        nodes.append(HNode(f"P{k}", f"p{k}", 0.0, "z"))
    nodes.append(HNode("OUT", "out", 0.0, "z", fixed=True, p_fixed=50e5))
    dl = L / n_seg
    links = []
    for k in range(n_seg):
        for j in (k, k + 1):
            if not nodes[j].fixed:
                nodes[j].volume += A * dl / 2
                nodes[j].capacitance += A * dl / 2 * c_f
        links.append(Link(f"S{k}", k, k + 1, PIPE, "pipe", inertance=rho * dl / A, length=dl, diameter=D, area=A,
                          roughness=4.5e-5, rho=rho, mu=5e-3))
    nodes[n_seg].volume += 0.01
    nodes[n_seg].capacitance += 0.01 * c_f
    valve = _FakeRestriction(2e-3)
    links.append(Link("V", n_seg, n_seg + 1, ORIFICE, "valve", inertance=rho * 0.5 / 2e-3, rho=rho, restriction=valve))
    net = HydraulicNetwork(nodes, links)
    net.P = np.linspace(100e5, 60e5, n_seg + 2)
    net.P[-1] = 50e5
    net.solve(None)
    return net, valve, dl, math.sqrt(1.0 / (rho * c_f))


def test_pressure_wave_reaches_far_location_later():
    """Instantaneous closure at the outlet: the pressure rise reaches a point
    1 km upstream of the valve before a point 3 km upstream; the arrival-time
    difference matches 2 km / a (lumped LC ladder, fine step) within 25 %."""
    net, valve, dl, a = _pipe_network()
    near, far = 40 - int(1000 / dl), 40 - int(3000 / dl)
    p_near0, p_far0 = net.P[near], net.P[far]
    valve.capacity = 0.0
    t, t_near, t_far, dt = 0.0, None, None, 0.01
    while t < 6.0 and (t_near is None or t_far is None):
        net.solve(dt)
        t += dt
        if t_near is None and net.P[near] - p_near0 > 0.5e5:
            t_near = t
        if t_far is None and net.P[far] - p_far0 > 0.5e5:
            t_far = t
    assert t_near is not None and t_far is not None
    assert t_far > t_near
    assert t_far - t_near == pytest.approx(2000.0 / a, rel=0.25)


# ======================================================== engine: pressure
def test_pressure_does_not_jump_to_new_steady_state():
    e = eng()
    p0 = bara(e, "PT-101")
    e.command_valve("PWV-101", "close")
    run_until(e, 40.0)  # valve fully closed (2 s dead time + 30 s travel)
    assert e.restrictions["PWV-101"].actuator.position_pct == 0.0
    ref = u.pa_to_bara(e.hyd.node_pressure["N_TREE"])
    p_closed = bara(e, "PT-101")
    assert p0 < p_closed < ref - 5.0  # rising, but far from the shut-in value
    run_until(e, 1800.0)
    p_30 = bara(e, "PT-101")
    run_until(e, 7200.0)
    p_120 = bara(e, "PT-101")
    assert p_closed < p_30 < p_120 < ref + 0.01  # monotone approach from below


def test_no_response_during_actuator_dead_time():
    e = eng()
    p0 = pv(e, "PT-102")
    e.command_valve("PWV-101", "close")
    run_until(e, 1.0)  # dead time is 2 s
    assert e.restrictions["PWV-101"].actuator.position_pct == 100.0
    assert pv(e, "PT-102") == pytest.approx(p0, abs=1.0)


def test_boundary_change_propagates_gradually_to_steady_reference():
    e = eng()
    run_until(e, 10.0)
    p103 = pv(e, "PT-103")
    e.set_boundary(downstream_pressure_pa=u.bara_to_pa(90.0))
    target = e.hyd.node_pressure["N_DC"]
    run_until(e, 11.0)
    first = pv(e, "PT-103")
    assert p103 < first < target  # moving, not arrived
    run_until(e, 4 * 3600.0)
    assert pv(e, "PT-103") == pytest.approx(target, abs=0.5e5)


def test_measurement_locations_respond_differently():
    e = eng()
    a0, b0 = pv(e, "PT-001"), pv(e, "PT-101")
    e.command_valve("PWV-101", "close")
    run_until(e, 120.0)
    da, db = pv(e, "PT-001") - a0, pv(e, "PT-101") - b0
    assert da > 0 and db > 0 and abs(da - db) > 1e4


def test_pressure_response_depends_on_reservoir_compressibility():
    def rise(ct):
        cfg = get_scenario("subsea_dynamic_base")
        cfg.dynamics.reservoir.total_compressibility_1_bar = ct
        e = SimulationEngine(cfg)
        e.start()
        p0 = pv(e, "PT-001")
        e.command_valve("PWV-101", "close")
        run_until(e, 600.0)
        return pv(e, "PT-001") - p0

    assert rise(0.5e-4) > rise(3e-4)  # stiffer reservoir: faster build-up


# ======================================================= chemical transport
def _open_meoh(scenario="dyn_c_methanol_injection", choke=None):
    cfg = get_scenario(scenario)
    if choke is not None:
        for el in cfg.elements:
            if el.id == "CHOKE":
                el.initial_position_pct = choke
    e = SimulationEngine(cfg)
    e.start()
    e.command_valve("CIV-301", "open")
    return e


def test_chemical_initially_only_near_injection_point():
    e = _open_meoh()
    run_until(e, 120.0)
    g = e.dyn.grid
    k = e.dyn.chem_ids.index("methanol")
    inj_cell = g.node_lookup["N_PMV_PWV"].cell
    assert g.c[k, :inj_cell].max() == 0.0  # nothing upstream of the injection point
    assert pv(e, "AT-510") > 0.01
    # upwind numerical dispersion leaves only a ~1e-11 tail ahead of the front
    assert pv(e, "AT-511") < 1e-6 and pv(e, "AT-512") < 1e-6


def _arrival(e, tag, frac=0.5, t_max=6 * 3600.0, step=30.0):
    """Time at which tag reaches frac of the fully-mixed concentration."""
    t0 = e.time_s
    while e.time_s - t0 < t_max:
        e.advance(step)
        c = next(c for c in e.snapshot(False)["chemicals"] if c["id"] == "methanol")
        if c["fully_mixed_concentration"] > 0 and pv(e, tag) >= frac * c["fully_mixed_concentration"]:
            return e.time_s - t0
    return None


def test_arrival_time_matches_plug_flow_residence_time():
    e = _open_meoh()
    run_until(e, 30.0)
    an = next(a for c in e.snapshot(False)["chemicals"] if c["id"] == "methanol" for a in c["analysers"] if a["tag"] == "AT-511")
    t_plug = an["plug_flow_transit_s"]
    t_arr = _arrival(e, "AT-511")
    assert t_arr == pytest.approx(t_plug, rel=0.12)


def test_higher_flow_gives_earlier_arrival():
    slow = _arrival(_open_meoh(choke=20), "AT-511")
    fast = _arrival(_open_meoh(choke=60), "AT-511")
    assert fast is not None and slow is not None and fast < 0.8 * slow


def test_no_advective_transport_without_flow():
    e = _open_meoh()
    run_until(e, 3600.0)
    front0 = next(c for c in e.snapshot(False)["chemicals"] if c["id"] == "methanol")["front_distance_m"]
    e.command_valve("CIV-301", "close")
    e.command_valve("PWV-101", "close")
    run_until(e, 3600.0 + 600.0)
    front1 = next(c for c in e.snapshot(False)["chemicals"] if c["id"] == "methanol")["front_distance_m"]
    run_until(e, 3600.0 + 7200.0)
    front2 = next(c for c in e.snapshot(False)["chemicals"] if c["id"] == "methanol")["front_distance_m"]
    # With production stopped the only fluid movement is thermal contraction
    # of the cooling flowline (fluid drawn back from the manifold): ~100 m in
    # 2 h, compared with ~5 km of advection in the same time while flowing.
    assert abs(front2 - front1) < 250.0
    assert front1 >= front0 - 60.0


def test_injection_shutdown_does_not_erase_chemical_in_line():
    e = eng("dyn_e_injection_shutdown")
    k = e.dyn.chem_ids.index("methanol")
    inv0 = e.dyn.grid.inventory()[k]
    at512 = pv(e, "AT-512")
    assert at512 > 0.01
    e.command_valve("CIV-301", "close")
    run_until(e, 300.0)
    assert e.readings["FT-301"].pv == pytest.approx(0.0, abs=1e-9)
    assert pv(e, "AT-512") == pytest.approx(at512, rel=0.02)
    assert e.dyn.grid.inventory()[k] > 0.9 * inv0


def test_chemical_mass_balance():
    e = _open_meoh()
    run_until(e, 3 * 3600.0)
    e.command_valve("CIV-301", "close")
    run_until(e, 4 * 3600.0)
    b = e.snapshot(False)["transport_balance"]["methanol"]
    assert b["injected_m3"] > 1.0
    assert b["in_line_m3"] + b["exported_m3"] + b["to_reservoir_m3"] == pytest.approx(b["injected_m3"], rel=1e-6)


def test_small_injection_does_not_create_large_production_pressure_change():
    e = _open_meoh()
    p0 = pv(e, "PT-101")
    run_until(e, 600.0)
    q_inj = e.readings["FT-301"].pv
    q_prod = e.readings["FT-101"].pv
    assert 0 < q_inj < 0.06 * q_prod
    assert abs(pv(e, "PT-101") - p0) < 3e5  # < 3 bar


def test_downstream_flow_includes_injected_stream():
    e = eng("dyn_d_flowrate_change")  # biocide injected at N_DC, upstream of FT-101's link
    run_until(e, 60.0)
    q_choke = e.dyn.element_flow("CHOKE")
    q_bio = e.dyn.element_flow("NRV303")
    assert pv(e, "FT-101") == pytest.approx(q_choke + q_bio, rel=1e-4)


def test_insufficient_supply_pressure_prevents_injection():
    e = eng("dyn_c_methanol_injection")
    e.set_pump("methanol", discharge_pressure_pa=u.bara_to_pa(80.0))  # below tree-bore pressure
    e.command_valve("CIV-301", "open")
    run_until(e, 120.0)
    c = next(c for c in e.snapshot(False)["chemicals"] if c["id"] == "methanol")
    assert c["available_differential_pa"] < 0
    assert c["injection_flow_m3s"] <= 0.0
    assert c["status"] == "insufficient_differential"


# ============================================================== valves
def test_commanded_and_actual_position_distinct_during_travel():
    e = eng()
    e.command_valve("CHK-101", "set_position", 60.0)
    run_until(e, 30.0)
    a = e.restrictions["CHK-101"].actuator
    assert a.commanded_pct == 60.0 and 30.0 < a.position_pct < 60.0
    c1 = e.restrictions["CHK-101"].capacity
    run_until(e, 60.0)
    assert e.restrictions["CHK-101"].capacity > c1  # resistance changes with travel


def test_valve_end_of_travel_and_process_settled_are_separate_events():
    e = eng()
    e.command_valve("CHK-101", "set_position", 40.0)
    run_until(e, 6 * 3600.0)
    ev = e.events.all()
    reached = [x for x in ev if x.category == "valve" and x.component == "CHK-101"]
    settled = [x for x in ev if x.category == "process"]
    assert reached and settled
    assert settled[0].sim_time_s > reached[0].sim_time_s + 60.0


# ============================================================== thermal
def test_flowline_temperature_matches_exponential_heat_loss():
    """Steady plug flow with uniform U and ambient:
    T(L) = T_amb + (T_in - T_amb) exp(-U pi D L / (mdot cp)). 125 upwind
    cells: tanks-in-series error < 0.05 K for this NTU."""
    e = eng()
    g = e.dyn.grid
    cells = g.cell_of_pipe["FL-101"]
    fl = next(x for x in e.topology.path if x.id == "FL-101")
    q = e.dyn.element_flow("FL-101")
    mdot = q * e.fluid.rho
    t_in = e.dyn.node_temperature("N_DC")
    ntu = fl.overall_htc * math.pi * fl.geometry.diameter * fl.geometry.length / (mdot * e.fluid.cp)
    exact = fl.ambient_in + (t_in - fl.ambient_in) * math.exp(-ntu)
    assert g.T[cells[-1]] == pytest.approx(exact, abs=0.05)


def test_mixing_at_equal_temperature_creates_no_temperature_change():
    cfg = get_scenario("dyn_c_methanol_injection")
    e0 = SimulationEngine(cfg)
    t_cav = e0.dyn.node_temperature("N_PMV_PWV")
    cfg.chemicals[0].injection_temperature_c = u.k_to_c(t_cav)
    e = SimulationEngine(cfg)
    e.start()
    t_up0, t0 = e.readings["TT-101"].pv, e.readings["TT-103"].pv
    thr0 = float(e.dyn.grid.dT_throttle.sum())
    e.command_valve("CIV-301", "open")
    run_until(e, 1800.0)
    assert e.readings["FT-301"].pv > 0
    # throttling heating changes too (higher flow -> larger choke dP)
    d_thr = float(e.dyn.grid.dT_throttle.sum()) - thr0
    # The only temperature change is the genuine coupled effect seen upstream
    # too (the injected stream raises tree pressure, slightly reducing
    # reservoir inflow, so the tubing loses a little more heat). Mixing at
    # equal temperature adds nothing on top of it.
    d_up = e.readings["TT-101"].pv - t_up0
    d_dn = e.readings["TT-103"].pv - t0
    # residual < 0.1 K: second-order effects (mixture rho*cp in the throttling
    # term, stream drifting from the fixed injection temperature) - compare
    # with ~2.6 K of genuine cooling when the methanol is injected cold.
    assert abs(d_dn - d_up - d_thr) < 0.1


def test_cold_injection_cools_downstream_but_not_upstream():
    e = _open_meoh()
    t_up0, t_dn0 = e.readings["TT-101"].pv, e.readings["TT-103"].pv
    q_tub0 = e.dyn.element_flow("TBG-UPPER")
    run_until(e, 1800.0)
    d_up = e.readings["TT-101"].pv - t_up0
    d_dn = e.readings["TT-103"].pv - t_dn0
    # upstream: only the small coupled effect of the reduced reservoir inflow
    assert e.dyn.element_flow("TBG-UPPER") < q_tub0
    assert abs(d_up) < 0.5
    # downstream: enthalpy mixing with cold methanol
    assert d_dn < d_up - 1.0


def test_higher_reservoir_temperature_warms_the_tree_progressively():
    e = eng()
    t0 = e.readings["TT-101"].pv
    e.set_boundary(reservoir_temperature_k=e.ipr.t_res + 10.0)
    run_until(e, 60.0)
    t1 = e.readings["TT-101"].pv
    run_until(e, 4 * 3600.0)
    t2 = e.readings["TT-101"].pv
    assert t0 <= t1 < t2 < t0 + 10.0


# ======================================================= clock / determinism
def test_dynamic_result_independent_of_tick_partitioning():
    a, b = eng(), eng()
    for x in (a, b):
        x.command_valve("PWV-101", "close")
    a.advance(600.0)
    for _ in range(2400):
        b.advance(0.25)
    assert a.time_s == b.time_s == 600.0
    assert np.array_equal(a.dyn.net.P, b.dyn.net.P)
    assert np.array_equal(a.dyn.grid.T, b.dyn.grid.T)


def test_speed_changes_wall_ratio_not_results():
    a, b = eng(), eng()
    b.set_time_scale(600.0)
    for x in (a, b):
        x.command_valve("CHK-101", "set_position", 50.0)
        x.advance(300.0)
    assert np.array_equal(a.dyn.net.P, b.dyn.net.P)


def test_pause_resume_reset():
    e = eng()
    e.command_valve("PWV-101", "close")
    e.advance(100.0)
    e.pause()
    p = pv(e, "PT-101")
    e.advance(500.0)
    assert e.time_s == 100.0 and pv(e, "PT-101") == p
    e.resume()
    e.advance(50.0)
    assert e.time_s == 150.0
    e.reset()
    fresh = SimulationEngine(get_scenario("subsea_dynamic_base"))
    assert e.time_s == 0.0 and e.status == "ready"
    assert np.array_equal(e.dyn.net.P, fresh.dyn.net.P)


def test_mode_switch_keeps_steady_model_available():
    e = SimulationEngine(get_scenario("subsea_dynamic_base"))
    e.set_mode("steady")
    assert e.dyn is None and e.mode == "steady"
    e.start()
    e.command_valve("PWV-101", "close")
    e.advance(60.0)
    assert e.hyd.q == 0.0  # quasi-steady: closed path -> zero flow immediately after travel
    assert e.readings["PT-401"].status == "NOT_MODELLED"
    with pytest.raises(CommandRejected):
        e.set_pump("methanol", running=False)


# ============================================================= annulus
def test_annulus_independent_of_production_when_isolated():
    e = eng()
    p0 = pv(e, "PT-401")
    e.command_valve("PWV-101", "close")
    run_until(e, 600.0)
    assert pv(e, "PT-401") == pytest.approx(p0, abs=0.5e5)


def test_annulus_bleed_down_is_gradual():
    e = eng()
    p0 = pv(e, "PT-401")
    e.command_valve("AMV-101", "open")
    e.command_valve("AWV-101", "open")
    run_until(e, 30.0)
    p30 = pv(e, "PT-401")
    run_until(e, 3600.0)
    p3600 = pv(e, "PT-401")
    vent = u.bara_to_pa(15.0)
    assert p0 > p30 > p3600 > vent - 1e5


def test_crossover_connects_annulus_to_production_bore():
    e = eng()
    e.command_valve("AMV-101", "open")
    e.command_valve("XOV-101", "open")
    run_until(e, 1800.0)
    assert abs(pv(e, "PT-401") - pv(e, "PT-104")) < abs(u.bara_to_pa(80.0) - u.bara_to_pa(116.4))


# ============================================================ integrity
def _prepare_pmv_inflow(e: SimulationEngine) -> None:
    e.command_valve("PMV-101", "close")
    run_until(e, e.time_s + 300.0)  # cavity bleeds to flowline through PWV
    e.command_valve("PWV-101", "close")
    run_until(e, e.time_s + 60.0)


def test_inflow_test_passes_with_tight_valve_and_fails_with_leak():
    results = {}
    for scen in ("subsea_dynamic_base", "dyn_f_leaking_pmv"):
        e = eng(scen)
        _prepare_pmv_inflow(e)
        e.start_integrity_test(type="inflow", transmitter="PT-104", stabilisation_s=120, duration_s=900, max_change_bar=3)
        t = e.integrity.tests[-1]
        assert t.phase == "stabilising"
        run_until(e, e.time_s + 600.0)
        assert t.phase == "holding" and len(t.trace) > 100  # evolves over simulated time
        run_until(e, e.time_s + 600.0)
        results[scen] = t
    ok, leak = results["subsea_dynamic_base"], results["dyn_f_leaking_pmv"]
    assert ok.phase == "passed" and leak.phase == "failed"
    assert leak.result["change_bar"] > ok.result["change_bar"] + 3.0
    assert abs(leak.result["net_leak_l_per_min"]) > 10 * abs(ok.result["net_leak_l_per_min"])


def test_isolation_must_be_verified():
    e = eng()
    with pytest.raises(CommandRejected, match="isolation NOT verified"):
        e.start_integrity_test(type="pressure_hold", transmitter="PT-104")


def test_isolation_loss_aborts_test():
    e = eng()
    _prepare_pmv_inflow(e)
    e.start_integrity_test(type="inflow", transmitter="PT-104", stabilisation_s=60, duration_s=600)
    run_until(e, e.time_s + 30.0)
    e.command_valve("PWV-101", "open")
    run_until(e, e.time_s + 20.0)
    assert e.integrity.tests[-1].phase == "aborted"


def test_pressure_hold_after_methanol_pressurisation():
    e = eng()
    e.command_valve("PMV-101", "close")
    e.command_valve("PWV-101", "close")
    run_until(e, 120.0)
    e.command_valve("CIV-301", "open")
    run_until(e, 400.0)
    assert pv(e, "PT-104") > u.bara_to_pa(200.0)  # cavity packed up by the injection pump
    e.command_valve("CIV-301", "close")
    run_until(e, 430.0)
    e.start_integrity_test(type="pressure_hold", transmitter="PT-104", stabilisation_s=300, duration_s=900, max_change_bar=5)
    run_until(e, 430.0 + 1250.0)
    t = e.integrity.tests[-1]
    assert t.phase == "passed", t.message
    assert "thermal" in t.message


def test_stroke_test_detects_slow_actuator():
    good, slow = eng(), eng("dyn_f_leaking_pmv")
    for e in (good, slow):
        e.start_integrity_test(type="stroke", valve="PWV-101", stroke_tolerance_pct=15)
        run_until(e, 120.0)
    assert good.integrity.tests[-1].phase == "passed"
    assert slow.integrity.tests[-1].phase == "failed"
    assert slow.integrity.tests[-1].result["measured_stroke_time_s"] == pytest.approx(44.0, abs=1.01)


# ========================================================= instruments
def test_sensor_lag_is_additional_to_process_dynamics():
    e = eng()
    run_until(e, 60.0)
    e.set_boundary(reservoir_temperature_k=e.ipr.t_res + 20.0)
    run_until(e, 3 * 3600.0)
    r = e.readings["TT-101"]
    # TT has a 15 s lag: during a slow process change output trails PV slightly
    assert r.value <= r.pv + 0.06


def test_analyser_update_interval_holds_output():
    e = _open_meoh()
    run_until(e, 600.0)
    vals = []
    for _ in range(10):
        e.advance(1.0)
        vals.append(e.readings["AT-510"].value)
    assert len(set(vals)) <= 2  # 30 s sample-and-hold


# =================================================== tree: swab, SLV, MIV
def test_swab_valve_isolates_tree_cap_until_opened():
    e = eng()
    cap0 = pv(e, "PT-105")
    assert cap0 == pytest.approx(u.bara_to_pa(60.0), abs=0.2e5)  # cap held at its own pressure
    run_until(e, 300.0)
    assert pv(e, "PT-105") == pytest.approx(cap0, abs=0.1e5)  # tight SV: no change
    e.command_valve("SV-101", "open")
    run_until(e, 360.0)
    assert pv(e, "PT-105") == pytest.approx(pv(e, "PT-104"), abs=0.2e5)  # equalised with the bore
    assert any(x.category == "training_rule" and "SV-101" in x.message for x in e.events.all())  # opened against dP


def test_swab_valve_inflow_test_passes_when_tight():
    e = eng()
    # the monitoring transmitter must sit inside the isolated test volume
    with pytest.raises(CommandRejected, match="does not measure inside"):
        e.start_integrity_test(type="inflow", transmitter="PT-104", test_node="N_SWAB_CAP")
    e2 = eng()
    e2.start_integrity_test(type="inflow", transmitter="PT-105", stabilisation_s=60, duration_s=300, max_change_bar=3)
    run_until(e2, 420.0)
    assert e2.integrity.tests[-1].phase == "passed"


def test_service_line_valve_controls_annulus_bleed():
    e = eng()
    e.command_valve("SLV-101", "close")
    e.command_valve("AMV-101", "open")
    e.command_valve("AWV-101", "open")
    run_until(e, 600.0)
    p_closed = pv(e, "PT-401")
    assert p_closed > u.bara_to_pa(60.0)  # SLV closed: no bleed to the host
    e.command_valve("SLV-101", "open")
    run_until(e, 3600.0)
    assert pv(e, "PT-401") < p_closed - 10e5  # bleeding through the service line


def test_methanol_into_annulus_service_line_is_accounted_separately():
    e = eng()
    e.command_valve("MIV-301", "open")
    run_until(e, 1800.0)
    c = next(x for x in e.snapshot(False)["chemicals"] if x["id"] == "methanol")
    route = c["annulus_route"]
    assert route["status"] == "injecting" and route["flow_m3s"] > 0 and route["cumulative_m3"] > 0.1
    # production route untouched (a trapped line segment may decompress by picolitres through the NRV)
    assert c["status"] == "isolated" and c["cumulative_injected_m3"] < 1e-9
    b = e.snapshot(False)["transport_balance"]["methanol"]
    assert b["injected_m3"] < 1e-9 and b["in_line_m3"] < 1e-9  # production line stays clean
    assert e.readings["FT-305"].pv == pytest.approx(route["flow_m3s"], rel=1e-6)


def test_methanol_annulus_route_can_pressurise_the_annulus():
    e = eng()
    p0 = pv(e, "PT-401")
    e.command_valve("SLV-101", "close")
    e.command_valve("AWV-101", "open")
    e.command_valve("AMV-101", "open")
    e.command_valve("MIV-301", "open")
    run_until(e, 1800.0)
    assert pv(e, "PT-401") > p0 + 20e5  # bullheading: annulus pressure rises toward the pump pressure
