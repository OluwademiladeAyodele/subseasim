"""Background jobs: cooperative execution on the event loop, states,
progress, cancellation (partial work kept and reported), failure, one job
per session, and the API. The fast-forward job must give the same wear as
the synchronous fast-forward."""

from __future__ import annotations

import asyncio
import time
import warnings
from types import SimpleNamespace

import pytest

from app import job_kinds  # noqa: F401 - registers kinds
from app.jobs import JobAborted, JobManager, JobRejected

warnings.simplefilter("ignore", RuntimeWarning)


def _engine():
    from app.scenarios.loader import get_scenario
    from app.simulation.engine import SimulationEngine

    e = SimulationEngine(get_scenario("xt_230xp22b_multiphase"))
    e.load_sand_example()
    e.start()
    e.command_valve("CHK-101", "set_position", 70)
    e.advance(2 * 3600)
    return e


def _wear(e):
    return float(e.sand.dd_base.max()), e.sand.service_s, e.sand.cum["choke_kg"]


# ------------------------------------------------------------- generic runner
def _toy(n, fail_at=None, log=None):
    def work():
        try:
            for i in range(n):
                if fail_at is not None and i == fail_at:
                    raise JobAborted("toy failure")
                time.sleep(0.002)
                yield (i + 1) / n, f"{i + 1}/{n}"
            return {"message": "toy done", "n": n}
        finally:
            if log is not None:
                log.append("closed")
    return work()


def _mgr():
    m = JobManager()
    m.register("toy", lambda s, p: (f"toy {p['n']}", _toy(p["n"], p.get("fail_at"), p.get("log"))))
    return m


def test_runner_completes_reports_progress_and_yields_to_the_event_loop():
    async def main():
        m = _mgr()
        ticks = 0

        async def other():  # stands in for the simulation loop
            nonlocal ticks
            while True:
                ticks += 1
                await asyncio.sleep(0)

        t = asyncio.create_task(other())
        job = m.submit(SimpleNamespace(id="s1"), "toy", {"n": 100})
        assert job.state == "pending"
        done = await m.wait(job.id)
        t.cancel()
        return done, ticks

    job, ticks = asyncio.run(main())
    assert job.state == "completed" and job.progress == 1.0 and job.result == {"message": "toy done", "n": 100}
    assert job.message == "toy done" and job.started_at and job.finished_at
    assert ticks >= 3  # 100 x 2 ms of work was sliced: the loop ran in between


def test_cancel_closes_the_generator_and_failure_is_reported():
    async def main():
        m = _mgr()
        log: list = []
        j1 = m.submit(SimpleNamespace(id="s1"), "toy", {"n": 2000, "log": log})
        await asyncio.sleep(0.05)
        m.cancel(j1.id)
        j1 = await m.wait(j1.id)
        j2 = m.submit(SimpleNamespace(id="s1"), "toy", {"n": 10, "fail_at": 3})
        j2 = await m.wait(j2.id)
        return j1, j2, log

    j1, j2, log = asyncio.run(main())
    assert j1.state == "cancelled" and 0 < j1.progress < 1 and "cancelled by the user" in j1.message and log == ["closed"]
    assert j2.state == "failed" and j2.error == "toy failure"


def test_one_active_job_per_session_and_unknown_kind():
    async def main():
        m = _mgr()
        s = SimpleNamespace(id="s1")
        j = m.submit(s, "toy", {"n": 500})
        with pytest.raises(JobRejected, match="already running"):
            m.submit(s, "toy", {"n": 5})
        other = m.submit(SimpleNamespace(id="s2"), "toy", {"n": 5})  # another session is independent
        with pytest.raises(JobRejected, match="unknown job kind"):
            m.submit(SimpleNamespace(id="s3"), "nope", {})
        m.cancel(j.id)
        await m.wait(j.id)
        await m.wait(other.id)
        return m.get(other.id)

    assert asyncio.run(main()).state == "completed"


def test_jobs_are_listed_newest_first_even_within_the_same_second():
    async def main():
        m = _mgr()
        s = SimpleNamespace(id="s1")
        ids = []
        for _ in range(3):
            j = m.submit(s, "toy", {"n": 1})
            ids.append(j.id)
            await m.wait(j.id)
        return m, ids

    m, ids = asyncio.run(main())
    assert [j.id for j in m.for_session("s1")] == ids[::-1]


def test_job_stops_when_the_session_ends():
    async def main():
        m = _mgr()
        alive = {"v": True}
        j = m.submit(SimpleNamespace(id="s1"), "toy", {"n": 2000}, is_alive=lambda: alive["v"])
        await asyncio.sleep(0.03)
        alive["v"] = False
        return await m.wait(j.id)

    j = asyncio.run(main())
    assert j.state == "cancelled" and "session ended" in j.message


# ------------------------------------------------------------ fast-forward job
def test_fast_forward_job_equals_the_synchronous_fast_forward():
    a, b = _engine(), _engine()
    a.sand_fast_forward(45)
    gen_steps = list(b.sand_fast_forward_steps(45))
    assert len(gen_steps) == 45 and gen_steps[-1][0] == pytest.approx(1.0)
    assert _wear(a) == pytest.approx(_wear(b), rel=1e-12)


def test_fast_forward_cancel_keeps_the_days_done_and_logs_them():
    e = _engine()
    s0 = e.sand.service_s
    g = e.sand_fast_forward_steps(100)
    for _ in range(30):
        next(g)
    g.close()
    assert (e.sand.service_s - s0) / 86400 == pytest.approx(30)
    assert any("STOPPED after 30 of 100 days" in ev.message for ev in e.events.all())


def test_fast_forward_aborts_when_inputs_change_mid_job():
    e = _engine()
    g = e.sand_fast_forward_steps(100)
    next(g)
    e.set_sand_inputs(e.sand_inputs.model_copy(deep=True))
    with pytest.raises(JobAborted, match="inputs changed"):
        next(g)


def test_fast_forward_job_validates_before_queueing():
    from app.jobs import jobs

    e = _engine()
    s = SimpleNamespace(id="ff1", engine=e)
    for bad in (0, -1, 4000, "x", True):
        with pytest.raises(JobRejected):
            jobs.kinds["sand_fast_forward"](s, {"days": bad})


def test_api_runs_cancels_and_rejects_jobs():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        sid = client.post("/api/sessions", json={"scenario_id": "xt_230xp22b_multiphase"}).json()["session_id"]
        client.post(f"/api/sessions/{sid}/sand-choke/example")
        client.post(f"/api/sessions/{sid}/lifecycle", json={"action": "start"})
        r = client.post(f"/api/sessions/{sid}/jobs", json={"kind": "sand_fast_forward", "params": {"days": 60}})
        assert r.status_code == 202 and r.json()["state"] in ("pending", "running")
        jid = r.json()["id"]
        for _ in range(400):
            j = client.get(f"/api/jobs/{jid}").json()
            if j["state"] not in ("pending", "running"):
                break
            time.sleep(0.05)
        assert j["state"] == "completed" and j["result"]["days"] == 60
        assert j["result"]["service_days_after"] - j["result"]["service_days_before"] == pytest.approx(60)
        st = client.get(f"/api/sessions/{sid}").json()["state"]
        assert st["sand_choke"]["service_days"] == pytest.approx(j["result"]["service_days_after"])
        # cancel a long one
        jid2 = client.post(f"/api/sessions/{sid}/jobs", json={"kind": "sand_fast_forward", "params": {"days": 3650}}).json()["id"]
        assert client.post(f"/api/sessions/{sid}/jobs", json={"kind": "sand_fast_forward", "params": {"days": 1}}).status_code == 409
        client.post(f"/api/jobs/{jid2}/cancel")
        for _ in range(400):
            j2 = client.get(f"/api/jobs/{jid2}").json()
            if j2["state"] not in ("pending", "running"):
                break
            time.sleep(0.05)
        assert j2["state"] in ("cancelled", "completed")
        assert [x["id"] for x in client.get(f"/api/sessions/{sid}/jobs").json()][:2] == [jid2, jid]
        assert client.post(f"/api/sessions/{sid}/jobs", json={"kind": "nope"}).status_code == 409
        assert client.post(f"/api/sessions/{sid}/jobs", json={"kind": "sand_fast_forward", "params": {"days": -5}}).status_code == 409
        assert client.get("/api/jobs/unknown").status_code == 404
