"""Cavitation / flashing screening at the production choke: reference
values, regimes, valve-specific limits and engine integration."""

from __future__ import annotations

import warnings

import pytest

from app.models.sand import CavitationInputs, SandChokeInputs
from app.simulation.choke import cavitation as cv
from app.simulation.choke.cavitation import CavitationPoint

warnings.simplefilter("ignore", RuntimeWarning)


# ------------------------------------------------------------ references
@pytest.mark.parametrize("t_k, p_mpa", [(300.0, 0.353658941e-2), (500.0, 0.263889776e1), (600.0, 0.123443146e2)])
def test_water_saturation_pressure_matches_iapws_if97_verification_values(t_k, p_mpa):
    assert cv.water_saturation_pressure(t_k) == pytest.approx(p_mpa * 1e6, rel=1e-8)


def test_iec_ff_factor_and_choked_differential():
    pv = 0.2e5
    assert cv.ff_factor(pv, cv.PC_WATER) == pytest.approx(0.96 - 0.28 * (0.2 / 220.64) ** 0.5)
    pt = CavitationPoint(p1=100e5, p2=40e5, t1=333.15, opening_pct=40, pb_correlation=50e5, gvf_inlet=0.0, water_cut=0.3)
    r = cv.screen(pt, CavitationInputs(fl=0.9))
    pv_w = cv.water_saturation_pressure(333.15)
    ff = cv.ff_factor(pv_w, cv.PC_WATER)
    assert r["water"]["dp_choked_bar"] == pytest.approx(0.81 * (100e5 - ff * pv_w) / 1e5)
    assert r["vena_contracta_bara"] == pytest.approx((100e5 - 60e5 / 0.81) / 1e5)
    assert r["water"]["sigma"] == pytest.approx((100e5 - pv_w) / 60e5)


def test_fl_table_is_interpolated_by_opening():
    assert cv.interpolate_fl([(10, 0.95), (50, 0.85), (100, 0.75)], 30) == pytest.approx(0.90)
    assert cv.interpolate_fl([(10, 0.95), (100, 0.75)], 5) == 0.95
    assert cv.interpolate_fl([(10, 0.95), (100, 0.75)], 120) == 0.75


# --------------------------------------------------------------- regimes
def _pt(**kw):
    base = dict(p1=150e5, p2=60e5, t1=343.15, opening_pct=40.0, pb_correlation=100e5, gvf_inlet=0.0, water_cut=0.3)
    return CavitationPoint(**(base | kw))


def test_regimes_follow_the_pressures():
    inp = CavitationInputs(fl=0.9)
    assert cv.screen(_pt(p1=90e5, gvf_inlet=0.05), inp)["oil"]["regime"] == "two_phase_inlet"
    assert cv.screen(_pt(p2=60e5), inp)["oil"]["regime"] == "outgassing"  # outlet below Pb
    # outlet above Pb, vena contracta below it: P_vc = 150 - 30/0.81 = 113 bar < Pb 115
    assert cv.screen(_pt(p2=120e5, pb_correlation=115e5), inp)["oil"]["regime"] == "gaseous_cavitation"
    assert cv.screen(_pt(p2=140e5, pb_correlation=50e5), inp)["oil"]["regime"] == "none"
    # water vapour cavitation needs a deep vena contracta: low FL and a large differential
    r = cv.screen(_pt(p1=150e5, p2=20e5, pb_correlation=10e5), CavitationInputs(fl=0.6))
    assert r["vena_contracta_bara"] < r["water"]["pv_bara"] < r["p2_bara"]
    assert r["water"]["regime"] == "vapour_cavitation" and r["regime"] == "vapour_cavitation"


def test_without_fl_only_the_physics_checks_are_made():
    r = cv.screen(_pt(p2=140e5, pb_correlation=50e5), CavitationInputs())
    assert r["vena_contracta_bara"] is None and r["water"]["dp_choked_bar"] is None
    assert any("FL" in m for m in r["missing"])
    assert r["oil"]["regime"] == "unknown" and r["risk"] == "Unavailable"
    # the outlet-vs-bubble-point check needs no FL
    assert cv.screen(_pt(), CavitationInputs())["oil"]["regime"] == "outgassing"


def test_sigma_limits_are_valve_specific_and_never_assumed():
    pt = _pt(p1=150e5, p2=60e5, pb_correlation=50e5)  # sigma_w ~ 1.67
    r = cv.screen(pt, CavitationInputs(fl=0.9))
    assert r["water"]["level"] == "Unavailable" and any("sigma limits" in m for m in r["missing"])
    lim = dict(sigma_incipient=2.0, sigma_constant=1.8, sigma_damage=1.5)
    assert cv.screen(pt, CavitationInputs(fl=0.9, **lim))["water"]["level"] == "Constant cavitation"
    assert cv.screen(_pt(p1=150e5, p2=40e5, pb_correlation=30e5), CavitationInputs(fl=0.9, **lim))["water"]["level"] == \
        "Manufacturer damage limit exceeded"
    assert cv.screen(_pt(p1=150e5, p2=100e5, pb_correlation=30e5), CavitationInputs(fl=0.9, **lim))["water"]["level"] == "Not indicated"


def test_free_gas_makes_the_sigma_result_indicative():
    lim = dict(sigma_incipient=2.0, sigma_constant=1.8, sigma_damage=1.5)
    r = cv.screen(_pt(p1=90e5, p2=40e5, gvf_inlet=0.1), CavitationInputs(fl=0.9, **lim))
    assert r["inlet_free_gas"] and r["risk"].endswith("(indicative - free gas at the inlet)")
    assert "local pressure minima" in r["water"]["text"]


def test_sigma_limits_must_be_ordered():
    with pytest.raises(ValueError):
        CavitationInputs(sigma_incipient=1.5, sigma_constant=1.8)


def test_pvt_bubble_point_overrides_the_correlation_and_band_flags_sensitivity():
    r = cv.screen(_pt(p2=95e5), CavitationInputs(fl=0.9, bubble_point_bara=98.0))
    assert r["oil"]["pb_source"] == "PVT report entry" and r["oil"]["regime"] == "outgassing"
    assert r["sensitivity"]["outlet_below_pb_low"] is False and r["sensitivity"]["outlet_below_pb_high"] is True
    assert any("uncertainty band" in n for n in r["notes"])


def test_dry_oil_has_no_water_result():
    assert cv.screen(_pt(water_cut=0.0), CavitationInputs(fl=0.9))["water"] is None


def test_old_saves_without_a_cavitation_block_load():
    assert SandChokeInputs.model_validate({}).cavitation.fl is None


# ------------------------------------------------------------ integration
def test_engine_reports_cavitation_screening_from_the_simulated_choke():
    from app.scenarios.loader import get_scenario
    from app.simulation.engine import SimulationEngine

    e = SimulationEngine(get_scenario("xt_230xp22b_multiphase"))
    e.load_sand_example()
    e.start()
    e.advance(300)
    c = e.snapshot(False)["sand_choke"]["cavitation"]
    ch = e.restrictions["CHK-101"]
    assert c["available"] and c["status"] == "Correlation-based screening"
    assert c["opening_pct"] == pytest.approx(ch.actuator.position_pct)
    assert c["p1_bara"] > c["p2_bara"] > 1.0
    assert c["oil"]["regime"] in ("two_phase_inlet", "outgassing", "gaseous_cavitation", "none")
    # opening the choke lowers the differential: sigma rises
    s0 = c["water"]["sigma"]
    e.command_valve("CHK-101", "set_position", 70)
    e.advance(900)
    c2 = e.snapshot(False)["sand_choke"]["cavitation"]
    assert c2["dp_bar"] < c["dp_bar"] and c2["water"]["sigma"] > s0
