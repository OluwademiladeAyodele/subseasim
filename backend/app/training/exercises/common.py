"""Helpers shared by the tree-workstation exercises (Exercises 1, 2, 4, 5, 6,
8 and 9). Every condition reads the SIMULATION STATE; every number in a
review comes from observations recorded in the trainee's own run.
"""

from __future__ import annotations

from typing import Any

from app.core import units as u
from app.simulation.engine import SimulationEngine

#: Transmitters recorded at every observation (tree workstation tags).
KEY_TAGS = ("PT-001", "PT-101", "PT-104", "PT-105", "PT-102", "PT-103", "PDT-101", "PT-201", "FT-101", "TT-104", "TT-103",
            "PT-401", "PT-402", "PT-404", "PT-403", "FT-301", "FT-302", "AT-510", "AT-511", "AT-512", "AT-521", "AT-522")
VALVES = ("SCSSV-101", "PMV-101", "PWV-101", "CHK-101", "SV-101", "AMV-101", "AWV-101", "XOV-101", "SLV-101", "CIV-301", "CIV-302",
          "MIV-302", "MIV-303")


def running(e: SimulationEngine) -> bool:
    return e.status == "running"


def pos(e: SimulationEngine, tag: str) -> float:
    return e.restrictions[tag].actuator.position_pct


def quantised(e: SimulationEngine, tag: str, target: float) -> float:
    """The position the actuator actually goes to for ``target`` (stepping chokes
    move on a step grid, e.g. 10 % -> 10.3 % with 165 steps)."""
    steps = getattr(e.restrictions[tag], "steps", None)
    return round(target / 100.0 * steps) / steps * 100.0 if steps else target


def at(e: SimulationEngine, tag: str, target: float, tol: float = 0.05) -> bool:
    """Valve commanded to and arrived at ``target`` % (not moving)."""
    target = quantised(e, tag, target)
    a = e.restrictions[tag].actuator
    return abs(a.commanded_pct - target) <= tol and abs(a.position_pct - target) <= tol and not a.is_moving


def is_open(e: SimulationEngine, tag: str) -> bool:
    return at(e, tag, 100.0)


def is_closed(e: SimulationEngine, tag: str) -> bool:
    return at(e, tag, 0.0)


def value(e: SimulationEngine, tag: str) -> float | None:
    r = e.readings.get(tag)
    return None if r is None else r.value


def bara(e: SimulationEngine, tag: str) -> float | None:
    v = value(e, tag)
    return None if v is None else u.pa_to_bara(v)


def bar(e: SimulationEngine, tag: str) -> float | None:
    v = value(e, tag)
    return None if v is None else u.pa_to_bar_delta(v)


def m3d(e: SimulationEngine, tag: str) -> float | None:
    v = value(e, tag)
    return None if v is None else u.m3s_to_m3d(v)


def capture(e: SimulationEngine) -> dict[str, Any]:
    out: dict[str, Any] = {"sim_time_s": e.time_s, "valves": {t: pos(e, t) for t in VALVES if t in e.restrictions}}
    for t in KEY_TAGS:
        v = value(e, t)
        if v is None:
            out[t] = None
        elif t.startswith("PDT"):
            out[t] = u.pa_to_bar_delta(v)
        elif t.startswith("PT"):
            out[t] = u.pa_to_bara(v)
        elif t.startswith("FT"):
            out[t] = u.m3s_to_m3d(v)
        elif t.startswith("TT"):
            out[t] = u.k_to_c(v)
        else:
            out[t] = float(v)
    ctrl = getattr(e, "ctrl", None)
    if ctrl is not None:
        out["supply_ok"] = {s: ctrl.supply_ok(s) for s in ("LP", "HP")}
    return out


class Held:
    """Condition that must stay true for ``seconds`` of SIMULATION time
    (e.g. "PMV open for 5 minutes") before the task completes."""

    def __init__(self, cond, seconds: float):
        self.cond, self.seconds = cond, seconds
        self.since: dict[int, float] = {}

    def __call__(self, e: SimulationEngine) -> bool:
        k = id(e)
        if not (running(e) and self.cond(e)):
            self.since.pop(k, None)
            return False
        t0 = self.since.setdefault(k, e.time_s)
        return e.time_s - t0 >= self.seconds

    def remaining(self, e: SimulationEngine) -> float:
        t0 = self.since.get(id(e))
        return self.seconds if t0 is None else max(self.seconds - (e.time_s - t0), 0.0)


def travel_hint(e: SimulationEngine, tag: str, target: float, what: str) -> str:
    """Generic hint for a valve task."""
    if not running(e):
        return "Press START (or RESUME): valves only travel while simulation time runs."
    a = e.restrictions[tag].actuator
    if abs(a.commanded_pct - quantised(e, tag, target)) > 0.05:
        return f"Select {tag} on the Christmas tree and {what}."
    return f"{tag} is travelling: {a.position_pct:.0f} % -> {a.commanded_pct:.0f} % (about {a.time_to_target():.0f} s of simulation time)."


def fmt(v: float | None, d: int = 1) -> str:
    return "n/a" if v is None else f"{v:.{d}f}"


def table(obs: dict, rows: list[tuple[str, str]], cols: list[tuple[str, str, int]]) -> dict:
    """Review table: rows = (observation key, label), cols = (field, header, decimals)."""
    out_rows = []
    for key, label in rows:
        o = obs.get(key)
        if not o:
            continue
        cells = [label]
        for f, _h, d in cols:
            v = o.get(f) if not f.startswith("valves.") else o["valves"].get(f.split(".", 1)[1])
            cells.append(fmt(v, d))
        out_rows.append(cells)
    return {"columns": ["Step"] + [h for _f, h, _d in cols], "rows": out_rows}


def bins(v: float | None, edges: list[float], ids: list[str]) -> str | None:
    """Option id for a value: ids[i] when edges[i-1] <= v < edges[i]."""
    if v is None:
        return None
    for i, edge in enumerate(edges):
        if v < edge:
            return ids[i]
    return ids[len(edges)]
