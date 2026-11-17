"""Sand production, screens, detection, transport and choke erosion.

Independent references: Willson et al. (2002) critical BHFP evaluated by
hand, DNV-RP-O501 formulas evaluated by hand, unit conversions by hand,
log-normal quantiles; plus conservation, sensitivity, calibration and
decision-logic checks and the integration with the simulated well."""

from __future__ import annotations

import math
import warnings

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.sand import ChokeTrimInputs, CompletionInputs, GeomechanicsInputs, HoleRow, SandChokeInputs, SandInputs
from app.scenarios.loader import get_scenario
from app.simulation.engine import SimulationEngine
from app.simulation.sand import erosion as er
from app.simulation.sand import production as sp

warnings.simplefilter("ignore", RuntimeWarning)
SCN = "xt_230xp22b_multiphase"
G = GeomechanicsInputs(depth_tvd_m=3700, overburden_gradient_bar_m=0.18, min_horizontal_stress_gradient_bar_m=0.15,
                       initial_reservoir_pressure_bara=380, stress_path_coefficient=0.6, twc_strength_mpa=27.0, biot_coefficient=0.9,
                       poisson_ratio=0.25, water_weakening_fraction=0.3)


# ------------------------------------------------------------ onset
def test_critical_bhfp_matches_hand_calculation():
    """Willson et al. (2002): CBHFP = (3 s1 - s3 - U - A Pr) / (2 - A),
    U = 3.1 TWC, A = alpha (1 - 2 nu) / (1 - nu)."""
    pr, pw, wc = 380e5, 330e5, 0.3
    o = sp.sanding_onset(G, pr, pw, wc)
    sv, sh = 0.18e5 * 3700, 0.15e5 * 3700
    u = 3.1 * 27e6 * (1 - 0.3 * wc)
    a = 0.9 * (1 - 0.5) / 0.75
    cbhfp = (3 * sv - sh - u - a * pr) / (2 - a)
    assert o.available and o.cbhfp_pa == pytest.approx(cbhfp, rel=1e-12)
    assert o.critical_drawdown_pa == pytest.approx(pr - cbhfp, rel=1e-12)
    assert o.risk_index == pytest.approx((pr - pw) / (pr - cbhfp), rel=1e-12)


def test_onset_responds_to_strength_depletion_and_water():
    base = sp.sanding_onset(G, 380e5, 330e5, 0.0).critical_drawdown_pa
    stronger = sp.sanding_onset(G.model_copy(update={"twc_strength_mpa": 35.0}), 380e5, 330e5, 0.0).critical_drawdown_pa
    depleted = sp.sanding_onset(G, 300e5, 260e5, 0.0).critical_drawdown_pa
    wet = sp.sanding_onset(G, 380e5, 330e5, 0.8).critical_drawdown_pa
    assert stronger > base  # stronger rock tolerates more drawdown
    assert depleted < base  # depletion raises the effective stress concentration
    assert wet < base  # water weakening


def test_missing_geomechanics_gives_unavailable_with_reasons():
    o = sp.sanding_onset(GeomechanicsInputs(depth_tvd_m=3000), 300e5, 250e5, 0.0)
    assert not o.available
    assert any("overburden" in m for m in o.missing) and any("strength" in m for m in o.missing)
    o = sp.sanding_onset(G.model_copy(update={"twc_strength_mpa": None, "ucs_mpa": 10.0, "twc_ucs_ratio": None}), 300e5, 250e5, 0.0)
    assert not o.available  # UCS without the site TWC/UCS ratio is not enough
    o = sp.sanding_onset(G.model_copy(update={"biot_coefficient": None, "poisson_ratio": None}), 380e5, 330e5, 0.0)
    assert o.available and len(o.assumed) == 2  # defaults are disclosed


# ------------------------------------------------------- PSD & screens
def test_psd_fit_reproduces_the_entered_quantiles():
    psd = sp.fit_psd(SandInputs(d10_um=60, d50_um=150, d90_um=375))  # symmetric in log space
    assert psd.quantile(0.5) * 1e6 == pytest.approx(150, rel=1e-6)
    assert psd.quantile(0.1) * 1e6 == pytest.approx(60, rel=1e-3)
    assert psd.quantile(0.9) * 1e6 == pytest.approx(375, rel=1e-3)
    assert sp.fit_psd(SandInputs(d50_um=150)) is None  # one point is not a distribution


def test_screen_retention_and_damage():
    psd = sp.fit_psd(SandInputs(d10_um=60, d50_um=150, d90_um=300))
    c = CompletionInputs(screen_aperture_um=300, bridging_factor=2.0)
    r = sp.screen_passing(c, psd)
    assert r.passing_fraction == pytest.approx(psd.fraction_finer(150e-6), rel=1e-12) == pytest.approx(0.5, abs=1e-9)
    damaged = sp.screen_passing(c.model_copy(update={"screen_damage_fraction": 0.2}), psd)
    assert damaged.passing_fraction == pytest.approx(0.2 + 0.8 * 0.5)
    none = sp.screen_passing(CompletionInputs(completion_type="cased_perforated_no_screens"), psd)
    assert none.passing_fraction == 1.0
    finer = sp.screen_passing(c, sp.fit_psd(SandInputs(d10_um=30, d50_um=80, d90_um=200)))
    assert finer.passing_fraction > r.passing_fraction  # finer sand passes more
    assert not sp.screen_passing(CompletionInputs(), psd).available  # aperture missing


def test_measured_sand_unit_conversions_by_hand():
    q_liq = 1000 / 86400  # 1000 Sm3/d
    for unit, v, expected in [
        ("kg_d", 86.4, 0.001), ("kg_h", 3.6, 0.001), ("g_s", 1.0, 0.001),
        ("pptb", 10.0, 10 * 0.45359237 / (1000 * 0.158987294928) * q_liq),
        ("ppm_vol_liquid", 1.0, 1e-6 * q_liq * 2650),
    ]:
        s = SandInputs(mode="measured", measured_value=v, measured_unit=unit)
        assert sp.measured_rate_kg_s(s, q_liq, 9.0, 10.0) == pytest.approx(expected, rel=1e-12), unit
    assert sp.measured_rate_kg_s(SandInputs(mode="measured", measured_value=5, measured_unit="ppm_mass_total"), q_liq, 9, 10) == pytest.approx(5e-5)


def test_predicted_rate_zero_below_onset_and_needs_calibration():
    s = SandInputs(rate_coefficient_kg_m3=0.05, rate_exponent=1.5)
    below = sp.sanding_onset(G, 380e5, 370e5, 0.0)
    assert sp.predicted_formation_rate(s, below, 0.01)[0] == 0.0
    above = sp.sanding_onset(G, 380e5, 250e5, 0.0)
    m, _ = sp.predicted_formation_rate(s, above, 0.01)
    assert m == pytest.approx(0.05 * 0.01 * (above.risk_index - 1) ** 1.5)
    m, miss = sp.predicted_formation_rate(SandInputs(), above, 0.01)
    assert m is None and miss


# ----------------------------------------------------------- erosion
def test_dnv_formulas_by_hand():
    steel = er.MATERIALS["carbon_steel"]
    a = math.radians(30)
    f30 = 0.6 * (math.sin(a) + 7.2 * (math.sin(a) - math.sin(a) ** 2)) ** 0.6 * (1 - math.exp(-20 * a))
    assert er.f_alpha(a, "ductile") == pytest.approx(f30, rel=1e-12)
    assert er.erosion_ratio(steel, 20.0, 30.0) == pytest.approx(2.0e-9 * 20**2.6 * f30, rel=1e-12)
    assert er.f_alpha(math.radians(90), "brittle") == pytest.approx(1.0)
    # straight pipe: E = 2.5e-5 U^2.6 D^-2 m_p  [mm/y]
    assert er.outlet_wall_rate_mm_y(10.0, 0.1, 0.001) == pytest.approx(2.5e-5 * 10**2.6 / 0.01 * 0.001, rel=1e-12)
    # tungsten carbide erodes far less than steel at the same conditions
    assert er.erosion_ratio(er.MATERIALS["tungsten_carbide_cs10"], 50, 30) < 0.2 * er.erosion_ratio(steel, 50, 30)


def test_erosion_sensitivities():
    m = er.MATERIALS["carbon_steel"]
    assert er.erosion_ratio(m, 40, 30) / er.erosion_ratio(m, 20, 30) == pytest.approx(2**2.6, rel=1e-9)  # velocity
    ductile = [er.f_alpha(math.radians(x), "ductile") for x in range(5, 90, 5)]
    assert max(range(len(ductile)), key=lambda i: ductile[i]) < 10  # ductile peak at intermediate angle


def _cage():
    return ChokeTrimInputs(stroke_mm=60, cage_wall_thickness_mm=12, hole_rows=[HoleRow(axial_position_mm=10, diameter_mm=6, count=4),
                                                                               HoleRow(axial_position_mm=40, diameter_mm=10, count=6)])


def test_cage_geometry_open_area_and_volume_conservation():
    g = er.CageGeometry(_cage())
    full = g.open_areas(100.0).sum()
    assert full == pytest.approx(4 * math.pi * 0.003**2 + 6 * math.pi * 0.005**2, rel=1e-12)
    assert g.open_areas(0.0).sum() == 0.0
    assert 0 < g.open_areas(16.666).sum() < full  # first row partly open (lift 10 mm = hole centre)
    # hole growth from a removed volume conserves the volume (thin-wall ring)
    v = 1e-9
    dd = g.distribute(v, 100.0, np.zeros(2))
    vol = sum(n * math.pi * d * 0.012 * x / 2 for n, d, x in zip(g.n, g.d0, dd))
    assert vol == pytest.approx(v, rel=1e-9)
    # at a small opening only the lowest row erodes
    dd_small = g.distribute(v, 15.0, np.zeros(2))
    assert dd_small[0] > 0 and dd_small[1] == 0
    # eroded holes raise the flow area (Cv)
    assert g.wear_factor(100.0, np.array([0.5e-3, 0.5e-3])) > 1.0


# ------------------------------------------------------- integration
@pytest.fixture(scope="module")
def eng():
    e = SimulationEngine(get_scenario(SCN))
    e.load_sand_example()
    e.start()
    e.advance(60)
    return e


def test_operator_preset_has_no_made_up_predictions():
    e = SimulationEngine(get_scenario(SCN))
    sc = e.snapshot(True)
    r = sc["sand_choke"]
    assert r["health"]["category"] == "Unavailable"
    assert r["confidence"]["category"] == "unavailable"
    assert any("trim material" in m for m in r["inputs_status"]["choke"]["missing"])
    assert r["sand"]["formation_kg_d"] is None and r["sand"]["missing"]
    # the operator's known choke data drive the simulated choke
    ch = e.restrictions["CHK-101"]
    assert ch.cv_max == 161.0 and ch.steps == 165 and ch.rangeability == pytest.approx(100.0)
    assert sc["sand_choke_inputs"]["completion"]["completion_type"] == "cased_perforated_standalone_screens"


def test_choke_steps_quantise_the_position():
    e = SimulationEngine(get_scenario(SCN))
    e.start()
    e.command_valve("CHK-101", "set_position", 37.5)
    e.advance(120)
    pos = e.restrictions["CHK-101"].actuator.position_pct
    assert pos == pytest.approx(round(37.5 / 100 * 165) / 165 * 100)


def test_sand_follows_drawdown_and_reaches_the_choke_with_the_flow(eng):
    r0 = eng.snapshot(False)["sand_choke"]
    assert r0["sand"]["onset"]["risk_index"] < 1.0 and r0["sand"]["formation_kg_d"] == 0.0
    eng.command_valve("CHK-101", "set_position", 70)
    eng.advance(120)
    r1 = eng.snapshot(False)["sand_choke"]
    assert r1["sand"]["onset"]["risk_index"] > 1.0 and r1["sand"]["produced_kg_d"] > 0
    assert r1["sand"]["at_choke_kg_d"] < r1["sand"]["produced_kg_d"]  # transit time up the well
    eng.advance(3 * 3600)
    r2 = eng.snapshot(False)["sand_choke"]
    assert r2["sand"]["at_choke_kg_d"] == pytest.approx(r2["sand"]["produced_kg_d"], rel=0.05)
    assert r2["detector"]["reading_g_s"] is not None and r2["detector"]["alarm"]
    crit = {c["key"]: c for c in r2["criteria"]}
    assert crit["hole"]["rate_per_year"] > 0 and crit["hole"]["life_days"]["p10"] < crit["hole"]["life_days"]["p50"] < crit["hole"]["life_days"]["p90"]
    assert r2["health"]["category"] in ("Elevated erosion risk", "Increased wear")


def test_wear_accumulates_with_operating_time_and_sand(eng):
    s = eng.sand
    used0 = float(s.dd_cal().max())
    rate = float(np.max(s.rates["hole_growth_rate_m_s"])) * s.c_factor
    eng.sand_fast_forward(100)
    used1 = float(s.dd_cal().max())
    assert used1 - used0 == pytest.approx(rate * 100 * 86400, rel=0.05)  # wear ~ rate x time at constant conditions
    cum0 = s.cum["choke_kg"]
    eng.sand_fast_forward(100)
    assert s.cum["choke_kg"] - cum0 == pytest.approx(s.rates["m_sand_choke"] * 100 * 86400, rel=1e-6)


def test_more_sand_means_more_erosion():
    e = SimulationEngine(get_scenario(SCN), mode="steady")  # steady: sand at the choke = produced sand
    inp = get_scenario(SCN).sand_choke_example.model_copy(deep=True)
    inp.sand.mode = "measured"
    inp.sand.measured_unit = "kg_d"
    rates = []
    for v in (10.0, 40.0):
        inp.sand.measured_value = v
        e.set_sand_inputs(inp.model_copy(deep=True))
        e.sand._update_rates_only()
        rates.append(float(e.sand.rates["trim_volume_rate_m3_s"]))
    assert rates[1] / rates[0] == pytest.approx(4.0, rel=1e-4)  # linear in sand mass rate


def test_inspection_calibration_shifts_and_narrows_the_prediction():
    e = SimulationEngine(get_scenario(SCN))
    inp = get_scenario(SCN).sand_choke_example.model_copy(deep=True)
    inp.history = [dict(label="m1", days=200, choke_step=115, upstream_pressure_bara=110, downstream_pressure_bara=65, oil_sm3_d=1000,
                        gas_sm3_d=120000, water_sm3_d=430, sand_kg_d=40)]
    e.set_sand_inputs(type(inp).model_validate(inp.model_dump()))
    pred = float(e.sand.dd_cal().max()) * 1e3
    assert pred > 0
    inp.inspections = [dict(label="2025 inspection", service_days=200, measured_max_hole_increase_mm=2 * pred)]
    e.set_sand_inputs(type(inp).model_validate(inp.model_dump()))
    s = e.sand
    lnc = math.log(2) * (1 / 0.35**2) / (1 / er_prior() ** 2 + 1 / 0.35**2)
    assert s.c_factor == pytest.approx(math.exp(lnc), rel=1e-9)
    assert s.sigma_c < er_prior()
    snap = e.snapshot(False)["sand_choke"]
    assert snap["confidence"]["category"].startswith("calibrated")
    assert snap["calibration"]["points"][0]["used"]


def er_prior():
    from app.simulation.sand.system import SIGMA_K_PRIOR

    return SIGMA_K_PRIOR


def test_health_categories_follow_configurable_thresholds():
    e = SimulationEngine(get_scenario(SCN))
    inp = get_scenario(SCN).sand_choke_example.model_copy(deep=True)
    inp.choke.trim_material = "carbon_steel"  # fast wear for the test
    inp.sand.mode = "measured"
    inp.sand.measured_value = 200.0
    e.set_sand_inputs(inp)
    e.start()
    e.advance(3600)
    seen = []
    for _ in range(40):
        e.sand_fast_forward(30)
        cat = e.snapshot(False)["sand_choke"]["health"]["category"]
        if not seen or seen[-1] != cat:
            seen.append(cat)
        if cat == "Critical condition":
            break
    order = ["Normal", "Elevated erosion risk", "Increased wear", "Inspection recommended", "Changeout assessment required", "Critical condition"]
    idx = [order.index(c) for c in seen]
    assert idx == sorted(idx) and seen[-1] == "Critical condition"
    rec = e.snapshot(False)["sand_choke"]["recommendation"]
    assert "Critical" in rec["title"] and rec["reasons"] and rec["disclaimer"]
    assert any(ev.category == "alarm" and "Choke health" in ev.message for ev in e.events.all())


def test_erosion_feedback_raises_the_simulated_cv_and_cv_tracking_sees_it():
    e = SimulationEngine(get_scenario(SCN))
    inp = get_scenario(SCN).sand_choke_example.model_copy(deep=True)
    inp.choke.trim_material = "carbon_steel"
    inp.sand.mode = "measured"
    inp.sand.measured_value = 300.0
    e.set_sand_inputs(inp)
    ch = e.restrictions["CHK-101"]
    e.start()
    e.advance(1800)
    c0 = ch.capacity
    e.sand_fast_forward(400)
    assert ch.capacity > 1.05 * c0  # worn cage passes more flow at the same step
    e.advance(4 * 3600)
    cvt = e.snapshot(False)["sand_choke"]["cv_tracking"]
    assert cvt["available"] and cvt["deviation_pct"] > 5.0 and cvt["significant"]
    assert any("erosion" in c for c in cvt["possible_causes"])


def test_single_phase_mode_keeps_the_choke_data_but_no_sand_model():
    e = SimulationEngine(get_scenario("xt_230xp22b"))
    assert e.snapshot(False)["sand_choke"]["available"] is False
    assert e.restrictions["CHK-101"].cv_max == 161.0


def test_inputs_survive_reset_and_api():
    with TestClient(app) as client:
        sid = client.post("/api/sessions", json={"scenario_id": SCN}).json()["session_id"]
        r = client.post(f"/api/sessions/{sid}/sand-choke/example")
        assert r.status_code == 200 and r.json()["state"]["sand_choke"]["health"]["category"] != "Unavailable"
        inputs = r.json()["state"]["sand_choke_inputs"]
        inputs["acceptance"]["max_hole_diameter_increase_mm"] = 0.8
        r = client.put(f"/api/sessions/{sid}/sand-choke/inputs", json=inputs)
        assert r.status_code == 200
        client.post(f"/api/sessions/{sid}/lifecycle", json={"action": "reset"})
        st = client.get(f"/api/sessions/{sid}").json()["state"]
        assert st["sand_choke_inputs"]["acceptance"]["max_hole_diameter_increase_mm"] == 0.8
        assert client.post(f"/api/sessions/{sid}/sand-choke/fast-forward", json={"days": 30}).status_code == 200
        bad = dict(inputs)
        bad["sand"] = {**inputs["sand"], "measured_unit": "furlongs"}
        assert client.put(f"/api/sessions/{sid}/sand-choke/inputs", json=bad).status_code == 422
