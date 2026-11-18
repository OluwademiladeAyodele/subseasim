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

