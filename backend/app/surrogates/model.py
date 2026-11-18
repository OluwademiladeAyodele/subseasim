"""Surrogate models: fast predictions inside a validated operating envelope.

A surrogate is trained on a CASE LIBRARY (inputs -> outputs), each case
tagged with its source: ``simulator`` (steady twins of a SubseaSim session,
generated here), or ``cfd`` / ``experiment`` / ``vendor`` / ``field``
(imported by the user - SubseaSim never generates such data). Two methods:

- ``gp``: Gaussian process (app/surrogates/gp.py) with a predictive standard
  deviation;
- ``poly``: quadratic response surface by least squares (light ridge),
  standard deviation from the residual variance and leverage.

Validation: leave-one-out cross-validation for every output (RMSE, R2 and
the coverage of the 95 % interval). A prediction is returned with its
interval, the model status ("Surrogate-model prediction"), the training
source and an ENVELOPE check: every input inside the training range, and the
nearest training case not further than the largest nearest-neighbour
gap of the training design.
Outside the envelope the prediction is flagged and a high-fidelity
(simulator) run is recommended.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime

import numpy as np

from app.surrogates import gp as gpm

MODEL_VERSION = "1.0"

#: Inputs a simulator design can vary (Variant fields of the comparison study).
INPUTS = {
    "choke_pct": ("Choke opening", "%"),
    "reservoir_pressure_bara": ("Reservoir pressure", "bara"),
    "downstream_pressure_bara": ("Manifold pressure", "bara"),
    "water_cut": ("Water cut", "fraction"),
    "gor_sm3_sm3": ("GOR", "Sm3/Sm3"),
    "sand_rate_kg_d": ("Sand rate", "kg/d"),
    "d50_um": ("Median grain size D50", "um"),
}
#: Outputs (metrics of the comparison study).
OUTPUTS = {
    "oil_sm3_d": ("Oil rate", "Sm3/d"),
    "gas_sm3_d": ("Gas rate", "Sm3/d"),
    "water_sm3_d": ("Water rate", "Sm3/d"),
    "choke_dp_bar": ("Choke differential", "bar"),
    "drawdown_bar": ("Drawdown", "bar"),
    "risk_index": ("Sanding risk index", "-"),
    "sand_at_choke_kg_d": ("Sand at the choke", "kg/d"),
    "jet_velocity_m_s": ("Choke jet velocity", "m/s"),
    "hole_rate_mm_y": ("Cage-hole wear rate", "mm/yr"),
}
SOURCES = ("simulator", "cfd", "experiment", "vendor", "field")
Z95 = 1.959964
SPARSE_FACTOR = 1.0  # a query further from every case than any case is from its neighbour: a void larger than any in the design


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


# ------------------------------------------------------------ poly surface
def _quad_features(x: np.ndarray) -> np.ndarray:
    n, d = x.shape
    cols = [np.ones(n)] + [x[:, i] for i in range(d)]
    cols += [x[:, i] * x[:, j] for i in range(d) for j in range(i, d)]
    return np.column_stack(cols)


@dataclass
class Poly:
    beta: np.ndarray
    xtx_inv: np.ndarray
    sigma: float
    loo_mu: np.ndarray
    loo_sd: np.ndarray

    def predict(self, xs: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        f = _quad_features(xs)
        lev = np.einsum("ij,jk,ik->i", f, self.xtx_inv, f)
        return f @ self.beta, self.sigma * np.sqrt(1.0 + lev)


def fit_poly(x: np.ndarray, y: np.ndarray, ridge: float = 1e-6) -> Poly:
    f = _quad_features(x)
    n, p = f.shape
    a = f.T @ f + ridge * np.eye(p)
    ainv = np.linalg.inv(a)
    beta = ainv @ f.T @ y
    res = y - f @ beta
    h = np.einsum("ij,jk,ik->i", f, ainv, f)
    dof = max(n - p, 1)
    sigma = float(np.sqrt(np.sum(res**2) / dof))
    loo_res = res / np.maximum(1.0 - h, 1e-9)  # PRESS residuals
    return Poly(beta=beta, xtx_inv=ainv, sigma=sigma, loo_mu=y - loo_res, loo_sd=sigma * np.sqrt(1.0 + h / np.maximum(1 - h, 1e-9)))


def min_cases(method: str, d: int) -> int:
    return (1 + d + d * (d + 1) // 2) + 3 if method == "poly" else max(6, 2 * d + 2)


# --------------------------------------------------------------- the model
@dataclass
class Surrogate:
    name: str
    method: str
    inputs: list[str]
    outputs: list[str]
    lo: np.ndarray
    hi: np.ndarray
    cases: list[dict]  # {"x": {...}, "y": {...}, "source": ..., "reference": ...}
    scenario_id: str | None = None
    created_at: str = field(default_factory=_now)
    models: dict = field(default_factory=dict)
    validation: dict = field(default_factory=dict)
    spacing: float = 0.0
    notes: list[str] = field(default_factory=list)

    # ---------------------------------------------------------- scaling
    def scale(self, xs: np.ndarray) -> np.ndarray:
        span = np.where(self.hi > self.lo, self.hi - self.lo, 1.0)
        return (xs - self.lo) / span

    def _matrix(self) -> np.ndarray:
        return np.array([[c["x"][k] for k in self.inputs] for c in self.cases], float)

    # -------------------------------------------------------------- fit
    def train(self) -> None:
        x = self.scale(self._matrix())
        n = len(x)
        if n < min_cases(self.method, len(self.inputs)):
            raise ValueError(f"{self.method} with {len(self.inputs)} inputs needs at least {min_cases(self.method, len(self.inputs))} cases (have {n})")
        nn = np.sqrt(((x[:, None, :] - x[None, :, :]) ** 2).sum(-1))
        np.fill_diagonal(nn, np.inf)
        # largest gap between a case and its nearest neighbour: a query further than
        # this from every case lies in a void larger than any in the design (sparse region)
        self.spacing = float(nn.min(axis=1).max()) if n > 1 else 0.0
        self.models, self.validation = {}, {}
        for k in self.outputs:
            y = np.array([c["y"][k] for c in self.cases], float)
            m = gpm.fit(x, y) if self.method == "gp" else fit_poly(x, y)
            self.models[k] = m
            mu, sd = m.loo() if self.method == "gp" else (m.loo_mu, m.loo_sd)
            err = mu - y
            ss = float(np.sum((y - y.mean()) ** 2))
            self.validation[k] = {
                "loo_rmse": float(np.sqrt(np.mean(err**2))),
                "loo_r2": None if ss <= 0 else float(1 - np.sum(err**2) / ss),
                "loo_coverage_95": float(np.mean(np.abs(err) <= Z95 * np.maximum(sd, 1e-12))),
                "y_min": float(y.min()), "y_max": float(y.max()),
                "loo_points": [[float(a), float(b)] for a, b in zip(y, mu)],
            }

    # ---------------------------------------------------------- predict
    def envelope(self, xq: dict) -> dict:
        raw = np.array([float(xq[k]) for k in self.inputs])
        outside = [{"input": k, "value": float(raw[i]), "min": float(self.lo[i]), "max": float(self.hi[i])}
                   for i, k in enumerate(self.inputs) if raw[i] < self.lo[i] - 1e-9 or raw[i] > self.hi[i] + 1e-9]
        xs = self.scale(raw[None, :])
        d = float(np.sqrt(((self.scale(self._matrix()) - xs) ** 2).sum(-1)).min())
        sparse = d > SPARSE_FACTOR * self.spacing if self.spacing > 0 else False
        inside = not outside and not sparse
        msg = ("Inside the validated envelope." if inside else
               ("Outside the training range: " + ", ".join(f"{o['input']} = {o['value']:g} (trained {o['min']:g} - {o['max']:g})" for o in outside) + ". "
                if outside else "") + ("Far from the training cases (sparse region). " if sparse else "") +
               "Run a high-fidelity calculation for this point; the surrogate is not validated here.")
        return {"inside": inside, "outside_inputs": outside, "nearest_case_distance": d, "typical_spacing": self.spacing,
                "sparse": sparse, "message": msg}

    def predict(self, xq: dict) -> dict:
        missing = [k for k in self.inputs if k not in xq]
        if missing:
            raise ValueError(f"missing inputs: {', '.join(missing)}")
        xs = self.scale(np.array([[float(xq[k]) for k in self.inputs]]))
        env = self.envelope(xq)
        out = {}
        for k, m in self.models.items():
            mu, sd = m.predict(xs)
            out[k] = {"mean": float(mu[0]), "std": float(sd[0]), "p2_5": float(mu[0] - Z95 * sd[0]), "p97_5": float(mu[0] + Z95 * sd[0]),
                      "label": OUTPUTS.get(k, (k, ""))[0], "unit": OUTPUTS.get(k, ("", ""))[1]}
        return {"inputs": {k: float(xq[k]) for k in self.inputs}, "outputs": out, "envelope": env, "status": self.status,
                "trained_on": self.source_summary}

    # ------------------------------------------------------------ cards
    @property
    def source_summary(self) -> dict:
        s: dict[str, int] = {}
        for c in self.cases:
            s[c["source"]] = s.get(c["source"], 0) + 1
        return s

    @property
    def status(self) -> str:
        srcs = set(self.source_summary)
        what = "simulator data (SubseaSim steady twins), not CFD or field data" if srcs == {"simulator"} else \
            "imported " + " / ".join(sorted(srcs)) + " data"
        return f"Surrogate-model prediction - trained on {what}"

    def card(self) -> dict:
        return {"name": self.name, "method": self.method, "model_version": MODEL_VERSION, "scenario_id": self.scenario_id,
                "created_at": self.created_at, "inputs": [{"key": k, "label": INPUTS.get(k, (k, ""))[0], "unit": INPUTS.get(k, ("", ""))[1],
                                                           "min": float(self.lo[i]), "max": float(self.hi[i])} for i, k in enumerate(self.inputs)],
                "outputs": [{"key": k, "label": OUTPUTS.get(k, (k, ""))[0], "unit": OUTPUTS.get(k, ("", ""))[1]} for k in self.outputs],
                "n_cases": len(self.cases), "sources": self.source_summary, "status": self.status, "validation": self.validation,
                "typical_spacing": self.spacing, "notes": self.notes,
                "limitations": [
                    "Valid only inside the training envelope; outside it a high-fidelity calculation is required.",
                    "It reproduces its training data source and inherits all of its limitations - a surrogate of the simulator is not "
                    "more accurate than the simulator.",
                    "Cross-validation measures how well the surrogate reproduces its training source, not the accuracy of that source.",
                    "Step changes (e.g. sanding onset at risk index 1) are smoothed; check the cross-validation of those outputs.",
                ]}

    # ---------------------------------------------------------- storage
    def to_dict(self) -> dict:
        return {"name": self.name, "method": self.method, "inputs": self.inputs, "outputs": self.outputs, "lo": self.lo.tolist(),
                "hi": self.hi.tolist(), "cases": self.cases, "scenario_id": self.scenario_id, "created_at": self.created_at,
                "notes": self.notes, "model_version": MODEL_VERSION}

    @classmethod
    def from_dict(cls, d: dict) -> Surrogate:
        s = cls(name=d["name"], method=d["method"], inputs=d["inputs"], outputs=d["outputs"], lo=np.array(d["lo"], float),
                hi=np.array(d["hi"], float), cases=d["cases"], scenario_id=d.get("scenario_id"), created_at=d["created_at"],
                notes=d.get("notes", []))
        s.train()  # deterministic: same cases -> same model
        return s


def build(name: str, method: str, inputs: list[str], outputs: list[str], cases: list[dict], bounds: dict | None = None,
          scenario_id: str | None = None, notes: list[str] | None = None) -> Surrogate:
    if method not in ("gp", "poly"):
        raise ValueError("method must be 'gp' or 'poly'")
    if not inputs or not outputs:
        raise ValueError("at least one input and one output are needed")
    ok = []
    dropped = 0
    for c in cases:
        if c.get("source") not in SOURCES:
            raise ValueError(f"case source must be one of {', '.join(SOURCES)}")
        vals = [c["x"].get(k) for k in inputs] + [c["y"].get(k) for k in outputs]
        if all(v is not None and isinstance(v, (int, float)) and math.isfinite(v) for v in vals):
            ok.append(c)
        else:
            dropped += 1
    x = np.array([[c["x"][k] for k in inputs] for c in ok], float) if ok else np.zeros((0, len(inputs)))
    lo = np.array([bounds[k][0] if bounds and k in bounds else (x[:, i].min() if len(x) else 0.0) for i, k in enumerate(inputs)], float)
    hi = np.array([bounds[k][1] if bounds and k in bounds else (x[:, i].max() if len(x) else 1.0) for i, k in enumerate(inputs)], float)
    s = Surrogate(name=name, method=method, inputs=inputs, outputs=outputs, lo=lo, hi=hi, cases=ok, scenario_id=scenario_id,
                  notes=list(notes or []) + ([f"{dropped} case(s) without a value for every input and output were left out"] if dropped else []))
    s.train()
    return s
