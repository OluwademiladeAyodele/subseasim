"""Steady-state three-phase solution of the production path (marching).

Unknown: the production MASS flow W [kg/s] (identical in every element at
steady state - component mass conservation is exact by construction). The
stream composition (GOR, WC) is constant along the path; phase split, phase
volumes and properties follow from the black-oil model at local (p, T).

For a candidate W the path is marched from the reservoir:

    inflow     p_wf from the IPR: linear (reference-volume PI) above the
               bubble point, Vogel (1968) composite below it
    pipe       Beggs & Brill (or no-slip) gradient, Heun predictor-corrector
               over segments of <= SEGMENT_M, with the acceleration term
               E_k = rho_s v_m v_sg / p
    valve /    Sachdeva choke model with C_dA = element capacity (the
    choke      configured Cv / loss-coefficient characteristic); a flow
               above the critical (choked) flow is infeasible

and the arrival pressure is compared with the boundary pressure. The
residual is monotone in W. To keep the solve fast the march is vectorised
over a batch of candidate flows: the bracket shrinks by ~1/(N-1) per batch
and the last batch is refined by linear interpolation.

Temperatures are supplied by the caller (thermal model); the solver is
isothermal within a segment (temperature interpolated linearly along each
pipe between its end nodes).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from app.simulation.components.elements import InflowElement, PipeElement, RestrictionElement
from app.simulation.fluid_properties.black_oil import BlackOilFluid
from app.simulation.multiphase.correlations import PATTERN_NAMES, beggs_brill, sachdeva_critical_ratio
from app.simulation.topology.topology import SeriesTopology

SEGMENT_M = 150.0
MAX_SEGMENTS = 12
BATCH = 17
P_MIN = 1.0e5  # Pa: below this a candidate is infeasible (flow too high)


@dataclass
class MultiphaseProfilePoint:
    node: str
    element: str | None
    distance_m: float
    p: float
    t: float
    pattern: str
    holdup: float
    lambda_l: float
    gvf: float
    v_sl: float
    v_sg: float
    rho_s: float
    rho_ns: float


@dataclass
class MultiphaseSteadyResult:
    ok: bool
    w: float  # kg/s
    q_ref: float  # reference volume flow W / rho_ref [m3/s]
    node_pressure: dict[str, float | None]
    element_dp: dict[str, float | None]
    message: str = ""
    critical_choke: bool = False
    profile: list[MultiphaseProfilePoint] = field(default_factory=list)
    iterations: int = 0


class _Infeasible(Exception):
    pass


def _ipr_pwf(w, rho_ref, p_res, j, pb_res):
    """Flowing bottomhole pressure for mass flow arrays (reference-volume PI)."""
    q = w / rho_ref
    pwf_lin = p_res - q / j
    if p_res <= pb_res:  # saturated reservoir: Vogel only
        qmax = j * p_res / 1.8
        r = np.clip(1 - q / qmax, -1, 1)
        # q/qmax = 1 - 0.2 x - 0.8 x^2  => x = (-0.2 + sqrt(0.04 + 3.2 r)) / 1.6
        disc = 0.04 + 3.2 * r
        x = np.where(disc >= 0, (-0.2 + np.sqrt(np.maximum(disc, 0))) / 1.6, -1.0)
        return np.where(q <= 0, pwf_lin, x * p_res)
    qb = j * (p_res - pb_res)
    above = q <= qb
    qv = j * pb_res / 1.8
    r = 1 - (q - qb) / qv
    disc = 0.04 + 3.2 * r
    x = np.where(disc >= 0, (-0.2 + np.sqrt(np.maximum(disc, 0))) / 1.6, -1.0)
    return np.where(above, pwf_lin, x * pb_res)


def _phase_velocities(fluid: BlackOilFluid, w, p, t, gor, wc, area):
    s = fluid.state(p, t, gor, wc)
    q_liq_sc = w / fluid.mass_per_liquid_sc(gor, wc)
    v_sl = q_liq_sc * s.vol_l / area
    v_sg = q_liq_sc * s.vol_g / area
    return s, v_sl, v_sg


def _pipe_gradient(fluid, w, p, t, gor, wc, e: PipeElement, theta, correlation):
    g = e.geometry
    s, v_sl, v_sg = _phase_velocities(fluid, np.abs(w), p, t, gor, wc, g.area)
    bb = beggs_brill(v_sl, v_sg, s.rho_l, s.rho_g, s.mu_l, s.mu_g, s.sigma_gl, g.diameter, theta, g.roughness, correlation)
    grad = bb["grad_gravity"] + np.sign(w) * bb["grad_friction"]
    ek = np.clip(bb["rho_s"] * bb["v_m"] * v_sg / p, 0.0, 0.9)
    return grad / (1.0 - ek), s, bb, v_sl, v_sg


def _restriction_p2(fluid, w, p1, t, gor, wc, cda, k):
    """Downstream pressure for mass flow w through C_dA (Sachdeva)."""
    q = fluid.params
    s = fluid.state(p1, t, gor, wc)
    x1 = s.free_gas_mass_fraction
    rho_l = s.rho_l
    v_g1 = 1.0 / np.maximum(s.rho_g, 1e-6)
    cv = q.cp_gas_j_kgk / k
    c_l = (s.mass_o * q.cp_oil_j_kgk + s.mass_w * q.cp_water_j_kgk) / np.maximum(s.mass_o + s.mass_w, 1e-12)
    n = 1.0 + x1 * (q.cp_gas_j_kgk - cv) / np.maximum(x1 * cv + (1 - x1) * c_l, 1e-9)
    has_gas = x1 > 1e-7
    yc = np.where(has_gas, sachdeva_critical_ratio(np.where(has_gas, x1, 0.5), rho_l, v_g1, k, n), 0.0)
    kk = k / (k - 1.0)
    v_l = 1.0 / rho_l

    def flux(y):
        v_g2 = v_g1 * np.maximum(y, 1e-6) ** (-1.0 / k)
        rho_m2 = 1.0 / (x1 * v_g2 + (1 - x1) * v_l)
        term = (1 - x1) * (1 - y) * v_l + x1 * kk * (v_g1 - y * v_g2)
        return cda * np.sqrt(np.maximum(2.0 * p1 * rho_m2**2 * term, 0.0))

    aw = np.abs(w)
    w_crit = flux(np.maximum(yc, 1e-6))
    feasible = aw <= w_crit * (1 + 1e-12)
    # bisection on y in [yc, 1] (flux decreasing in y)
    lo = np.maximum(yc, 1e-6)
    hi = np.ones_like(lo)
    for _ in range(48):
        mid = 0.5 * (lo + hi)
        too_much = flux(mid) > aw
        lo = np.where(too_much, mid, lo)
        hi = np.where(too_much, hi, mid)
    y = 0.5 * (lo + hi)
    # liquid-only: exact orifice equation
    y = np.where(has_gas, y, 1.0 - aw**2 / (2.0 * rho_l * cda**2 * p1))
    p2 = np.where(w >= 0, y * p1, p1 + (p1 - y * p1))
    return np.where(feasible, p2, -np.inf), bool(np.any(has_gas & (aw >= 0.999 * w_crit)))


def march(topology: SeriesTopology, fluid: BlackOilFluid, w, p_res: float, j_ref: float, rho_ref: float,
          node_t: dict[str, float], gor: float, wc: float, correlation: str = "beggs_brill", k_gas: float | None = None,
          collect: bool = False):
    """March the path for an array of mass flows; returns (p_nodes [n_nodes x n_w], dps, profile)."""
    w = np.atleast_1d(np.asarray(w, float))
    k = k_gas or fluid.params.gas_cp_cv
    path, nodes = topology.path, topology.node_order
    pb_res = float(fluid.state(p_res, node_t[nodes[0]], gor, wc).pb[0])
    P = np.empty((len(nodes), w.size))
    P[0] = p_res
    profile: list[MultiphaseProfilePoint] = []
    p = np.full(w.size, p_res)
    crit = False
    dist = 0.0
    for i, e in enumerate(path):
        t_in, t_out = node_t[nodes[i]], node_t[nodes[i + 1]]
        if isinstance(e, InflowElement):
            p = _ipr_pwf(w, rho_ref, p_res, j_ref, pb_res)
        elif isinstance(e, PipeElement):
            g = e.geometry
            n = max(1, min(MAX_SEGMENTS, math.ceil(g.length / SEGMENT_M)))
            dl = g.length / n
            theta = math.asin(max(-1.0, min(1.0, g.dz / g.length))) if g.length > 0 else 0.0
            for sgm in range(n):
                ta = t_in + (t_out - t_in) * sgm / n
                tb = t_in + (t_out - t_in) * (sgm + 1) / n
                pa = np.where(np.isfinite(p) & (p > P_MIN), p, P_MIN)
                g1, s1, bb1, vsl1, vsg1 = _pipe_gradient(fluid, w, pa, ta, gor, wc, e, theta, correlation)
                pp = pa - g1 * dl
                pp_ok = np.where(pp > P_MIN, pp, P_MIN)
                g2, *_ = _pipe_gradient(fluid, w, pp_ok, tb, gor, wc, e, theta, correlation)
                p_new = pa - 0.5 * (g1 + g2) * dl
                p = np.where(np.isfinite(p) & (p > P_MIN) & (p_new > P_MIN), p_new, -np.inf)
                if collect:
                    profile.append(MultiphaseProfilePoint(
                        node=nodes[i] if sgm == 0 else f"{e.id}@{sgm * dl:.0f}m", element=e.id, distance_m=dist + sgm * dl,
                        p=float(pa[0]), t=float(ta), pattern=PATTERN_NAMES[int(bb1["pattern"][0])], holdup=float(bb1["holdup"][0]),
                        lambda_l=float(bb1["lambda_l"][0]), gvf=float(s1.gvf[0]), v_sl=float(vsl1[0]), v_sg=float(vsg1[0]),
                        rho_s=float(bb1["rho_s"][0]), rho_ns=float(bb1["rho_ns"][0])))
            dist += g.length
        elif isinstance(e, RestrictionElement):
            cda = e.capacity
            if cda <= 0:
                raise ValueError("closed element in an open-path march")
            pa = np.where(np.isfinite(p) & (p > P_MIN), p, P_MIN)
            p2, c = _restriction_p2(fluid, w, pa, t_in, gor, wc, cda, k)
            crit = crit or c
            p = np.where(np.isfinite(p) & (p > P_MIN) & (p2 > P_MIN), p2, -np.inf)
        else:
            raise ValueError(f"element {e.id}: {e.kind} is not supported on the production path")
        P[i + 1] = p
    return P, crit, profile


def _march_back(topology, fluid, w: float, p_out: float, start: int, node_t, gor, wc, correlation, k):
    """Backward march (outlet -> inlet) over path elements start.. end for a
    choked operating point: pressures downstream of the critical choke are
    set by the downstream line and the boundary, not by the choke."""
    path, nodes = topology.path, topology.node_order
    P = {nodes[-1]: p_out}
    p = np.array([p_out])
    wa = np.array([w])
    for i in range(len(path) - 1, start - 1, -1):
        e = path[i]
        t_in, t_out = node_t[nodes[i]], node_t[nodes[i + 1]]
        if isinstance(e, PipeElement):
            g = e.geometry
            n = max(1, min(MAX_SEGMENTS, math.ceil(g.length / SEGMENT_M)))
            dl = g.length / n
            theta = math.asin(max(-1.0, min(1.0, g.dz / g.length))) if g.length > 0 else 0.0
            for sgm in range(n, 0, -1):
                tb = t_in + (t_out - t_in) * sgm / n
                ta = t_in + (t_out - t_in) * (sgm - 1) / n
                g1, *_ = _pipe_gradient(fluid, wa, p, tb, gor, wc, e, theta, correlation)
                pp = p + g1 * dl
                g2, *_ = _pipe_gradient(fluid, wa, pp, ta, gor, wc, e, theta, correlation)
                p = p + 0.5 * (g1 + g2) * dl
        elif isinstance(e, RestrictionElement):
            # find p1 with p2(p1) = p (bisection; p2 increases with p1)
            lo, hi = float(p[0]), float(p[0]) * 4 + 1e6
            for _ in range(50):
                mid = 0.5 * (lo + hi)
                p2, _ = _restriction_p2(fluid, wa, np.array([mid]), t_in, gor, wc, e.capacity, k)
                if np.isfinite(p2[0]) and p2[0] >= p[0]:
                    hi = mid
                else:
                    lo = mid
            p = np.array([hi])
        P[nodes[i]] = float(p[0])
    return P


def solve_steady(topology: SeriesTopology, fluid: BlackOilFluid, p_res: float, p_boundary: float, j_ref: float, rho_ref: float,
                 node_t: dict[str, float], gor: float, wc: float, correlation: str = "beggs_brill",
                 tol_pa: float = 50.0) -> MultiphaseSteadyResult:
    path, nodes = topology.path, topology.node_order
    k_gas = fluid.params.gas_cp_cv
    if any(e.is_closed() for e in path):
        return MultiphaseSteadyResult(False, 0.0, 0.0, {n: None for n in nodes}, {e.id: None for e in path}, "path closed")
    pb_res = float(fluid.state(p_res, node_t[nodes[0]], gor, wc).pb[0])
    q_aof = j_ref * (max(p_res - pb_res, 0.0) + min(p_res, pb_res) / 1.8)
    lo, hi = 0.0, q_aof * rho_ref
    P0, _, _ = march(topology, fluid, np.array([0.0]), p_res, j_ref, rho_ref, node_t, gor, wc, correlation)
    if not P0[-1, 0] > p_boundary:
        return MultiphaseSteadyResult(False, 0.0, 0.0, {n: None for n in nodes}, {e.id: None for e in path},
                                      "no forward flow: static arrival pressure below the boundary (reverse flow not supported in the multiphase model)")
    r_lo, r_hi = float(P0[-1, 0] - p_boundary), -1e12
    iters = 0
    for _ in range(6):
        ws = np.linspace(lo, hi, BATCH)
        P, _, _ = march(topology, fluid, ws, p_res, j_ref, rho_ref, node_t, gor, wc, correlation)
        ok = np.isfinite(P[-1]) & (P[-1] > P_MIN)
        r = np.where(ok, P[-1] - p_boundary, -1e12)
        r[0] = r_lo if ws[0] == lo else r[0]
        iters += 1
        idx = np.flatnonzero(r <= 0)
        if not idx.size:
            return MultiphaseSteadyResult(False, 0.0, 0.0, {n: None for n in nodes}, {e.id: None for e in path},
                                          "operating point above the reservoir absolute open flow")
        k = max(int(idx[0]), 1)
        lo, hi, r_lo, r_hi = ws[k - 1], ws[k], r[k - 1], r[k]
        normal = r_hi > -1e11
        if (normal and abs(r_lo - r_hi) < 4 * tol_pa) or (hi - lo) < 1e-5 * max(hi, 1e-9):
            break
    choked = not (r_hi > -1e11)
    w_star = lo + (hi - lo) * r_lo / (r_lo - r_hi) if not choked else lo
    P, crit, prof = march(topology, fluid, np.array([w_star]), p_res, j_ref, rho_ref, node_t, gor, wc, correlation, collect=True)
    pres = {n: float(P[i, 0]) for i, n in enumerate(nodes)}
    msg = f"converged (arrival residual {pres[nodes[-1]] - p_boundary:.0f} Pa)"
    if choked:
        # downstream of the critical restriction: march back from the boundary
        ci = max(i for i, e in enumerate(path) if isinstance(e, RestrictionElement) and e.capacity > 0
                 and i < len(path) and _is_critical(fluid, w_star, pres[nodes[i]], node_t[nodes[i]], gor, wc, e.capacity, k_gas))
        back = _march_back(topology, fluid, w_star, p_boundary, ci + 1, node_t, gor, wc, correlation, k_gas)
        pres.update(back)
        msg = f"critical (choked) flow through {path[ci].id}: rate set by upstream conditions"
        crit = True
    pres[nodes[-1]] = p_boundary
    dps = {e.id: pres[nodes[i]] - pres[nodes[i + 1]] for i, e in enumerate(path)}
    return MultiphaseSteadyResult(True, float(w_star), float(w_star / rho_ref), pres, dps, msg, crit, prof, iters)


def _is_critical(fluid, w, p1, t, gor, wc, cda, k) -> bool:
    p2, _ = _restriction_p2(fluid, np.array([w * 1.0005]), np.array([p1]), t, gor, wc, cda, k)
    return not np.isfinite(p2[0])
