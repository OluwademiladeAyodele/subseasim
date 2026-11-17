"""Virtual multiphase flow meter: measurement model, standard-condition
conversion, uncertainty, diagnostics, faults and integration with the
simulated production system."""

from __future__ import annotations

import math
import warnings

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.scenario import MPFMConfig
from app.scenarios.loader import get_scenario
from app.simulation.engine import SimulationEngine
from app.simulation.fluid_properties.black_oil import BlackOilFluid, BlackOilParams
from app.simulation.mpfm.meter import MPFM, chisholm_slip, momentum_density, quality_from_void, void_fraction

warnings.simplefilter("ignore", RuntimeWarning)
SCN = "xt_230xp22b_multiphase"
FLUID = BlackOilParams("t", 35.0, 0.75, 120.0, 0.30)
P, T, W = 60e5, 330.0, 9.5


def _meter(**over) -> MPFM:
    cfg = dict(tag="MPFM-T", location_node="N_ARR", pressure_sigma_bar=0, temperature_sigma_k=0, dp_sigma_pct_full_scale=0,
               gamma_count_rate_low_cps=1e15, gamma_count_rate_high_cps=1e15, integration_time_s=2.0, update_interval_s=2.0)
    cfg.update(over)
    return MPFM(MPFMConfig(**cfg), BlackOilFluid(FLUID), 120.0, 0.30)


def _run(m: MPFM, n: int = 10, p=P, t=T, w=W, gor=120.0, wc=0.30):
    for k in range(n):
        m.update(2.0 * (k + 1), p, t, w, gor, wc)
    return m.derived(m.reading), m.truth_derived(m.truth)


# --------------------------------------------------------------- physics
def test_slip_relations_are_consistent():
    rho_l, rho_g = 800.0, 60.0
    s = chisholm_slip(rho_l, rho_g)
    assert s == pytest.approx((800 / 60) ** 0.25)
    for x in (0.01, 0.1, 0.5):
        a = void_fraction(x, rho_l, rho_g, s)
        assert quality_from_void(a, rho_l, rho_g, s) == pytest.approx(x, rel=1e-12)
        # with slip the in-situ gas fraction is below the no-slip (volumetric) gas fraction
        a_ns = void_fraction(x, rho_l, rho_g, 1.0)
        assert a < a_ns
    # no slip: momentum density equals the homogeneous density
    x = 0.1
    a = void_fraction(x, rho_l, rho_g, 1.0)
    assert momentum_density(x, a, rho_l, rho_g) == pytest.approx(a * rho_g + (1 - a) * rho_l, rel=1e-12)


def test_noise_free_matched_meter_reproduces_the_true_rates():
    """Meter PVT = true PVT, slip model = true slip model, no sensor noise:
    the flow computer must invert the simulated sensors exactly."""
    meas, true = _run(_meter())
    # negligible sensor noise remains (1e15 counts/s -> ~3e-8 attenuation noise)
    for k in ("oil_sm3_d", "gas_sm3_d", "water_sm3_d", "mass_kg_s", "oil_m3_d", "gas_m3_d", "water_m3_d"):
        assert meas[k] == pytest.approx(true[k], rel=2e-4), k
    assert meas["water_cut"] == pytest.approx(true["water_cut"], abs=1e-5)
    assert meas["gor_sm3_sm3"] == pytest.approx(120.0, rel=2e-4)


def test_actual_versus_standard_conditions_use_the_black_oil_volume_factors():
    m = _meter()
    meas, _ = _run(m)
    s = m.meter_fluid.state(P, T)
    bo, bg, bw, rs = float(s.bo[0]), float(s.bg[0]), float(s.bw[0]), float(s.rs[0])
    assert meas["oil_sm3_d"] == pytest.approx(meas["oil_m3_d"] / bo, rel=1e-12)
    assert meas["water_sm3_d"] == pytest.approx(meas["water_m3_d"] / bw, rel=1e-12)
    assert meas["gas_sm3_d"] == pytest.approx(meas["gas_m3_d"] / bg + rs * meas["oil_sm3_d"], rel=1e-12)
    # line-condition gas volume is far smaller than the standard volume; oil shrinks at standard conditions
    assert meas["gas_m3_d"] < meas["gas_sm3_d"] / 20 and meas["oil_sm3_d"] < meas["oil_m3_d"]
    assert meas["water_cut"] == pytest.approx(meas["water_sm3_d"] / (meas["oil_sm3_d"] + meas["water_sm3_d"]))
    assert meas["gor_sm3_sm3"] == pytest.approx(meas["gas_sm3_d"] / meas["oil_sm3_d"])
    assert meas["gvf"] + meas["lvf"] == pytest.approx(1.0)


def test_homogeneous_meter_misreads_slipping_flow():
    """A meter assuming no slip under-reads gas and over-reads liquid when the
    gas phase slips past the liquid (in-situ gas fraction < flowing fraction)."""
    meas, true = _run(_meter(meter_slip_model="homogeneous"))
    assert meas["gas_sm3_d"] < 0.97 * true["gas_sm3_d"]
    assert meas["liquid_sm3_d"] > 1.03 * true["liquid_sm3_d"]


def test_water_salinity_mismatch_biases_water_cut_and_calibration_removes_it():
    m = _meter()
    salty = BlackOilFluid(BlackOilParams("t", 35.0, 0.75, 120.0, 0.30, water_salinity_wt_pct=8.0))
    m.set_true_fluid(salty)
    meas, true = _run(m)
    # saltier water attenuates more at low energy: the meter (calibrated for 3.5 wt%) sees too much water
    assert meas["water_cut"] > true["water_cut"] + 0.05
    m.calibrate(100.0, salty, 120.0, 0.30)
    meas, true = _run(m, n=12)
    assert meas["water_cut"] == pytest.approx(true["water_cut"], abs=1e-5)


def test_uncertainty_grows_with_gvf_and_at_low_flow():
    lo_gvf = _meter(gamma_count_rate_low_cps=2e5, gamma_count_rate_high_cps=5e4)
    _run(lo_gvf, gor=30.0)
    u_lo = lo_gvf.uncertainty
    hi_gvf = _meter(gamma_count_rate_low_cps=2e5, gamma_count_rate_high_cps=5e4)
    _run(hi_gvf, gor=400.0)
    u_hi = hi_gvf.uncertainty
    assert u_hi["gvf"] > u_lo["gvf"]
    assert u_hi["liquid_sm3_d"] > u_lo["liquid_sm3_d"]
    # low flow: the fixed dP transmitter noise dominates
    big = _meter(gamma_count_rate_low_cps=2e5, gamma_count_rate_high_cps=5e4, dp_sigma_pct_full_scale=0.05)
    _run(big, w=W)
    small = _meter(gamma_count_rate_low_cps=2e5, gamma_count_rate_high_cps=5e4, dp_sigma_pct_full_scale=0.05)
    _run(small, w=W / 4)
    assert small.uncertainty["mass_kg_s"] > big.uncertainty["mass_kg_s"]
    # every uncertainty is a positive, finite percentage
    assert all(math.isfinite(v) and v >= 0 for v in u_hi.values())


def test_uncertainty_budget_matches_a_direct_perturbation():
    """GUM first-order propagation: the dP contribution to the mass-flow
    uncertainty equals 0.5 x (sigma_dP / dP) for W ~ sqrt(dP)."""
    m = _meter(dp_sigma_pct_full_scale=0.05, slip_uncertainty_table=[(0.0, 0.0), (1.0, 0.0)])
    _run(m)
    dp = m.meas_inputs["dp_pa"]
    sig = math.hypot(0.05 / 100 * 5.0e5, 0.0025 * dp)
    assert m.budget["mass_kg_s"]["dp"] == pytest.approx(100 * 0.5 * sig / dp, rel=0.02)


def test_sensor_noise_is_reproducible_and_inside_the_uncertainty():
    a, _ = _run(_meter(gamma_count_rate_low_cps=2e5, gamma_count_rate_high_cps=5e4, dp_sigma_pct_full_scale=0.05, seed=7), n=30)
    b, true = _run(_meter(gamma_count_rate_low_cps=2e5, gamma_count_rate_high_cps=5e4, dp_sigma_pct_full_scale=0.05, seed=7), n=30)
    assert a == b  # same seed, same readings
    m = _meter(gamma_count_rate_low_cps=2e5, gamma_count_rate_high_cps=5e4, dp_sigma_pct_full_scale=0.05, seed=7)
    meas, true = _run(m, n=30)
    for k in ("oil_sm3_d", "gas_sm3_d", "water_sm3_d"):
        assert abs(meas[k] - true[k]) / true[k] * 100 < m.uncertainty[k]


# -------------------------------------------------------------- diagnostics
def test_faults_and_quality():
    m = _meter()
    _run(m)
    assert m.quality == "GOOD"
    m.set_faults(gamma_failed=True)
    m.update(100.0, P, T, W, 120.0, 0.30)
    assert m.quality == "BAD" and m.reading is None
    assert m.snapshot(100.0)["measured"] is None
    m.set_faults(gamma_failed=False, dp_stuck=True)
    _run(m, n=31, w=W * 1.2)
    assert m.quality == "DEGRADED" and any(f["code"] == "DP_FROZEN" for f in m.flags)
    m.set_faults(dp_stuck=False, dp_offset_bar=0.05)
    meas, true = _run(m, n=15)
    assert meas["mass_kg_s"] > true["mass_kg_s"] * 1.05  # positive offset over-reads flow
    m.calibrate(500.0, BlackOilFluid(FLUID), 120.0, 0.30)
    meas, true = _run(m, n=15)
    assert meas["mass_kg_s"] == pytest.approx(true["mass_kg_s"], rel=1e-4)
    m.set_faults(pt_failed=True)
    _run(m, n=2)
    assert m.quality == "DEGRADED" and any(f["code"] == "PT_FAILED" for f in m.flags)


def test_envelope_checks():
    m = _meter()
    _run(m, w=0.01)
    assert any(f["code"] == "LOW_FLOW_CUTOFF" for f in m.flags) and m.derived(m.reading)["oil_sm3_d"] == 0
    m = _meter()
    _run(m, gor=2000.0, p=20e5)
    assert any(f["code"] == "GVF_OUT_OF_ENVELOPE" for f in m.flags)
    m = _meter(calibration_interval_days=1.0)
    m.update(3 * 86400.0, P, T, W, 120.0, 0.3)
    assert any(f["code"] == "CALIBRATION_DUE" for f in m.flags)


# -------------------------------------------------------------- integration
def test_meter_follows_the_simulated_production_system():
    e = SimulationEngine(get_scenario(SCN))
    e.start()
    e.advance(60)
    m0 = e.snapshot(False)["mpfm"]
    assert m0["quality"] == "GOOD" and m0["location_node"] == "N_ARR"
    # the meter's truth is the simulated flow at the manifold
    rep = e.snapshot(False)["multiphase"]["rates_arrival"]
    assert m0["true"]["oil_sm3_d"] == pytest.approx(rep["oil_sm3_d"], rel=0.01)
    oil0 = m0["measured"]["oil_sm3_d"]
    e.command_valve("CHK-101", "set_position", 70)
    e.advance(1800)
    m1 = e.snapshot(False)["mpfm"]
    assert m1["measured"]["oil_sm3_d"] > 1.3 * oil0
    assert abs(m1["measured"]["oil_sm3_d"] - m1["true"]["oil_sm3_d"]) / m1["true"]["oil_sm3_d"] * 100 < m1["uncertainty_pct"]["oil_sm3_d"]
    # shut-in: the manifold flow decays and the meter reaches its low-flow cut-off
    e.command_valve("PWV-101", "close")
    e.advance(1800)
    m2 = e.snapshot(False)["mpfm"]
    assert any(f["code"] in ("LOW_FLOW", "LOW_FLOW_CUTOFF") for f in m2["flags"])
    # history carries measured and true values for trending
    s = e.history.all()[-1]
    assert "mpfm:oil_sm3_d" in s and "mpfm_true:oil_sm3_d" in s


def test_water_cut_change_reaches_the_meter_with_the_fluid():
    e = SimulationEngine(get_scenario(SCN))
    e.start()
    e.advance(30)
    wc0 = e.snapshot(False)["mpfm"]["true"]["water_cut"]
    e.set_black_oil(water_cut=0.6)
    e.advance(120)
    assert e.snapshot(False)["mpfm"]["true"]["water_cut"] == pytest.approx(wc0, abs=0.005)  # not arrived yet
    e.advance(4 * 3600)
    m = e.snapshot(False)["mpfm"]
    assert m["true"]["water_cut"] > 0.5 and m["measured"]["water_cut"] > 0.5


def test_single_phase_model_reports_not_modelled():
    e = SimulationEngine(get_scenario("xt_230xp22b"))
    assert e.snapshot(False)["mpfm"]["quality"] == "NOT_MODELLED"


def test_mpfm_api():
    with TestClient(app) as client:
        sid = client.post("/api/sessions", json={"scenario_id": SCN}).json()["session_id"]
        r = client.put(f"/api/sessions/{sid}/mpfm/faults", json={"gamma_failed": True})
        assert r.status_code == 200 and r.json()["state"]["mpfm"]["quality"] == "BAD"
        r = client.put(f"/api/sessions/{sid}/mpfm/faults", json={"gamma_failed": False})
        r = client.post(f"/api/sessions/{sid}/mpfm/calibrate")
        assert r.status_code == 200 and r.json()["state"]["mpfm"]["quality"] == "GOOD"
        assert client.put(f"/api/sessions/{sid}/mpfm/faults", json={"dp_offset_bar": 5}).status_code == 422
        sid2 = client.post("/api/sessions", json={"scenario_id": "xt_230xp22b"}).json()["session_id"]
        assert client.post(f"/api/sessions/{sid2}/mpfm/calibrate").status_code == 409


__all__ = ["np"]
