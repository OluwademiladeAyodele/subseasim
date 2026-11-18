"""Surrogate models: GP and response-surface accuracy on known functions,
leave-one-out validation, operating envelope, provenance labelling,
simulator design of experiments, storage and the API."""

from __future__ import annotations

import time
import warnings

import numpy as np
import pytest

from app import job_kinds  # noqa: F401 - registers the job kinds
from app.storage import records
from app.surrogates import gp as gpm
from app.surrogates.doe import parse_cases_csv, sample_points, simulate_cases
from app.surrogates.model import Surrogate, build, fit_poly

warnings.simplefilter("ignore", RuntimeWarning)


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setenv("SUBSEASIM_DB_PATH", str(tmp_path / "records.sqlite"))


def _cases(f, n=25, seed=1, source="simulator"):
    rng = np.random.default_rng(seed)
    x = rng.uniform(0, 1, (n, 2))
    return [{"x": {"choke_pct": float(a) * 100, "water_cut": float(b)}, "y": {"oil_sm3_d": float(f(a, b))}, "source": source,
             "reference": None} for a, b in x]


# ----------------------------------------------------------------- GP / poly
def test_gp_reproduces_a_smooth_function_and_its_loo_is_the_brute_force_refit():
    rng = np.random.default_rng(1)
    x = rng.uniform(0, 1, (25, 2))
    f = lambda z: np.sin(3 * z[:, 0]) + 0.5 * z[:, 1] ** 2  # noqa: E731
    m = gpm.fit(x, f(x))
    xt = rng.uniform(0, 1, (200, 2))
    mu, sd = m.predict(xt)
    assert np.sqrt(np.mean((mu - f(xt)) ** 2)) < 5e-3
    lm, ls = m.loo()
    from scipy.linalg import cho_factor, cho_solve

    ell, sf2, sn2 = np.exp(m.log_ell), np.exp(2 * m.log_sf), np.exp(2 * m.log_sn)
    for i in (0, 7, 19):
        mask = np.arange(25) != i
        k = gpm._kernel(x[mask], x[mask], ell, sf2) + (sn2 + 1e-10) * np.eye(24)
        c = cho_factor(k, lower=True)
        ks = gpm._kernel(x[i:i + 1], x[mask], ell, sf2)
        assert lm[i] == pytest.approx(m.y_mean + m.y_std * (ks @ cho_solve(c, m.yn[mask]))[0], rel=1e-6, abs=1e-9)


def test_gp_uncertainty_grows_away_from_the_data():
    x = np.linspace(0, 0.5, 8)[:, None]
    m = gpm.fit(x, np.sin(4 * x[:, 0]))
    _, sd_in = m.predict(np.array([[0.25]]))
    _, sd_out = m.predict(np.array([[1.0]]))
    assert sd_out[0] > 10 * sd_in[0]


def test_quadratic_surface_is_exact_for_a_quadratic():
    rng = np.random.default_rng(2)
    x = rng.uniform(0, 1, (20, 2))
    y = 1 + 2 * x[:, 0] - x[:, 1] + 3 * x[:, 0] * x[:, 1] + 0.5 * x[:, 1] ** 2
    m = fit_poly(x, y)
    mu, _ = m.predict(np.array([[0.3, 0.7]]))
    assert mu[0] == pytest.approx(1 + 0.6 - 0.7 + 0.63 + 0.245, abs=1e-5)
    assert np.allclose(m.loo_mu, y, atol=1e-5)


# ---------------------------------------------------------------- the model
def test_validation_envelope_and_labels():
    s = build("t", "gp", ["choke_pct", "water_cut"], ["oil_sm3_d"], _cases(lambda a, b: 500 + 900 * a - 300 * b))
    v = s.validation["oil_sm3_d"]
    assert v["loo_r2"] > 0.999 and v["loo_coverage_95"] >= 0.8 and len(v["loo_points"]) == 25
    p = s.predict({"choke_pct": 50, "water_cut": 0.5})
    assert p["envelope"]["inside"] and p["outputs"]["oil_sm3_d"]["mean"] == pytest.approx(500 + 450 - 150, rel=1e-3)
    out = s.predict({"choke_pct": 150, "water_cut": 0.5})["envelope"]
    assert not out["inside"] and out["outside_inputs"][0]["input"] == "choke_pct" and "high-fidelity" in out["message"]
    assert s.status == "Surrogate-model prediction - trained on simulator data (SubseaSim steady twins), not CFD or field data"
    cfd = build("c", "poly", ["choke_pct", "water_cut"], ["oil_sm3_d"], _cases(lambda a, b: a + b, source="cfd"))
    assert cfd.status.endswith("trained on imported cfd data") and cfd.card()["sources"] == {"cfd": 25}
    with pytest.raises(ValueError, match="missing inputs"):
        s.predict({"choke_pct": 50})


def test_sparse_region_is_flagged_inside_the_box():
    cases = [c for c in _cases(lambda a, b: a + b, n=60) if not (0.3 < c["x"]["choke_pct"] / 100 < 0.7 and 0.3 < c["x"]["water_cut"] < 0.7)]
    s = build("t", "poly", ["choke_pct", "water_cut"], ["oil_sm3_d"], cases)
    env = s.envelope({"choke_pct": 50, "water_cut": 0.5})
    assert env["sparse"] and not env["inside"] and not env["outside_inputs"]


def test_build_checks_its_data():
    with pytest.raises(ValueError, match="needs at least"):
        build("t", "poly", ["choke_pct", "water_cut"], ["oil_sm3_d"], _cases(lambda a, b: a, n=5))
    with pytest.raises(ValueError, match="source"):
        build("t", "gp", ["choke_pct", "water_cut"], ["oil_sm3_d"], _cases(lambda a, b: a, source="made_up"))
    cases = _cases(lambda a, b: a + b, n=12)
    cases[0]["y"]["oil_sm3_d"] = None
    s = build("t", "gp", ["choke_pct", "water_cut"], ["oil_sm3_d"], cases)
    assert len(s.cases) == 11 and "left out" in s.notes[0]


def test_storage_round_trip_retrains_the_same_model():
    s = build("t", "gp", ["choke_pct", "water_cut"], ["oil_sm3_d"], _cases(lambda a, b: np.sin(3 * a) + b))
    row = records.save_surrogate(s)
    again = Surrogate.from_dict(records.get_surrogate_body(row["id"]))
    q = {"choke_pct": 33, "water_cut": 0.4}
    assert again.predict(q)["outputs"]["oil_sm3_d"]["mean"] == pytest.approx(s.predict(q)["outputs"]["oil_sm3_d"]["mean"], rel=1e-9)
    assert records.list_surrogates()[0]["id"] == row["id"] and records.list_surrogates()[0]["sources"] == {"simulator": 25}
    records.delete_surrogate(row["id"])
    with pytest.raises(records.RecordNotFound):
        records.get_surrogate_body(row["id"])


def test_imported_csv_is_validated():
    ok = "choke_pct,water_cut,oil_sm3_d,source,reference\n30,0.3,500,cfd,Case A\n60,0.3,1000,experiment,\n"
    c = parse_cases_csv(ok, ["choke_pct", "water_cut"], ["oil_sm3_d"])
    assert [x["source"] for x in c] == ["cfd", "experiment"] and c[0]["reference"] == "Case A"
    with pytest.raises(ValueError, match="missing column"):
        parse_cases_csv("choke_pct,oil_sm3_d\n30,500\n", ["choke_pct", "water_cut"], ["oil_sm3_d"])
    with pytest.raises(ValueError, match="line 4: could not convert"):
        parse_cases_csv(ok + "40,0.3,abc,cfd,\n", ["choke_pct", "water_cut"], ["oil_sm3_d"])
    with pytest.raises(ValueError, match="source must be"):
        parse_cases_csv("choke_pct,water_cut,oil_sm3_d,source\n30,0.3,500,guess\n", ["choke_pct", "water_cut"], ["oil_sm3_d"])


# ------------------------------------------------------- simulator training
def test_latin_hypercube_covers_each_range_once_per_stratum():
    pts = sample_points({"choke_pct": (20, 70)}, 10)
    strata = sorted(int((p["choke_pct"] - 20) / 5) for p in pts)
    assert strata == list(range(10))


def test_simulator_trained_surrogate_matches_the_simulator_at_a_new_point():
    from app.scenarios.loader import get_scenario
    from app.simulation.engine import SimulationEngine
    from app.studies.comparison import Variant, _apply, metrics, steady_twin

    e = SimulationEngine(get_scenario("xt_230xp22b_multiphase"))
    e.load_sand_example()
    e.start()
    e.advance(300)
    g = simulate_cases(e, {"choke_pct": (25.0, 70.0)}, ["oil_sm3_d", "jet_velocity_m_s"], 12)
    try:
        while True:
            next(g)
    except StopIteration as s:
        cases = s.value
    assert all(c["source"] == "simulator" for c in cases) and len(cases) == 12
    sur = build("choke", "gp", ["choke_pct"], ["oil_sm3_d", "jet_velocity_m_s"], cases, bounds={"choke_pct": (25.0, 70.0)})
    tw = steady_twin(e)
    _apply(tw, Variant(label="check", choke_pct=52.0))
    truth = metrics(tw)
    p = sur.predict({"choke_pct": truth["choke_pct"]})
    assert p["envelope"]["inside"]
    assert p["outputs"]["oil_sm3_d"]["mean"] == pytest.approx(truth["oil_sm3_d"], rel=0.02)
    assert sur.validation["oil_sm3_d"]["loo_r2"] > 0.99


# -------------------------------------------------------------------- API
def test_api_train_predict_check_import_delete():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        sid = client.post("/api/sessions", json={"scenario_id": "xt_230xp22b_multiphase"}).json()["session_id"]
        client.post(f"/api/sessions/{sid}/sand-choke/example")
        bad = client.post(f"/api/sessions/{sid}/jobs", json={"kind": "surrogate_build", "params": {"name": "x", "bounds": {"choke_pct": [70, 20]},
                                                                                                    "outputs": ["oil_sm3_d"]}})
        assert bad.status_code == 409 and "min < max" in bad.json()["detail"]
        r = client.post(f"/api/sessions/{sid}/jobs", json={"kind": "surrogate_build", "params": {
            "name": "Choke response", "method": "gp", "bounds": {"choke_pct": [25, 70]}, "outputs": ["oil_sm3_d", "choke_dp_bar"], "n_samples": 8}})
        assert r.status_code == 202
        jid = r.json()["id"]
        for _ in range(1200):
            j = client.get(f"/api/jobs/{jid}").json()
            if j["state"] not in ("pending", "running"):
                break
            time.sleep(0.05)
        assert j["state"] == "completed", j
        gid = j["result"]["id"]
        assert client.get("/api/surrogates").json()[0]["id"] == gid
        card = client.get(f"/api/surrogates/{gid}").json()
        assert card["n_cases"] == 8 and card["status"].startswith("Surrogate-model prediction") and card["inputs"][0]["min"] == 25
        p = client.post(f"/api/surrogates/{gid}/predict", json={"inputs": {"choke_pct": 45}}).json()
        assert p["envelope"]["inside"] and p["outputs"]["oil_sm3_d"]["std"] >= 0
        assert client.post(f"/api/surrogates/{gid}/predict", json={"inputs": {}}).status_code == 422
        chk = client.post(f"/api/sessions/{sid}/surrogates/{gid}/check", json={"inputs": {"choke_pct": 45}}).json()
        assert chk["outputs"]["oil_sm3_d"]["simulator"] == pytest.approx(chk["outputs"]["oil_sm3_d"]["surrogate"], rel=0.05)
        imp = client.post("/api/surrogates/import", json={"name": "Vendor data", "method": "poly", "inputs": ["choke_pct"], "outputs": ["oil_sm3_d"],
                                                          "csv": "choke_pct,oil_sm3_d,source\n" + "".join(f"{c},{10 * c + 0.1 * c * c},vendor\n" for c in range(20, 80, 6))})
        assert imp.status_code == 201 and imp.json()["card"]["sources"] == {"vendor": 10}
        assert client.post("/api/surrogates/import", json={"name": "x", "inputs": ["nope"], "outputs": ["oil_sm3_d"], "csv": ""}).status_code == 422
        assert client.delete(f"/api/surrogates/{gid}").status_code == 204
        assert client.get(f"/api/surrogates/{gid}").status_code == 404
