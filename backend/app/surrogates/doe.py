"""Simulator design of experiments for surrogate training.

Latin-hypercube samples of the chosen inputs (scipy.stats.qmc, fixed seed),
each solved on a steady twin of the session with the SAME models as the
scenario comparison (app/studies/comparison.py). Every generated case is
tagged ``source = simulator``.
"""

from __future__ import annotations

import copy

from scipy.stats import qmc

from app.studies.comparison import Variant, _apply, metrics, steady_twin
from app.surrogates.model import INPUTS, OUTPUTS


def sample_points(bounds: dict[str, tuple[float, float]], n: int, seed: int = 7) -> list[dict]:
    keys = list(bounds)
    u = qmc.LatinHypercube(d=len(keys), seed=seed).random(n)
    lo = [bounds[k][0] for k in keys]
    hi = [bounds[k][1] for k in keys]
    pts = qmc.scale(u, lo, hi)
    return [{k: float(p[i]) for i, k in enumerate(keys)} for p in pts]


def simulate_cases(engine, bounds: dict[str, tuple[float, float]], outputs: list[str], n: int, seed: int = 7):
    """Generator (background job): yields (progress, message); returns the case list."""
    for k in bounds:
        if k not in INPUTS:
            raise ValueError(f"unknown input '{k}' (available: {', '.join(INPUTS)})")
    for k in outputs:
        if k not in OUTPUTS:
            raise ValueError(f"unknown output '{k}' (available: {', '.join(OUTPUTS)})")
    yield 0.0, "building the steady twin of the session"
    base = steady_twin(engine)
    cases = []
    for i, x in enumerate(sample_points(bounds, n, seed)):
        yield i / n, f"case {i + 1} of {n}"
        tw = copy.deepcopy(base)
        _apply(tw, Variant(label=f"doe{i + 1}", **x))
        m = metrics(tw)
        # the choke opening actually applied (actuator step grid) is the training input
        xa = dict(x)
        if "choke_pct" in xa and m.get("choke_pct") is not None:
            xa["choke_pct"] = m["choke_pct"]
        cases.append({"x": xa, "y": {k: m.get(k) for k in outputs}, "source": "simulator",
                      "reference": f"SubseaSim steady twin, scenario {engine.scenario.id}"})
    return cases


def parse_cases_csv(text: str, inputs: list[str], outputs: list[str]) -> list[dict]:
    """Imported cases (CFD, experiment, vendor, field): header row with the input
    and output keys plus ``source`` and optional ``reference``. Atomic."""
    import csv
    import io

    from app.surrogates.model import SOURCES

    rows = [r for r in csv.reader(io.StringIO(text.strip().lstrip("﻿"))) if any(c.strip() for c in r)]
    if not rows:
        raise ValueError("empty file")
    head = [h.strip() for h in rows[0]]
    need = inputs + outputs + ["source"]
    miss = [k for k in need if k not in head]
    if miss:
        raise ValueError(f"missing column(s): {', '.join(miss)}")
    errors, out = [], []
    for n, r in enumerate(rows[1:], start=2):
        d = {h: (r[i].strip() if i < len(r) else "") for i, h in enumerate(head)}
        try:
            src = d["source"].lower()
            if src not in SOURCES:
                raise ValueError(f"source must be one of {', '.join(SOURCES)}")
            out.append({"x": {k: float(d[k]) for k in inputs}, "y": {k: float(d[k]) for k in outputs}, "source": src,
                        "reference": d.get("reference") or None})
        except ValueError as exc:
            errors.append(f"line {n}: {exc}")
    if errors:
        raise ValueError("; ".join(errors))
    return out
