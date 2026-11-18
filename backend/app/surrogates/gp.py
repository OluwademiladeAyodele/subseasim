"""Gaussian process regression (numpy / scipy only).

Kernel: squared exponential with automatic relevance determination plus
white noise,

    k(x, x') = s_f^2 exp(-1/2 sum_k ((x_k - x'_k) / l_k)^2) + s_n^2 delta,

on inputs scaled to [0, 1] and outputs standardised. Hyper-parameters
(log l_k, log s_f, log s_n) maximise the log marginal likelihood
(Rasmussen & Williams, Gaussian Processes for Machine Learning, 2006,
eq. 2.30 and 5.9) with L-BFGS-B from several starts. Leave-one-out
predictions use the closed form of R&W eq. 5.12:

    mu_-i = y_i - [K^-1 y]_i / [K^-1]_ii,   var_-i = 1 / [K^-1]_ii.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.linalg import cho_factor, cho_solve
from scipy.optimize import minimize

#: Bounds on log hyper-parameters (scaled units): length scales 0.03-30,
#: signal 0.05-20 (standardised outputs), noise 1e-4-1.
_B_L = (math.log(0.03), math.log(30.0))
_B_F = (math.log(0.05), math.log(20.0))
_B_N = (math.log(1e-4), math.log(1.0))


def _kernel(a: np.ndarray, b: np.ndarray, ell: np.ndarray, sf2: float) -> np.ndarray:
    d = (a[:, None, :] - b[None, :, :]) / ell
    return sf2 * np.exp(-0.5 * np.sum(d * d, axis=-1))


@dataclass
class GP:
    x: np.ndarray  # (n, d) scaled inputs
    yn: np.ndarray  # standardised training outputs
    y_mean: float
    y_std: float
    log_ell: np.ndarray
    log_sf: float
    log_sn: float
    alpha: np.ndarray  # K^-1 y (standardised)
    chol: tuple

    @property
    def params(self) -> dict:
        return {"length_scales": np.exp(self.log_ell).tolist(), "signal_std": math.exp(self.log_sf),
                "noise_std": math.exp(self.log_sn), "y_mean": self.y_mean, "y_std": self.y_std}

    def predict(self, xs: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Mean and standard deviation (output units) at scaled inputs xs."""
        ell, sf2 = np.exp(self.log_ell), math.exp(2 * self.log_sf)
        ks = _kernel(xs, self.x, ell, sf2)
        mu = ks @ self.alpha
        v = cho_solve(self.chol, ks.T)
        var = np.maximum(sf2 - np.sum(ks * v.T, axis=1), 0.0) + math.exp(2 * self.log_sn)
        return self.y_mean + self.y_std * mu, self.y_std * np.sqrt(var)

    def loo(self) -> tuple[np.ndarray, np.ndarray]:
        """Leave-one-out mean and standard deviation (output units), R&W eq. 5.12."""
        d = np.diag(cho_solve(self.chol, np.eye(len(self.x))))
        mu = self.yn - self.alpha / d
        return self.y_mean + self.y_std * mu, self.y_std * np.sqrt(1.0 / d)


def _nlml(theta: np.ndarray, x: np.ndarray, y: np.ndarray) -> float:
    d = x.shape[1]
    ell, sf2, sn2 = np.exp(theta[:d]), math.exp(2 * theta[d]), math.exp(2 * theta[d + 1])
    k = _kernel(x, x, ell, sf2) + (sn2 + 1e-10) * np.eye(len(x))
    try:
        c = cho_factor(k, lower=True)
    except np.linalg.LinAlgError:
        return 1e25
    a = cho_solve(c, y)
    return float(0.5 * y @ a + np.sum(np.log(np.diag(c[0]))) + 0.5 * len(x) * math.log(2 * math.pi))


def fit(x: np.ndarray, y: np.ndarray, restarts: int = 4, seed: int = 0) -> GP:
    """Fit a GP to scaled inputs x (n, d) and outputs y (n,)."""
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    n, d = x.shape
    ym, ys = float(np.mean(y)), float(np.std(y))
    ys = ys if ys > 1e-12 else 1.0
    yn = (y - ym) / ys
    rng = np.random.default_rng(seed)
    bounds = [_B_L] * d + [_B_F, _B_N]
    starts = [np.r_[np.full(d, math.log(0.5)), 0.0, math.log(0.01)]]
    starts += [np.r_[rng.uniform(math.log(0.1), math.log(3.0), d), rng.uniform(-0.5, 0.5), rng.uniform(math.log(1e-3), math.log(0.1))]
               for _ in range(max(0, restarts - 1))]
    best = None
    for t0 in starts:
        r = minimize(_nlml, t0, args=(x, yn), method="L-BFGS-B", bounds=bounds)
        if best is None or r.fun < best.fun:
            best = r
    th = best.x
    ell, sf2, sn2 = np.exp(th[:d]), math.exp(2 * th[d]), math.exp(2 * th[d + 1])
    k = _kernel(x, x, ell, sf2) + (sn2 + 1e-10) * np.eye(n)
    c = cho_factor(k, lower=True)
    return GP(x=x, yn=yn, y_mean=ym, y_std=ys, log_ell=th[:d].copy(), log_sf=float(th[d]), log_sn=float(th[d + 1]),
              alpha=cho_solve(c, yn), chol=c)
