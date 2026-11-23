"""Simulation records (SQLite): build from the live engine, provenance of
every input group, methods / versions, persistence, listing, API."""

from __future__ import annotations

import json
import sqlite3
import warnings

import pytest

from app.core.model_registry import MODELS, STATUS_LADDER
from app.storage import assessment, records

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
    e.advance(300)
    return e


def test_registry_entries_are_complete_and_on_the_status_ladder():
    for k, m in MODELS.items():
        assert {"version", "status", "method", "validation", "doc"} <= set(m), k
        assert m["status"] in STATUS_LADDER, k


def test_record_captures_inputs_results_methods_and_validation(eng):
    b = assessment.build_record(eng, "sid-1")
    snap = eng.snapshot(False)
    assert b["header"]["scenario_id"] == "xt_230xp22b_multiphase" and b["header"]["sim_time_s"] == snap["time_s"]
    chk = next(v for v in b["inputs"]["valves"] if v["tag"] == "CHK-101")
    assert chk["position_pct"] == pytest.approx(eng.restrictions["CHK-101"].actuator.position_pct)
    assert b["inputs"]["sand_choke"]["choke"]["max_cv"] == 161.0
    pt = next(i for i in b["results"]["instruments"] if i["tag"] == "PT-104")
    assert pt["value_si"] == next(i for i in snap["instruments"] if i["tag"] == "PT-104")["value_si"]
    assert b["results"]["choke_health"]["category"] == snap["sand_choke"]["health"]["category"]
    assert b["results"]["cavitation"]["status"] == "Correlation-based screening"
    assert {"black_oil_pvt", "multiphase_flow", "mpfm", "choke_erosion", "cavitation", "api14e"} <= set(b["methods"])
    assert b["validation"]["overall"].startswith("Verified models, not field-validated")
    assert b["validation"]["data_classification"].startswith("ILLUSTRATIVE")
    assert b["uncertainty"]["mpfm_uncertainty_pct"]
    assert any(a.startswith("Sand / erosion:") for a in b["assumptions"])
    json.dumps(b)


def test_provenance_distinguishes_illustrative_estimated_simulated(eng):
    p = assessment.build_record(eng)["provenance"]
    assert p["sand_and_choke_inputs"].startswith("illustrative") and p["sand_inputs_origin"] == "illustrative example"
    assert p["sand_rate"].startswith("estimated") and p["process_measurements"].startswith("simulated")
    assert p["mpfm_reading"].startswith("simulated measurement")


def test_provenance_of_imported_measured_sand():
    from app.scenarios.loader import get_scenario
    from app.simulation.engine import SimulationEngine

    e = SimulationEngine(get_scenario("xt_230xp22b_multiphase"))
    e.load_sand_example()
    inp = e.sand_inputs.model_copy(deep=True)
    inp.sand.mode = "measured"
    e.set_sand_inputs(inp)
    e.import_sand_measurements("timestamp,value,unit\n2025-01-01,2,kg/d\n")
    e.start()
    e.advance(60)
    p = assessment.build_record(e)["provenance"]
    assert p["sand_rate"] == "measured (imported CSV history, latest record)"
    assert p["sand_and_choke_inputs"].startswith("illustrative, partly edited")  # edited after loading the example
    assert e.sand_inputs.sand.measurements[0].source == "csv_import"


def test_save_list_get_delete_round_trip(eng, tmp_db):
    a = records.save(assessment.build_record(eng, "s"), "baseline 30 %", "first")
    b = records.save(assessment.build_record(eng, "s"), "after change")
    rows = records.list_records()
    assert [r["label"] for r in rows] == ["after change", "baseline 30 %"]  # newest first
    full = records.get(a["id"])
    assert full["label"] == "baseline 30 %" and full["notes"] == "first" and full["id"] == a["id"]
    assert full["results"]["choke_health"]["category"] == a["health_category"]
    assert records.list_records(scenario_id="nope") == []
    records.delete(b["id"])
    with pytest.raises(records.RecordNotFound):
        records.get(b["id"])
    with pytest.raises(records.RecordNotFound):
        records.delete(b["id"])
    # stored on disk with the schema version
    con = sqlite3.connect(tmp_db)
    assert con.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()[0] == str(records.SCHEMA_VERSION)
    con.close()


def test_api_save_list_get_export_delete(tmp_db):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        sid = client.post("/api/sessions", json={"scenario_id": "xt_230xp22b_multiphase"}).json()["session_id"]
        r = client.post(f"/api/sessions/{sid}/records", json={"label": "Shift handover", "notes": "choke at 30 %"})
        assert r.status_code == 201
        rid = r.json()["id"]
        assert r.json()["scenario_id"] == "xt_230xp22b_multiphase"
        lst = client.get("/api/records").json()
        assert lst[0]["id"] == rid and lst[0]["label"] == "Shift handover"
        full = client.get(f"/api/records/{rid}").json()
        assert full["header"]["session_id"] == sid and full["methods"]
        ex = client.get(f"/api/records/{rid}/export")
        assert ex.status_code == 200 and "attachment" in ex.headers["content-disposition"]
        assert json.loads(ex.content)["id"] == rid
        assert client.post(f"/api/sessions/{sid}/records", json={"label": ""}).status_code == 422
        assert client.delete(f"/api/records/{rid}").status_code == 204
        assert client.get(f"/api/records/{rid}").status_code == 404


def test_unwritable_storage_gives_a_clear_503(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app

    blocker = tmp_path / "not_a_folder"
    blocker.write_text("x")  # a FILE where the records folder should be
    monkeypatch.setenv("SUBSEASIM_DB_PATH", str(blocker / "records.sqlite"))
    with TestClient(app) as client:
        r = client.get("/api/records")
        assert r.status_code == 503 and "Records storage unavailable" in r.json()["detail"]
