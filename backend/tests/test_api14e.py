"""API RP 14E erosional-velocity screening (supplementary to the DNV
erosion model): unit conversion, scaling and engine integration."""

from __future__ import annotations

import math
import warnings

import pytest

from app.models.sand import ErosionalVelocityInputs, SandChokeInputs
from app.simulation.sand import erosion as er

warnings.simplefilter("ignore", RuntimeWarning)


def test_erosional_velocity_matches_the_us_unit_formula():
    # Ve = C / sqrt(rho) in ft/s with rho in lb/ft3: 1000 kg/m3 = 62.428 lb/ft3
    rho_lb = 1000.0 / 16.018463373960138
    assert er.api14e_erosional_velocity(1000.0, 100.0) == pytest.approx(100.0 / math.sqrt(rho_lb) * 0.3048, rel=1e-12)
    assert er.api14e_erosional_velocity(1000.0, 100.0) == pytest.approx(3.8577, abs=1e-4)


def test_erosional_velocity_scales_with_c_and_inverse_root_density():
    v = er.api14e_erosional_velocity(400.0, 100.0)
    assert er.api14e_erosional_velocity(400.0, 125.0) == pytest.approx(1.25 * v)
    assert er.api14e_erosional_velocity(100.0, 100.0) == pytest.approx(2.0 * v)


def test_c_factor_is_validated_and_defaults_to_continuous_service():
    assert ErosionalVelocityInputs().c_factor == 100.0
    with pytest.raises(ValueError):
        ErosionalVelocityInputs(c_factor=0)
    assert SandChokeInputs.model_validate({}).erosional_velocity.c_factor == 100.0


@pytest.fixture(scope="module")
def eng():
    from app.scenarios.loader import get_scenario
    from app.simulation.engine import SimulationEngine

    e = SimulationEngine(get_scenario("xt_230xp22b_multiphase"))
    e.load_sand_example()
    e.start()
    e.advance(600)
    return e


def test_engine_screens_gallery_outlet_and_flowline_from_the_simulated_flow(eng):
    ev = eng.snapshot(False)["sand_choke"]["erosional_velocity"]
    assert ev["available"] and ev["status"].startswith("Correlation-based screening")
    rows = {r["key"]: r for r in ev["locations"]}
    assert set(rows) == {"gallery", "outlet", "flowline"}
    for r in rows.values():
        assert r["available"]
        assert r["ve_m_s"] == pytest.approx(er.api14e_erosional_velocity(r["rho_mix_kg_m3"], 100.0))
        assert r["ratio"] == pytest.approx(r["u_mix_m_s"] / r["ve_m_s"])
    # the outlet bore is smaller than the flowline: higher mixture velocity at the same density
    assert rows["outlet"]["u_mix_m_s"] > rows["flowline"]["u_mix_m_s"]
    assert any("NOT a sand-erosion model" in n for n in ev["notes"])


def test_sand_present_warns_that_c_must_be_reduced(eng):
    eng.command_valve("CHK-101", "set_position", 70)
    eng.advance(3 * 3600)
    ev = eng.snapshot(False)["sand_choke"]["erosional_velocity"]
    assert ev["sand_present"] and any("C must be reduced" in n for n in ev["notes"])


def test_missing_geometry_is_reported_not_assumed():
    from app.scenarios.loader import get_scenario
    from app.simulation.engine import SimulationEngine

    e = SimulationEngine(get_scenario("xt_230xp22b_multiphase"))  # operator preset: no gallery / outlet bore
    e.start()
    e.advance(300)
    rows = {r["key"]: r for r in e.snapshot(False)["sand_choke"]["erosional_velocity"]["locations"]}
    assert not rows["gallery"]["available"] and rows["gallery"]["missing"] == "gallery diameter"
    assert not rows["outlet"]["available"] and rows["flowline"]["available"]


def test_lower_c_lowers_the_limit_through_the_inputs(eng):
    inp = eng.sand.inputs.model_copy(deep=True)
    v0 = {r["key"]: r for r in eng.snapshot(False)["sand_choke"]["erosional_velocity"]["locations"]}["flowline"]["ve_m_s"]
    inp.erosional_velocity.c_factor = 50.0
    eng.set_sand_inputs(inp)
    eng.advance(60)
    v1 = {r["key"]: r for r in eng.snapshot(False)["sand_choke"]["erosional_velocity"]["locations"]}["flowline"]["ve_m_s"]
    assert v1 == pytest.approx(v0 / 2, rel=0.05)
