"""Measured sand history: CSV import (atomic, validated), unit conversion,
abnormal-increase trigger, latest record driving the erosion model, API."""

from __future__ import annotations

import warnings

import pytest

from app.models.sand import SandInputs, SandMeasurement
from app.simulation.sand import measurements as sm

warnings.simplefilter("ignore", RuntimeWarning)

CSV = """timestamp,value,unit,method,uncertainty_pct,liquid_rate_sm3_d,water_cut,d50_um,note
2025-01-01,2.0,kg/d,sand trap,20,,,150,
2025-02-01,2.4,kg/d,sand trap,20,,,,
2025-03-01,0.03,g/s,acoustic,40,,,,SDT-101 monthly mean
2025-04-01,10,pptb,well test,30,1500,30%,,
2025-05-01,5,ppm_mass_liquid,sample,,,,,no liquid rate recorded
"""

RHO = dict(rho_oil_sc=850.0, rho_water_sc=1030.0, rho_gas_sc=0.92, gor=120.0)


# ------------------------------------------------------------------ CSV
def test_csv_parses_units_methods_and_percent_water_cut():
    recs = sm.parse_csv(CSV)
    assert [r.unit for r in recs] == ["kg_d", "kg_d", "g_s", "pptb", "ppm_mass_liquid"]
    assert [r.method for r in recs] == ["sand_trap", "sand_trap", "acoustic_detector", "well_test_sample", "well_test_sample"]
    assert recs[3].water_cut == pytest.approx(0.30) and recs[3].liquid_rate_sm3_d == 1500
    assert recs[0].d50_um == 150 and recs[2].note == "SDT-101 monthly mean"


def test_csv_import_is_atomic_and_reports_every_bad_line():
    bad = "timestamp,value,unit\n2025-01-01,1,kg/d\nnot-a-date,1,kg/d\n2025-01-03,-1,kg/d\n2025-01-04,1,furlongs\n"
    with pytest.raises(sm.CsvImportError) as ei:
        sm.parse_csv(bad)
    lines = [e["line"] for e in ei.value.errors]
    assert lines == [3, 4, 5]
    assert "furlongs" in ei.value.errors[2]["error"]


@pytest.mark.parametrize("text, msg", [("", "empty"), ("value,unit\n1,kg/d\n", "timestamp"),
                                       ("timestamp,value,colour\n2025-01-01,1,red\n", "unknown column"),
                                       ("timestamp,value\n", "no data rows")])
def test_csv_header_problems(text, msg):
    with pytest.raises(sm.CsvImportError) as ei:
        sm.parse_csv(text)
    assert msg in ei.value.errors[0]["error"]


def test_csv_round_trip():
    recs = sm.parse_csv(CSV)
    again = sm.parse_csv(sm.to_csv(recs))
    assert [r.model_dump() for r in again] == [r.model_dump() for r in sorted(recs, key=lambda x: x.timestamp)]


# ----------------------------------------------------------- conversion
def test_conversion_to_kg_d_by_hand():
    s = SandInputs()
    recs = sm.parse_csv(CSV)
    assert sm.to_kg_d(recs[0], s, **RHO) == pytest.approx(2.0)
    assert sm.to_kg_d(recs[2], s, **RHO) == pytest.approx(0.03 * 86.4)
    # pptb: 10 lb per 1000 bbl liquid at 1500 Sm3/d
    lb, bbl = 0.45359237, 0.158987294928
    assert sm.to_kg_d(recs[3], s, **RHO) == pytest.approx(10 * lb / (1000 * bbl) * 1500)
    assert sm.to_kg_d(recs[4], s, **RHO) is None  # concentration without the liquid rate


# -------------------------------------------------------------- trigger
def _rep(values, **kw):
    s = SandInputs(measurements=[SandMeasurement(timestamp=f"2025-01-{i + 1:02d}", value=v) for i, v in enumerate(values)], **kw)
    return sm.report(s, **RHO)


def test_abnormal_increase_against_the_median_of_the_baseline():
    a = _rep([2, 2.2, 1.8, 2.1, 2.0, 5.0])["abnormal"]
    assert a["flag"] and a["baseline_kg_d"] == pytest.approx(2.0) and a["ratio"] == pytest.approx(2.5)
    assert not _rep([2, 2.2, 1.8, 2.1, 2.0, 3.0])["abnormal"]["flag"]
    # only the last N baseline records count
    assert _rep([10, 10, 2, 2, 5.0], abnormal_baseline_count=2)["abnormal"]["flag"]
    # configurable trigger: a minimum absolute increase suppresses small-number noise
    assert not _rep([0.01, 0.01, 0.05], abnormal_min_increase_kg_d=0.5)["abnormal"]["flag"]
    assert _rep([0.01, 0.01, 0.05])["abnormal"]["flag"]
    assert not _rep([2.0])["abnormal"]["available"]


def test_unconvertible_records_are_left_out_and_noted():
    r = sm.report(SandInputs(measurements=sm.parse_csv(CSV)), **RHO)
    assert r["count"] == 5 and sum(1 for x in r["series"] if x["kg_d"] is None) == 1
    assert any("cannot be converted" in n for n in r["notes"])
    assert r["abnormal"]["latest_timestamp"].startswith("2025-04-01")  # last CONVERTED record


# ---------------------------------------------------------- model input
def test_latest_record_drives_the_model_only_in_measured_mode():
    recs = sm.parse_csv(CSV)
    s = SandInputs(measurements=recs)
    eff, rec = sm.effective_sand(s)
    assert rec is None and eff is s  # predictive mode: history shown but not used
    eff, rec = sm.effective_sand(s.model_copy(update={"mode": "measured"}))
    assert rec.timestamp.month == 5 and eff.measured_value == 5 and eff.measured_unit == "ppm_mass_liquid"
    assert eff.measured_uncertainty_pct == 30.0  # record without uncertainty: the default


@pytest.fixture(scope="module")
def eng():
    from app.scenarios.loader import get_scenario
    from app.simulation.engine import SimulationEngine

    e = SimulationEngine(get_scenario("xt_230xp22b_multiphase"))
    e.load_sand_example()
    e.start()
    e.advance(300)
    return e


def test_engine_import_feeds_the_erosion_model_and_alarms_on_abnormal_increase(eng):
    inp = eng.sand_inputs.model_copy(deep=True)
    inp.sand.mode = "measured"
    eng.set_sand_inputs(inp)
    n = eng.import_sand_measurements("timestamp,value,unit,method\n2025-01-01,2,kg/d,sand trap\n2025-02-01,2.2,kg/d,sand trap\n"
                                     "2025-03-01,1.9,kg/d,sand trap\n2025-04-01,9,kg/d,sand trap\n", replace=True)
    assert n == 4
    eng.advance(60)
    sc = eng.snapshot(False)["sand_choke"]
    assert sc["sand"]["produced_kg_d"] == pytest.approx(9.0)  # latest record drives the model
    mh = sc["measured_history"]
    assert mh["drives_model"] and mh["driving_record"]["value"] == 9 and mh["abnormal"]["flag"]
    assert any(ev.category == "alarm" and "ABNORMAL INCREASE" in ev.message for ev in eng.events.all())
    m_choke = sc["sand"]["at_choke_kg_d"]
    # a further (lower) record replaces the driving rate
    eng.import_sand_measurements("timestamp,value,unit\n2025-05-01,3,kg/d\n")
    eng.advance(60)
    sc2 = eng.snapshot(False)["sand_choke"]
    assert sc2["measured_history"]["count"] == 5 and sc2["sand"]["produced_kg_d"] == pytest.approx(3.0)
    assert m_choke is not None
    import json

    json.dumps(eng.snapshot(True))  # the WebSocket payload must serialise (timestamps as ISO strings)


def test_api_imports_csv_and_rejects_bad_files():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        sid = client.post("/api/sessions", json={"scenario_id": "xt_230xp22b_multiphase"}).json()["session_id"]
        r = client.post(f"/api/sessions/{sid}/sand-choke/measurements/csv", json={"csv": CSV})
        assert r.status_code == 200 and r.json()["imported"] == 5
        assert r.json()["state"]["sand_choke"]["measured_history"]["count"] == 5
        assert r.json()["state"]["sand_choke_inputs"]["sand"]["measurements"][0]["unit"] == "kg_d"
        bad = client.post(f"/api/sessions/{sid}/sand-choke/measurements/csv", json={"csv": "timestamp,value\nx,1\n"})
        assert bad.status_code == 422 and bad.json()["detail"]["errors"][0]["line"] == 2
        # nothing imported by the rejected file
        st = client.get(f"/api/sessions/{sid}").json()
        assert st["state"]["sand_choke"]["measured_history"]["count"] == 5
