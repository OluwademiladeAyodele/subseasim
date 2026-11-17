"""Lumped-parameter compressible hydraulic network (dynamic model core).

Discretisation
--------------
The physical system is reduced to PRESSURE NODES (control volumes that
store fluid) joined by FLOW LINKS (that carry fluid and dissipate pressure).
Every pipe is split into N segments; segment k contributes half its volume
to each of its two end nodes (vertex-centred finite volumes).

Node mass balance (liquid, linearised equation of state rho = rho0 (1 + c_f dP)):

    C_i dP_i/dt = sum(Q_in) - sum(Q_out) + S_i                       (1)

    C_i = sum_parts V_part (c_f + c_wall)          [m3/Pa]  hydraulic capacitance
    c_wall = D / (E e)  (thin-walled pipe, Korteweg)  or a configured value
    S_i  = V_i beta dT_i/dt                        [m3/s]   thermal expansion of
                                                            the stored fluid

Dividing the mass balance by rho0 turns mass flows into volumetric flows;
the relative density change over the operating range (c_f dP ~ 1e-2) is
neglected in the flux terms (documented limitation).

Link momentum balance (1-D, uniform flow in the link):

    I dQ/dt = P_up - P_dn - G - R(Q)                                  (2)

    I = rho L / A             inertance of the fluid in the link [kg/m4]
    G = rho g dz (+ cracking pressure for an open check valve)
    R(Q) = friction (Darcy-Weisbach / Churchill), orifice rho Q|Q|/(2 C^2),
           or linear (Darcy flow in the reservoir: Q / T)

Equations (1)-(2) are a lumped "LC-R" ladder: it propagates pressure
disturbances at the wave speed a = 1/sqrt(rho (c_f + c_wall)) (approximately,
for segments short compared with the disturbance) and it relaxes to the
steady operating point with time constants set by capacitance x resistance.
The two effects are therefore represented separately, not by a delay.

Time integration
----------------
Backward (implicit) Euler for (1) and (2) together: A-stable, so a fixed
step that is large compared with the acoustic transit time of a segment is
still stable (it then damps the waves rather than resolving them - a
documented limitation). R(Q) is linearised about the current iterate and
the step is solved by Newton iteration. Eliminating Q from (2) gives one
symmetric linear system in the node pressures per iteration.

Steady state (dt -> infinity) is the same system without storage and
inertia terms. Nodes in a volume isolated from every fixed-pressure node
keep their pressure (a tiny storage term regularises the system), which is
the physically correct behaviour of an isolated liquid volume with no
leakage.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

PIPE, ORIFICE, LINEAR, CHECK = 0, 1, 2, 3

#: Pressure scale below which the orifice law is regularised [Pa]. The
#: quadratic law Q ~ sqrt(dP) has an infinite derivative at dP = 0; the
#: regularised law is exact to <0.1 % above ~10 x this differential.
ORIFICE_REG_DP_PA = 100.0
#: Equivalent length / bore area used for the (small) inertance of a
#: valve or choke bore [m].
RESTRICTION_LENGTH_M = 0.5
#: Storage regularisation time for the steady-state solve [s].
STEADY_REG_TIME_S = 1.0e9
#: Newton convergence on link flow.
Q_ABS_TOL = 1e-11  # m3/s
Q_REL_TOL = 1e-8
MAX_NEWTON = 40


class DynamicSolverError(RuntimeError):
    pass


@dataclass
class Link:
    id: str
    up: int
    dn: int
    kind: int
    #: Element that this link belongs to (pipe id, valve id, "reservoir").
    element_id: str
    segment: int = 0
    inertance: float = 0.0  # kg/m4
    gravity_dp: float = 0.0  # Pa (rho g dz)
    # pipe
    length: float = 0.0
    diameter: float = 0.0  # hydraulic diameter
    area: float = 0.0
    roughness: float = 0.0
    rho: float = 1000.0
    mu: float = 1e-3
    # orifice / check
    restriction: object | None = None  # RestrictionElement (capacity read each step)
    capacity_open: float = 0.0  # check valve
    cracking_pressure: float = 0.0
    # linear
    conductance: float = 0.0  # m3/(s Pa)


@dataclass
class HNode:
    id: str
    name: str
    elevation: float
    zone: str
    volume: float = 0.0  # m3 (fluid volume, pore volume for reservoir cells)
    capacitance: float = 0.0  # m3/Pa
    beta: float = 0.0  # 1/K thermal expansion of the stored fluid
    fixed: bool = False
    p_fixed: float = 0.0
    #: Topology node id this hydraulic node represents (None = interior).
    topo: str | None = None
    #: (pipe id, position along pipe [m]) for interior / end nodes of pipes.
    pipe_positions: list[tuple[str, float]] = field(default_factory=list)
    initial_pressure: float | None = None


def churchill(re: np.ndarray, rel_rough: np.ndarray) -> np.ndarray:
    """Vectorised Churchill (1977) Darcy friction factor; ``re`` > 0."""
    a = (2.457 * np.log(1.0 / ((7.0 / re) ** 0.9 + 0.27 * rel_rough))) ** 16
    b = (37530.0 / re) ** 16
    return 8.0 * ((8.0 / re) ** 12 + (a + b) ** -1.5) ** (1.0 / 12.0)


class HydraulicNetwork:
    """Graph of pressure nodes and flow links with an implicit solver."""

    def __init__(self, nodes: list[HNode], links: list[Link]):
        self.nodes = nodes
        self.links = links
        self.index = {n.id: i for i, n in enumerate(nodes)}
        n, m = len(nodes), len(links)
        self.n, self.m = n, m
        self.up = np.array([l.up for l in links], dtype=int)
        self.dn = np.array([l.dn for l in links], dtype=int)
        self.kind = np.array([l.kind for l in links], dtype=int)
        self.inertance = np.array([l.inertance for l in links])
        self.gravity = np.array([l.gravity_dp for l in links])
        self.cap_node = np.array([nd.capacitance for nd in nodes])
        self.fixed = np.array([nd.fixed for nd in nodes], dtype=bool)
        self.p_fixed = np.array([nd.p_fixed for nd in nodes])
        self.beta_node = np.array([nd.beta for nd in nodes])
        self.vol_node = np.array([nd.volume for nd in nodes])

        self.pipe_idx = np.flatnonzero(self.kind == PIPE)
        self.orf_idx = np.flatnonzero(self.kind == ORIFICE)
        self.lin_idx = np.flatnonzero(self.kind == LINEAR)
        self.chk_idx = np.flatnonzero(self.kind == CHECK)
        pl = [links[i] for i in self.pipe_idx]
        self._pL = np.array([l.length for l in pl])
        self._pD = np.array([l.diameter for l in pl])
        self._pA = np.array([l.area for l in pl])
        self._pE = np.array([l.roughness for l in pl]) / np.maximum(self._pD, 1e-12)
        self._prho = np.array([l.rho for l in pl])
        self._pmu = np.array([l.mu for l in pl])
        #: Two-phase friction multiplier per pipe link (1 = single phase);
        #: set by the multiphase property update (Beggs & Brill exp(S) x rho_ref / rho_ns).
        self._pfric = np.ones(len(pl))
        self._orf_rho = np.array([links[i].rho for i in self.orf_idx])
        self._chk_rho = np.array([links[i].rho for i in self.chk_idx])
        self._chk_cap = np.array([links[i].capacity_open for i in self.chk_idx])
        self._chk_crack = np.array([links[i].cracking_pressure for i in self.chk_idx])
        self._lin_T = np.array([links[i].conductance for i in self.lin_idx])

        self.P = np.zeros(n)
        self.Q = np.zeros(m)
        #: Check-valve state (True = open).
        self.check_open = np.zeros(len(self.chk_idx), dtype=bool)
        self.capacity = np.zeros(m)  # current orifice/check capacity per link
        self.blocked = np.zeros(m, dtype=bool)
        self.last_iterations = 0
        self.last_converged = True
        self.last_residual = 0.0
        # flattened-index helpers for fast assembly
        self._uu = self.up * n + self.up
        self._dd = self.dn * n + self.dn
        self._ud = self.up * n + self.dn
        self._du = self.dn * n + self.up
        self.refresh_restrictions()

    # ----------------------------------------------------------- properties
    def refresh_restrictions(self) -> None:
        """Read the current capacity of every valve/choke from its element."""
        for k, li in enumerate(self.orf_idx):
            el = self.links[li].restriction
            c = el.capacity  # type: ignore[union-attr]
            leak = getattr(el, "seat_leak_capacity", 0.0)
            c_eff = max(c, leak)
            self.capacity[li] = c_eff
            self.blocked[li] = c_eff <= 0.0
        for k, li in enumerate(self.chk_idx):
            self.capacity[li] = self._chk_cap[k]
            self.blocked[li] = not self.check_open[k]

    # ----------------------------------------------------------- resistance
    def _pipe_dp(self, q: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Friction loss and its exact derivative dR/dQ.

        R = f(Re) (L/D) rho v|v| / 2  =>  dR/dQ = (R/Q) (2 + dln f / dln Re);
        dln f/dln Re from one extra Churchill evaluation (relative step 1e-4).
        Below Re = 1 the laminar limit R = 32 mu L v / D^2 is used directly."""
        v = q / self._pA
        re = self._prho * np.abs(v) * self._pD / self._pmu
        re_s = np.maximum(re, 1.0)
        f = churchill(re_s, self._pE)
        f2 = churchill(re_s * 1.0001, self._pE)
        slope = np.log(f2 / f) / math.log(1.0001)
        geom = (self._pL / self._pD) * self._prho * self._pfric / 2.0
        turb = f * geom * v * np.abs(v)
        dturb = f * geom * 2.0 * np.abs(v) * (1.0 + slope / 2.0) / self._pA
        lam_k = 32.0 * self._pmu * self._pL / (self._pD**2 * self._pA)
        lam = re < 1.0
        return np.where(lam, lam_k * q, turb), np.where(lam, lam_k, dturb)

    def resistance(self, q: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """R(Q) [Pa] and dR/dQ [Pa s/m3] for every link."""
        r = np.zeros(self.m)
        dr = np.zeros(self.m)
        if self.pipe_idx.size:
            r[self.pipe_idx], dr[self.pipe_idx] = self._pipe_dp(q[self.pipe_idx])
        for idx, rho in ((self.orf_idx, self._orf_rho), (self.chk_idx, self._chk_rho)):
            if not idx.size:
                continue
            open_ = self.capacity[idx] > 0.0
            c = np.where(open_, self.capacity[idx], 1.0)
            qe = c * math.sqrt(2.0 * ORIFICE_REG_DP_PA) / np.sqrt(rho)
            k = rho / (2.0 * c * c)
            qq = np.where(open_, q[idx], 0.0)
            s = np.sqrt(qq * qq + qe * qe)
            r[idx] = np.where(open_, k * qq * s, 0.0)
            dr[idx] = np.where(open_, k * (2.0 * qq * qq + qe * qe) / s, 0.0)
        if self.lin_idx.size:
            r[self.lin_idx] = q[self.lin_idx] / self._lin_T
            dr[self.lin_idx] = 1.0 / self._lin_T
        return r, dr

    def link_inertance(self) -> np.ndarray:
        return self.inertance

    # ---------------------------------------------------------------- solve
    def _assemble_solve(self, storage: np.ndarray, rhs0: np.ndarray, b: np.ndarray, a: np.ndarray) -> np.ndarray:
        n = self.n
        A = np.bincount(self._uu, b, n * n) + np.bincount(self._dd, b, n * n) - np.bincount(self._ud, b, n * n) - np.bincount(self._du, b, n * n)
        A = A.reshape(n, n)
        A[np.diag_indices(n)] += storage
        rhs = rhs0 - np.bincount(self.up, b * a, n) + np.bincount(self.dn, b * a, n)
        fx = self.fixed
        A[fx, :] = 0.0
        A[fx, fx] = 1.0
        rhs[fx] = self.p_fixed[fx]
        return np.linalg.solve(A, rhs)

    def solve(self, dt: float | None, source: np.ndarray | None = None) -> None:
        """Advance by ``dt`` [s] (implicit Euler) or, with ``dt=None``,
        solve for the steady state. Updates ``self.P`` and ``self.Q``."""
        p_old = self.P.copy()
        q_old = self.Q.copy()
        src = np.zeros(self.n) if source is None else source
        if dt is None:
            storage = self.cap_node / STEADY_REG_TIME_S
            inert = np.zeros(self.m)
        else:
            storage = self.cap_node / dt
            inert = self.inertance / dt
        rhs0 = storage * p_old + src
        self.refresh_restrictions()

        # check-valve state at the start of the step: open if forward flow
        # or if the differential exceeds the cracking pressure
        if self.chk_idx.size:
            dp = p_old[self.up[self.chk_idx]] - p_old[self.dn[self.chk_idx]] - self.gravity[self.chk_idx]
            self.check_open = (q_old[self.chk_idx] > 0.0) | (dp > self._chk_crack)
            self.blocked[self.chk_idx] = ~self.check_open

        q = q_old.copy()
        q[self.blocked] = 0.0
        converged = False
        iters = 0
        toggles = 0
        p = p_old
        for iters in range(1, MAX_NEWTON + 1):
            r, dr = self.resistance(q)
            g = inert + dr
            grav = self.gravity.copy()
            if self.chk_idx.size:
                grav[self.chk_idx] += self._chk_crack
            with np.errstate(divide="ignore"):
                b = np.where(self.blocked | (g <= 0.0), 0.0, 1.0 / np.where(g > 0, g, 1.0))
            a = inert * q_old - grav - r + dr * q
            p = self._assemble_solve(storage, rhs0, b, a)
            q_new = b * (p[self.up] - p[self.dn] + a)
            if not np.all(np.isfinite(q_new)) or not np.all(np.isfinite(p)):
                raise DynamicSolverError("non-finite pressure or flow in dynamic hydraulic solution")
            # check-valve active set
            changed = False
            if self.chk_idx.size and toggles < 4:
                qc = q_new[self.chk_idx]
                dpc = p[self.up[self.chk_idx]] - p[self.dn[self.chk_idx]] - self.gravity[self.chk_idx]
                close = self.check_open & (qc < 0.0)
                opn = ~self.check_open & (dpc > self._chk_crack)
                if close.any() or opn.any():
                    self.check_open = (self.check_open & ~close) | opn
                    self.blocked[self.chk_idx] = ~self.check_open
                    q_new[self.blocked] = 0.0
                    changed = True
                    toggles += 1
            dq = np.abs(q_new - q)
            q = q_new
            if not changed and np.all(dq <= Q_ABS_TOL + Q_REL_TOL * np.abs(q)):
                converged = True
                break
        self.P = p
        self.Q = q
        self.last_iterations = iters
        self.last_converged = converged
        r, _ = self.resistance(q)
        resid = (p[self.up] - p[self.dn] - self.gravity - r) - (inert * (q - q_old))
        if self.chk_idx.size:
            resid[self.chk_idx] -= np.where(self.check_open, self._chk_crack, 0.0)
        resid[self.blocked] = 0.0
        self.last_residual = float(np.max(np.abs(resid))) if resid.size else 0.0

    # ------------------------------------------------------------- analysis
    def components(self) -> list[set[int]]:
        """Connected components through links that are not blocked."""
        parent = list(range(self.n))

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for li in range(self.m):
            if not self.blocked[li]:
                a, b = find(int(self.up[li])), find(int(self.dn[li]))
                if a != b:
                    parent[a] = b
        groups: dict[int, set[int]] = {}
        for i in range(self.n):
            groups.setdefault(find(i), set()).add(i)
        return list(groups.values())
