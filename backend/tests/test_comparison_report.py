"""Scenario comparison (steady twins of the session, same models) and the
engineering report generated from saved records."""

from __future__ import annotations

import sqlite3
import time
import warnings

import pytest

from app import job_kinds  # noqa: F401 - registers the job kinds
from app.jobs import JobRejected
from app.reports.report import render
from app.storage import assessment, records
from app.studies import comparison as cmp

warnings.simplefilter("ignore", RuntimeWarning)


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    p = tmp_path / "records.sqlite"
    monkeypatch.setenv("SUBSEASIM_DB_PATH", str(p))
    return p


@pytest.fixture(scope="module")
def eng():
    from app.scenarios.loader import get_scenario
    from app.simulation.engine import SimulationEngine

    e = SimulationEngine(get_scenario("xt_230xp22b_multiphase"))
    e.load_sand_example()
    e.start()
    e.advance(600)
    e.sand_fast_forward(30)  # some accumulated wear to carry over
    return e


def _run(e, req):
    g = cmp.run_study(e, cmp.StudyRequest.model_validate(req))
    steps = []
    try:
        while True:
            steps.append(next(g))
    except StopIteration as s:
        return s.value, steps


# ----------------------------------------------------------- steady twin
def test_steady_twin_carries_the_session_state(eng):
    tw = cmp.steady_twin(eng)
    assert tw.mode == "steady" and eng.mode == "dynamic"
    for tag, el in eng.restrictions.items():
        assert tw.restrictions[tag].actuator.position_pct == el.actuator.position_pct
    assert tw.ipr.p_res == eng.ipr.p_res and tw.mp_wc == eng.mp_wc
    assert tw.sand.service_s == eng.sand.service_s and (tw.sand.dd_base == eng.sand.dd_base).all()
    oil_tw = tw.snapshot(False)["multiphase"]["rates_arrival"]["oil_sm3_d"]
    oil_dyn = eng.snapshot(False)["multiphase"]["rates_arrival"]["oil_sm3_d"]
    assert oil_tw == pytest.approx(oil_dyn, rel=0.01)  # the settled dynamic session


def test_study_compares_cases_without_touching_the_live_session(eng):
    before = (eng.time_s, eng.restrictions["CHK-101"].actuator.position_pct, eng.sand.service_s, eng.mode, len(eng.events.all()))
    res, steps = _run(eng, {"variants": [{"label": "Choke 60 %", "choke_pct": 60}, {"label": "WC 50 %", "water_cut": 0.5},
                                         {"label": "WC trim 60 %", "choke_pct": 60, "trim_material": "tungsten_carbide_dc05"}],
                            "horizon_days": 90})
    assert (eng.time_s, eng.restrictions["CHK-101"].actuator.position_pct, eng.sand.service_s, eng.mode, len(eng.events.all())) == before
    c = {x["id"]: x for x in res["cases"]}
    base, ch60, wc50, carb = c["base"], c["v1"], c["v2"], c["v3"]
    # physics directions
    assert ch60["now"]["oil_sm3_d"] > base["now"]["oil_sm3_d"] and ch60["now"]["drawdown_bar"] > base["now"]["drawdown_bar"]
    assert ch60["now"]["choke_dp_bar"] < base["now"]["choke_dp_bar"]
    assert wc50["now"]["water_cut"] == pytest.approx(0.5) and wc50["now"]["water_sm3_d"] > base["now"]["water_sm3_d"]
    assert base["now"]["choke_pct"] == pytest.approx(eng.restrictions["CHK-101"].actuator.position_pct)
    # wear: carried over (service days = session + horizon), new trim for the material variant
    assert ch60["after_horizon"]["service_days"] == pytest.approx(eng.sand.service_s / 86400 + 90, abs=1e-6)
    assert carb["wear_start"] == "new trim (zero wear)" and ch60["wear_start"] == "current trim wear"
    assert carb["now"]["hole_rate_mm_y"] < ch60["now"]["hole_rate_mm_y"]  # tungsten carbide wears less
    assert ch60["changes"] == ["choke_pct = 60 %"]
    assert steps[-1][0] <= 1.0 and all(0 <= p <= 1 for p, _ in steps)
    assert res["limitations"] and "steady twin" in res["method"]


def test_choke_variant_respects_the_actuator_steps(eng):
    res, _ = _run(eng, {"variants": [{"label": "37.5", "choke_pct": 37.5}], "horizon_days": 0})
    pos = res["cases"][1]["now"]["choke_pct"]
    assert pos == pytest.approx(round(37.5 / 100 * 165) / 165 * 100)
    assert res["cases"][1]["now"] == res["cases"][1]["after_horizon"]  # horizon 0


def test_invalid_studies_are_rejected_before_running(eng):
    from types import SimpleNamespace

    from app.jobs import jobs

    f = jobs.kinds["scenario_comparison"]
    s = SimpleNamespace(engine=eng, id="x")
    for bad in ({"variants": []}, {"variants": [{"label": "a"}] * 7}, {"variants": [{"label": "m", "trim_material": "cheese"}]},
                {"variants": [{"label": "c", "choke_pct": 140}]}, {"variants": [{"label": "x"}], "horizon_days": 9999}):
        with pytest.raises(JobRejected):
            f(s, bad)


# ---------------------------------------------------------------- report
def test_report_has_every_section_and_escapes_text(eng):
    body = assessment.build_record(eng, "s1")
    res, _ = _run(eng, {"variants": [{"label": "Choke <60> %", "choke_pct": 60}], "horizon_days": 30})
    body["comparison"] = res
    row = records.save(body, "<script>alert(1)</script> baseline", "notes & more")
    out = render(records.get(row["id"]))
    assert "<script>alert(1)</script>" not in out and "&lt;script&gt;" in out and "Choke &lt;60&gt; %" in out
    for sec in ("1. Simulation configuration", "2. Reservoir fluid properties", "3. Production conditions", "4. Valve and choke states",
                "5. Pressure, temperature and flow readings", "6. Multiphase flow meter", "7. Sand production",
                "8. Choke erosion and remaining life", "9. Cavitation and flashing screening", "10. Component health",
                "11. Operating history", "12. Scenario comparison", "13. Data provenance", "14. Methods and model versions",
                "15. Uncertainty", "16. Model assumptions"):
        assert sec in out, sec
    assert "Verified models, not field-validated" in out and "Bubble point reservoir" in out
    assert row["has_comparison"] == 1


def test_old_database_is_migrated_in_place(tmp_db):
    con = sqlite3.connect(tmp_db)
    con.executescript("""CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT INTO meta VALUES ('schema_version', '1');
        CREATE TABLE simulation_records (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, label TEXT NOT NULL, notes TEXT,
          scenario_id TEXT NOT NULL, scenario_name TEXT, session_id TEXT, sim_time_s REAL NOT NULL, app_version TEXT NOT NULL,
          validation_status TEXT NOT NULL, health_category TEXT, body TEXT NOT NULL);
        INSERT INTO simulation_records VALUES ('old1', '2026-01-01T00:00:00+00:00', 'old record', NULL, 'xt', NULL, NULL, 0, '0.4.0',
          'Verified models, not field-validated', NULL, '{}');""")
    con.commit()
    con.close()
    rows = records.list_records()
    assert rows[0]["id"] == "old1" and rows[0]["has_comparison"] == 0
    con = sqlite3.connect(tmp_db)
    assert con.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()[0] == str(records.SCHEMA_VERSION)
    con.close()


# ------------------------------------------------------------------- API
def _wait(client, jid):
    for _ in range(1200):
        j = client.get(f"/api/jobs/{jid}").json()
        if j["state"] not in ("pending", "running"):
            return j
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def test_api_comparison_job_record_attachment_and_report():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        sid = client.post("/api/sessions", json={"scenario_id": "xt_230xp22b_multiphase"}).json()["session_id"]
        client.post(f"/api/sessions/{sid}/sand-choke/example")
        r = client.post(f"/api/sessions/{sid}/jobs", json={"kind": "scenario_comparison",
                                                          "params": {"variants": [{"label": "Choke 50 %", "choke_pct": 50}], "horizon_days": 30}})
        assert r.status_code == 202
        j = _wait(client, r.json()["id"])
        assert j["state"] == "completed" and len(j["result"]["cases"]) == 2
        bad = client.post(f"/api/sessions/{sid}/jobs", json={"kind": "scenario_comparison", "params": {"variants": []}})
        assert bad.status_code == 409 and "variants" in bad.json()["detail"]
        rec = client.post(f"/api/sessions/{sid}/records", json={"label": "Study", "comparison_job_id": j["id"]})
        assert rec.status_code == 201 and rec.json()["has_comparison"] == 1
        full = client.get(f"/api/records/{rec.json()['id']}").json()
        assert full["comparison"]["cases"][1]["label"] == "Choke 50 %"
        rep = client.get(f"/api/records/{rec.json()['id']}/report")
        assert rep.status_code == 200 and rep.headers["content-type"].startswith("text/html") and "12. Scenario comparison" in rep.text
        dl = client.get(f"/api/records/{rec.json()['id']}/report?download=true")
        assert "attachment" in dl.headers["content-disposition"]
        # only a completed comparison of THIS session can be attached
        assert client.post(f"/api/sessions/{sid}/records", json={"label": "x", "comparison_job_id": "nope"}).status_code == 404
        sid2 = client.post("/api/sessions", json={"scenario_id": "xt_230xp22b_multiphase"}).json()["session_id"]
        assert client.post(f"/api/sessions/{sid2}/records", json={"label": "x", "comparison_job_id": j["id"]}).status_code == 409
