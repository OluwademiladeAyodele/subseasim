"""Job kinds available through the background-job API (see app/jobs.py).

Each factory validates the request BEFORE anything is queued (raising
JobRejected with a readable message) and returns (label, work generator).
"""

from __future__ import annotations

import math

from app.jobs import JobRejected, jobs


def _sand_fast_forward(session, params: dict):
    days = params.get("days")
    if not isinstance(days, (int, float)) or isinstance(days, bool) or not math.isfinite(days) or not 0 < days <= 3650:
        raise JobRejected("days must be a number in (0, 3650]")
    e = session.engine
    if e.sand is None:
        raise JobRejected("sand and choke erosion need the three-phase fluid model")
    if e.sand.operating_point() is None and e.sand.last_op is None:
        raise JobRejected("no choke operating point yet - start the simulation first")

    def work():
        sv0 = e.sand.service_s
        yield from e.sand_fast_forward_steps(float(days))
        return {"message": f"fast-forwarded {days:g} days", "days": float(days),
                "service_days_before": sv0 / 86400, "service_days_after": e.sand.service_s / 86400,
                "health": e.sand.snapshot()["health"]["category"]}

    return f"Fast-forward choke wear {days:g} days", work()


jobs.register("sand_fast_forward", _sand_fast_forward)


def _scenario_comparison(session, params: dict):
    from pydantic import ValidationError

    from app.studies.comparison import StudyRequest, run_study

    try:
        req = StudyRequest.model_validate(params)
    except ValidationError as exc:
        raise JobRejected("; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())) from None
    n = len(req.variants) + 1
    return f"Scenario comparison: {n} cases over {req.horizon_days:g} days", run_study(session.engine, req)


jobs.register("scenario_comparison", _scenario_comparison)


def _surrogate_build(session, params: dict):
    from app.storage import records
    from app.surrogates.doe import simulate_cases
    from app.surrogates.model import INPUTS, OUTPUTS, build, min_cases

    name = str(params.get("name") or "").strip()
    method = params.get("method", "gp")
    bounds = params.get("bounds") or {}
    outputs = list(params.get("outputs") or [])
    n = params.get("n_samples", 30)
    if not name or len(name) > 80:
        raise JobRejected("name is required (at most 80 characters)")
    if method not in ("gp", "poly"):
        raise JobRejected("method must be 'gp' or 'poly'")
    if not bounds or any(k not in INPUTS for k in bounds):
        raise JobRejected(f"bounds must give [min, max] for inputs among: {', '.join(INPUTS)}")
    try:
        b = {k: (float(v[0]), float(v[1])) for k, v in bounds.items()}
    except (TypeError, ValueError, IndexError):
        raise JobRejected("each bound must be [min, max]") from None
    if any(not lo < hi for lo, hi in b.values()):
        raise JobRejected("each bound needs min < max")
    if not outputs or any(k not in OUTPUTS for k in outputs):
        raise JobRejected(f"outputs must be among: {', '.join(OUTPUTS)}")
    if not isinstance(n, int) or isinstance(n, bool) or not min_cases(method, len(b)) <= n <= 200:
        raise JobRejected(f"n_samples must be an integer from {min_cases(method, len(b))} to 200 for {method} with {len(b)} input(s)")
    e = session.engine
    if e.bo is None:
        raise JobRejected("surrogate training needs the three-phase (black-oil) fluid model")

    def work():
        cases = yield from simulate_cases(e, b, outputs, n)
        yield 0.99, "fitting and cross-validating the surrogate"
        sur = build(name, method, list(b), outputs, cases, bounds=b, scenario_id=e.scenario.id,
                    notes=[f"Latin-hypercube design of {n} simulator cases (steady twins of the session at t = {e.time_s:.0f} s)"])
        row = records.save_surrogate(sur)
        return {"message": f"surrogate '{name}' trained on {n} simulator cases", "id": row["id"], "card": sur.card()}

    return f"Train surrogate '{name}' ({method}, {n} cases)", work()


jobs.register("surrogate_build", _surrogate_build)
