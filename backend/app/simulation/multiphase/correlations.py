"""Multiphase pipe-flow and choke correlations (vectorised).

Beggs & Brill (1973) with the Payne et al. (1979) holdup corrections and a
rough-pipe (Churchill) no-slip friction factor:

    flow pattern from (lambda_L, N_Fr): segregated / transition /
    intermittent / distributed; horizontal holdup H_L(0) = a lambda^b / N_Fr^c;
    inclination correction psi = 1 + C [sin(1.8 theta) - sin^3(1.8 theta)/3];
    friction f_tp = f_ns exp(S), S = S(lambda / H_L^2);
    dp/dz = rho_s g sin(theta) + f_tp rho_ns v_m^2 / (2 D)  (+ acceleration,
    steady solver only).

Homogeneous (no-slip) model: H_L = lambda_L, f = f_ns - kept for comparison
and as the fallback for single-phase segments.

Sachdeva, Schmidt, Brill & Blais (1986) choke model: critical pressure ratio
from the frozen-composition isentropic expansion of a gas-liquid mixture,
then the mass flux for sub-critical or critical flow. In the liquid-only
limit it reduces exactly to the orifice equation W = C_dA sqrt(2 rho dP)
used by the single-phase model, so the configured choke capacity (Cv
characteristic) is reused unchanged.

Validity (documented in docs/MULTIPHASE_FLOW_MODEL.md): B&B was derived from
1 in and 1.5 in acrylic pipe, air-water, inclinations -90..+90 deg; it is
widely used for flowlines and is applied here to tubing as well (labelled).
Slugging, terrain-induced transients and phase-slip dynamics are NOT
simulated: holdup is evaluated quasi-steadily from local conditions.
"""

from __future__ import annotations

import math

import numpy as np

G = 9.80665

SEGREGATED, TRANSITION, INTERMITTENT, DISTRIBUTED, SINGLE_LIQUID, SINGLE_GAS = 0, 1, 2, 3, 4, 5
PATTERN_NAMES = {SEGREGATED: "segregated", TRANSITION: "transition", INTERMITTENT: "intermittent",
                 DISTRIBUTED: "distributed", SINGLE_LIQUID: "liquid", SINGLE_GAS: "gas"}

_HL0 = {SEGREGATED: (0.98, 0.4846, 0.0868), INTERMITTENT: (0.845, 0.5351, 0.0173), DISTRIBUTED: (1.065, 0.5824, 0.0609)}
_C_UP = {SEGREGATED: (0.011, -3.768, 3.539, -1.614), INTERMITTENT: (2.96, 0.305, -0.4473, 0.0978)}
_C_DOWN = (4.70, -0.3692, 0.1244, -0.5056)


def churchill(re, rel_rough):
    re = np.maximum(re, 1e-9)
    a = (2.457 * np.log(1.0 / ((7.0 / re) ** 0.9 + 0.27 * rel_rough))) ** 16
    b = (37530.0 / re) ** 16
    return 8.0 * ((8.0 / re) ** 12 + (a + b) ** -1.5) ** (1.0 / 12.0)


def flow_pattern(lam, nfr):
    lam = np.clip(lam, 1e-9, 1.0)
    l1 = 316.0 * lam**0.302
    l2 = 0.0009252 * lam**-2.4684
    l3 = 0.10 * lam**-1.4516
    l4 = 0.5 * lam**-6.738
    pat = np.full(lam.shape, DISTRIBUTED)
    seg = ((lam < 0.01) & (nfr < l1)) | ((lam >= 0.01) & (nfr < l2))
    tra = (lam >= 0.01) & (nfr >= l2) & (nfr <= l3)
    inter = ((lam >= 0.01) & (lam < 0.4) & (nfr > l3) & (nfr <= l1)) | ((lam >= 0.4) & (nfr > l3) & (nfr <= l4))
    pat = np.where(inter, INTERMITTENT, pat)
    pat = np.where(tra, TRANSITION, pat)
    pat = np.where(seg, SEGREGATED, pat)
    return pat, l2, l3


def _holdup_for(pattern: int, lam, nfr, nlv, theta):
    a, b, c = _HL0[pattern]
    hl0 = np.maximum(a * lam**b / np.maximum(nfr, 1e-12) ** c, lam)
    uphill = theta >= 0
    if pattern == DISTRIBUTED:
        cc_up = np.zeros_like(lam)
    else:
        d, e, f, g = _C_UP[pattern]
        cc_up = (1 - lam) * np.log(np.maximum(d * lam**e * nlv**f * np.maximum(nfr, 1e-12) ** g, 1e-300))
    d, e, f, g = _C_DOWN
    cc_dn = (1 - lam) * np.log(np.maximum(d * lam**e * nlv**f * np.maximum(nfr, 1e-12) ** g, 1e-300))
    cc = np.maximum(np.where(uphill, cc_up, cc_dn), 0.0)
    s = np.sin(1.8 * theta)
    psi = 1.0 + cc * (s - s**3 / 3.0)
    hl = hl0 * psi
    # Payne et al. (1979) corrections
    hl = np.where(uphill, hl * 0.924, hl * 0.685)
    hl = np.where(uphill, np.maximum(hl, lam), hl)
    return np.clip(hl, 1e-6, 1.0)


def beggs_brill(v_sl, v_sg, rho_l, rho_g, mu_l, mu_g, sigma, d, theta, rough, correlation: str = "beggs_brill"):
    """Local gradient components for a two-phase (gas-liquid) mixture.

    Arrays broadcast; theta = inclination from horizontal [rad], positive
    upward along the flow direction. Returns dict with holdup H_L, pattern,
    slip density rho_s, no-slip density rho_ns, gravity gradient
    rho_s g sin(theta) [Pa/m], friction gradient [Pa/m] (sign of v_m) and
    the two-phase friction multiplier exp(S)."""
    v_sl, v_sg = np.maximum(np.asarray(v_sl, float), 0.0), np.maximum(np.asarray(v_sg, float), 0.0)
    v_m = v_sl + v_sg
    vm_safe = np.maximum(v_m, 1e-12)
    lam = np.where(v_m > 0, v_sl / vm_safe, np.where(v_sg > 0, 0.0, 1.0))
    lam = np.broadcast_to(lam, np.broadcast(lam, rho_l, d, theta).shape).astype(float)
    rho_ns = rho_l * lam + rho_g * (1 - lam)
    mu_ns = mu_l * lam + mu_g * (1 - lam)
    nfr = v_m**2 / (G * d)
    nlv = v_sl * (rho_l / (G * np.maximum(sigma, 1e-4))) ** 0.25
    theta = np.broadcast_to(np.asarray(theta, float), lam.shape)
    liquid = lam >= 1.0 - 1e-6
    gas = lam <= 1e-6
    if correlation == "no_slip":
        hl = lam.copy()
        pat = np.where(liquid, SINGLE_LIQUID, np.where(gas, SINGLE_GAS, DISTRIBUTED))
    else:
        pat, l2, l3 = flow_pattern(lam, nfr)
        lam_c = np.clip(lam, 1e-6, 1.0)
        nlv_c = np.maximum(nlv, 1e-6)
        hl = np.empty_like(lam_c)
        for p_ in (SEGREGATED, INTERMITTENT, DISTRIBUTED):
            m = pat == p_
            if m.any():
                hl[m] = _holdup_for(p_, lam_c[m], nfr[m], nlv_c[m], theta[m])
        m = pat == TRANSITION
        if m.any():
            a = (l3[m] - nfr[m]) / np.maximum(l3[m] - l2[m], 1e-12)
            hl[m] = a * _holdup_for(SEGREGATED, lam_c[m], nfr[m], nlv_c[m], theta[m]) + (1 - a) * _holdup_for(
                INTERMITTENT, lam_c[m], nfr[m], nlv_c[m], theta[m])
        hl = np.where(liquid, 1.0, np.where(gas, 0.0, hl))
        pat = np.where(liquid, SINGLE_LIQUID, np.where(gas, SINGLE_GAS, pat))
    rho_s = rho_l * hl + rho_g * (1 - hl)
    re = rho_ns * v_m * d / np.maximum(mu_ns, 1e-9)
    f_ns = churchill(np.maximum(re, 1.0), rough / d)
    # laminar limit consistent with the single-phase network (f = 64/Re below Re = 1)
    if correlation == "no_slip":
        es = np.ones_like(lam)
    else:
        y = np.where(liquid | gas, 1.0, lam / np.maximum(hl, 1e-9) ** 2)
        ln_y = np.log(np.maximum(y, 1e-12))
        s = ln_y / (-0.0523 + 3.182 * ln_y - 0.8725 * ln_y**2 + 0.01853 * ln_y**4)
        with np.errstate(invalid="ignore", divide="ignore"):
            s = np.where((y > 1.0) & (y < 1.2), np.log(np.maximum(2.2 * y - 1.2, 1e-12)), s)
        s = np.where(liquid | gas | (np.abs(ln_y) < 1e-12), 0.0, s)
        es = np.exp(s)
    f_tp = f_ns * es
    grad_f = f_tp * rho_ns * v_m * np.abs(v_m) / (2 * d)
    grad_g = rho_s * G * np.sin(theta)
    return {"holdup": hl, "lambda_l": lam, "pattern": pat, "rho_s": rho_s, "rho_ns": rho_ns, "mu_ns": mu_ns,
            "v_m": v_m, "n_fr": nfr, "n_lv": nlv, "f_ns": f_ns, "friction_multiplier": es,
            "grad_gravity": grad_g, "grad_friction": grad_f, "reynolds_ns": re}


# --------------------------------------------------------------- choke
def sachdeva_critical_ratio(x1, rho_l, v_g1, k: float, cv_ratio_term):
    """Critical pressure ratio y_c (Sachdeva et al. 1986), frozen flow.

    x1 free-gas mass fraction upstream; v_g1 gas specific volume upstream
    [m3/kg]; ``cv_ratio_term`` = n = 1 + x1 (cp - cv) / (x1 cv + (1 - x1) c_L)."""
    x1 = np.clip(np.asarray(x1, float), 1e-9, 1.0)
    v_l = 1.0 / rho_l
    n = cv_ratio_term
    kk = k / (k - 1.0)
    r = (1 - x1) * v_l / (x1 * v_g1)

    def rhs(y):
        v_g2 = v_g1 * y ** (-1.0 / k)
        r2 = (1 - x1) * v_l / (x1 * v_g2)
        return ((kk + r * (1 - y)) / (kk + n / 2 + n * r2 + n / 2 * r2 * r2)) ** kk

    # h(y) = y - rhs(y) is negative at y -> 0 and positive at y = 1: bisection
    lo = np.full(x1.shape, 1e-6)
    hi = np.ones(x1.shape)
    for _ in range(40):
        mid = 0.5 * (lo + hi)
        neg = mid - rhs(mid) < 0
        lo = np.where(neg, mid, lo)
        hi = np.where(neg, hi, mid)
    return 0.5 * (lo + hi)


def sachdeva_mass_flow(p1, p2, x1, rho_l, rho_g1, cda, k: float, cp_g: float, c_l: float):
    """Mass flow through a choke of effective area C_d A [m2] (Sachdeva).

    Returns (W [kg/s], y_c, critical flag). For x1 -> 0 this is exactly
    W = C_dA sqrt(2 rho_l (p1 - p2))."""
    p1, p2 = np.asarray(p1, float), np.asarray(p2, float)
    x1 = np.clip(np.asarray(x1, float), 0.0, 1.0)
    v_l = 1.0 / rho_l
    v_g1 = 1.0 / np.maximum(rho_g1, 1e-6)
    cv = cp_g / k
    n = 1.0 + x1 * (cp_g - cv) / np.maximum(x1 * cv + (1 - x1) * c_l, 1e-9)
    has_gas = x1 > 1e-7
    yc = np.where(has_gas, sachdeva_critical_ratio(np.where(has_gas, x1, 0.5), rho_l, v_g1, k, n), 0.0)
    y_act = np.clip(p2 / np.maximum(p1, 1.0), 0.0, 1.0)
    y = np.maximum(y_act, yc)
    critical = has_gas & (y_act < yc)
    kk = k / (k - 1.0)
    v_g2 = v_g1 * np.maximum(y, 1e-6) ** (-1.0 / k)
    rho_m2 = 1.0 / (x1 * v_g2 + (1 - x1) * v_l)
    term = (1 - x1) * (1 - y) * v_l + x1 * kk * (v_g1 - y * v_g2)
    g2 = np.sqrt(np.maximum(2.0 * p1 * rho_m2**2 * term, 0.0))
    w = cda * g2
    return w, yc, critical
