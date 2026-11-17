"""Coupling of the black-oil / multiphase model to the dynamic network.

Formulation (mass based, see docs/MULTIPHASE_FLOW_MODEL.md section 5)
--------------------------------------------------------------------
The network keeps its (P, Q) structure. In multiphase mode the production
"volumetric" flow is a REFERENCE flow Q = W / rho_ref, with W the mass flow
and rho_ref the mixture density at reservoir conditions (so reservoir-side
flows are true reservoir volumes). With that substitution the node mass
balance d(V rho_m)/dt = sum(W) becomes

    (V / rho_ref) (d rho_m / dP) dP/dt = sum(Q) - (V / rho_ref)(d rho_m/dT) dT/dt

i.e. the existing equation (1) with a pressure-dependent capacitance
C = V (d rho_m/dP) / rho_ref (+ wall compliance) - gas compressibility and
gas liberation / re-solution are both inside d rho_m / dP. The link momentum
balance (L/A) dW/dt = dP - rho_s g dz - dP_f becomes equation (2) with

    gravity     rho_s g dz          (slip density, Beggs & Brill holdup)
    friction    f_tp rho_ns v_m^2 / 2 (L/D), v_m = W / (rho_ns A)
                -> network pipe law with rho = rho_ref, mu = mu_ns and the
                   multiplier exp(S) rho_ref / rho_ns
    valves /    W from the Sachdeva choke model at the current upstream and
    choke       downstream pressures, expressed as the equivalent orifice
                density rho_eff = 2 (C_dA)^2 dP / Q_s^2 (choking included);
                liquid-only reduces to rho_ref^2 / rho_l exactly

Properties are evaluated from the state at the START of each step (lagged,
explicit in the coefficients, implicit in P and Q) - a standard semi-
implicit treatment; the steady state is unaffected by the lag.

Phase behaviour is quasi-steady (instantaneous local equilibrium, no phase
slip dynamics, no slugging, no terrain-induced transients). The produced
stream composition (stock-tank oil, surface gas, water mass fractions) is
transported along the production path, so a change of GOR or water cut at
the reservoir reaches the tree and the manifold with the fluid transit time
and every component's mass balance can be closed.
"""

from __future__ import annotations

import math

import numpy as np

from app.simulation.dynamic.builder import PRODUCTION
from app.simulation.dynamic.network import CHECK, ORIFICE, PIPE
from app.simulation.dynamic.transport import TransportGrid
from app.simulation.fluid_properties.black_oil import BlackOilFluid
from app.simulation.multiphase.correlations import PATTERN_NAMES, beggs_brill, sachdeva_critical_ratio

G = 9.80665
#: Below this mixture velocity the link is treated as static (no-slip density,
#: no two-phase friction multiplier): Beggs & Brill holdup is undefined at v -> 0.
V_STATIC = 1e-3
#: Under-relaxation of the equivalent orifice density between steps.
ORIFICE_RELAX = 0.5
#: Property re-evaluation thresholds (see MultiphaseCoupling.update).
UPDATE_DP_PA = 2.0e3
UPDATE_DQ_REL = 1.0e-3
UPDATE_MAX_SKIP = 30


class MultiphaseCoupling:
    def __init__(self, dyn, fluid: BlackOilFluid, rho_ref: float, gor: float, wc: float, correlation: str,
                 cells_per_segment: dict[str, int], node_volumes: dict[str, float]):
        self.dyn = dyn
        self.fluid = fluid
        self.rho_ref = rho_ref
        self.correlation = correlation
        self.gor_res, self.wc_res = gor, wc
        net = dyn.net
        self.net = net
        zone_rho = dyn.layout.zones[PRODUCTION].rho
        cf = dyn.layout.zones[PRODUCTION].c_f
        self.prod = np.array([i for i, nd in enumerate(net.nodes) if nd.zone == PRODUCTION], dtype=int)
        self.pos = {int(i): k for k, i in enumerate(self.prod)}
        self.free = np.array([not net.fixed[i] for i in self.prod])
        self.cap_wall = np.maximum(net.cap_node[self.prod] - net.vol_node[self.prod] * cf, 0.0)
        self.vol = net.vol_node[self.prod].copy()
        prod_set = set(self.prod.tolist())
        # production pipe links
        pk, pl = [], []
        for k, li in enumerate(net.pipe_idx):
            if net.up[li] in prod_set and net.dn[li] in prod_set:
                pk.append(k), pl.append(li)
        self.p_k, self.p_li = np.array(pk, dtype=int), np.array(pl, dtype=int)
        links = net.links
        self.p_L = np.array([links[i].length for i in pl]) if pl else np.zeros(0)
        self.p_D = net._pD[self.p_k] if pk else np.zeros(0)
        self.p_A = net._pA[self.p_k] if pk else np.zeros(0)
        self.p_rough = np.array([links[i].roughness for i in pl]) if pl else np.zeros(0)
        self.p_dz = net.gravity[self.p_li] / (zone_rho * G) if pk else np.zeros(0)
        # production restrictions (orifice) and check valves
        ok, ol = [], []
        for k, li in enumerate(net.orf_idx):
            if net.up[li] in prod_set and net.dn[li] in prod_set:
                ok.append(k), ol.append(li)
        self.o_k, self.o_li = np.array(ok, dtype=int), np.array(ol, dtype=int)
        self.o_dz = net.gravity[self.o_li] / (zone_rho * G) if ok else np.zeros(0)
        ck, cl = [], []
        for k, li in enumerate(net.chk_idx):
            if net.up[li] in prod_set and net.dn[li] in prod_set:
                ck.append(k), cl.append(li)
        self.c_k, self.c_li = np.array(ck, dtype=int), np.array(cl, dtype=int)
        self.c_dz = net.gravity[self.c_li] / (zone_rho * G) if ck else np.zeros(0)
        # composition transport (stock-tank oil, surface gas, water mass fractions)
        g = dyn.grid
        self.comp = TransportGrid(dyn.layout, dyn.topology, 3, cells_per_segment, node_volumes)
        self.comp.mass_tracking = True
        x = np.array(fluid.component_mass_fractions(gor, wc))
        self.comp.c[:] = x[:, None]
        self.comp.c_left = x.copy()
        self.comp.c_right = x.copy()
        g.mass_tracking = True
        self.inventory0: np.ndarray | None = None
        # caches for reporting
        self.node_state = None
        self.node_rho = np.full(self.prod.size, rho_ref)
        self.node_cp = None
        self.pipe_bb: dict | None = None
        self.orf_crit = np.zeros(self.o_k.size, dtype=bool)
        self.link_props: dict[int, tuple[float, float, float]] = {}
        self._last_P: np.ndarray | None = None
        self._last_Q: np.ndarray | None = None
        self._skipped = 0

    # ----------------------------------------------------------- composition
    def set_reservoir_composition(self, gor: float, wc: float) -> None:
        self._last_P = None  # force a property update
        self.gor_res, self.wc_res = gor, wc
        x = np.array(self.fluid.component_mass_fractions(gor, wc))
        self.comp.c_left = x.copy()

    def node_composition(self) -> tuple[np.ndarray, np.ndarray]:
        """(GOR, WC) at every production hydraulic node."""
        gor = np.full(self.prod.size, self.gor_res)
        wc = np.full(self.prod.size, self.wc_res)
        ids, W = self.comp._hn_ids, self.comp._hn_W
        xs = W @ self.comp.c.T  # [n_hnodes_in_grid x 3]
        g, w = self.fluid.composition_from_mass_fractions(xs[:, 0], xs[:, 1], xs[:, 2])
        for j, hid in enumerate(ids):
            k = self.pos.get(int(hid))
            if k is not None:
                gor[k], wc[k] = g[j], w[j]
        return gor, wc

    # -------------------------------------------------------------- update
    def update(self, force: bool = False) -> None:
        """Re-evaluate the property coefficients. Skipped while the state is
        quiet (pressures within UPDATE_DP_PA, flows within UPDATE_DQ_REL and
        fewer than UPDATE_MAX_SKIP steps since the last evaluation): the
        coefficients depend only on P, T, Q and composition, so a quiet state
        leaves them unchanged to well within the correlation uncertainty."""
        net = self.net
        if not force and self._last_P is not None and self._skipped < UPDATE_MAX_SKIP:
            qs = max(float(np.max(np.abs(net.Q))), 1e-9)
            if (float(np.max(np.abs(net.P[self.prod] - self._last_P))) < UPDATE_DP_PA
                    and float(np.max(np.abs(net.Q - self._last_Q))) < UPDATE_DQ_REL * qs):
                self._skipped += 1
                return
        self._skipped = 0
        self._last_P = net.P[self.prod].copy()
        self._last_Q = net.Q.copy()
        self._update()

    def _update(self) -> None:
        net, f, rr = self.net, self.fluid, self.rho_ref
        P = net.P[self.prod]
        T = self.dyn.T_node[self.prod]
        gor, wc = self.node_composition()
        s, rho, drdp, drdt, cp = f.mixture(P, T, gor, wc)
        self.node_state, self.node_rho, self.node_cp = s, rho, cp
        self.node_beta = -drdt / rho
        self._drdp = drdp
        drdp = np.maximum(drdp, rho * 2e-11)
        fr = self.prod[self.free]
        net.cap_node[fr] = (self.vol * drdp / rr + self.cap_wall * rho / rr)[self.free]
        net.beta_node[self.prod] = -drdt / rr
        self._update_pipes(gor, wc)
        self._update_restrictions(rho, s, cp)

    def _update_pipes(self, gor, wc) -> None:
        if not self.p_k.size:
            return
        net, f, rr = self.net, self.fluid, self.rho_ref
        li = self.p_li
        q = net.Q[li]
        up = np.where(q >= 0, net.up[li], net.dn[li])
        iu = np.array([self.pos[int(i)] for i in up])
        pm = 0.5 * (net.P[net.up[li]] + net.P[net.dn[li]])
        tm = 0.5 * (self.dyn.T_node[net.up[li]] + self.dyn.T_node[net.dn[li]])
        g_, w_ = gor[iu], wc[iu]
        s = f.state(pm, tm, g_, w_)
        w = rr * np.abs(q)
        q_liq = w / f.mass_per_liquid_sc(g_, w_)
        v_sl = q_liq * s.vol_l / self.p_A
        v_sg = q_liq * s.vol_g / self.p_A
        theta = np.arcsin(np.clip(self.p_dz / np.maximum(self.p_L, 1e-9), -1, 1)) * np.where(q >= 0, 1.0, -1.0)
        bb = beggs_brill(v_sl, v_sg, s.rho_l, s.rho_g, s.mu_l, s.mu_g, s.sigma_gl, self.p_D, theta, self.p_rough, self.correlation)
        static = bb["v_m"] < V_STATIC
        rho_s = np.where(static, s.rho_ns, bb["rho_s"])
        es = np.where(static, 1.0, bb["friction_multiplier"])
        net._prho[self.p_k] = rr
        net._pmu[self.p_k] = bb["mu_ns"]
        net._pfric[self.p_k] = es * rr / s.rho_ns
        net.gravity[li] = rho_s * G * self.p_dz
        self.pipe_bb = {"li": li, "holdup": np.where(static, 1.0 - s.gvf, bb["holdup"]), "pattern": np.where(static, -1, bb["pattern"]),
                        "lambda_l": 1.0 - s.gvf, "v_sl": v_sl, "v_sg": v_sg, "rho_s": rho_s, "rho_ns": s.rho_ns,
                        "multiplier": es, "p": pm, "t": tm, "gor": g_, "wc": w_}

    def _update_restrictions(self, rho_node, s_node, cp_node) -> None:
        net, f, rr = self.net, self.fluid, self.rho_ref
        q_par = f.params
        k_gas = q_par.gas_cp_cv
        self.link_props = {}
        for kind_k, kind_li, dz, rho_arr in ((self.o_k, self.o_li, self.o_dz, net._orf_rho), (self.c_k, self.c_li, self.c_dz, net._chk_rho)):
            if not kind_k.size:
                continue
            q = net.Q[kind_li]
            fwd = q >= 0
            iu = np.array([self.pos[int(i)] for i in np.where(fwd, net.up[kind_li], net.dn[kind_li])])
            p1 = np.where(fwd, net.P[net.up[kind_li]], net.P[net.dn[kind_li]])
            p2 = np.where(fwd, net.P[net.dn[kind_li]], net.P[net.up[kind_li]])
            rho_up = rho_node[iu]
            homog = rr * rr / rho_up
            target = homog.copy()
            x1 = s_node.free_gas_mass_fraction[iu]
            crit = np.zeros(kind_k.size, dtype=bool)
            if kind_li is self.o_li:
                cda = np.array([max(net.links[i].restriction.capacity, getattr(net.links[i].restriction, "seat_leak_capacity", 0.0))
                                for i in kind_li])
                dp = p1 - p2
                gas = (x1 > 1e-7) & (cda > 0) & (dp > 5e3)
                if gas.any():
                    rho_l = s_node.rho_l[iu][gas]
                    v_g1 = 1.0 / np.maximum(s_node.rho_g[iu][gas], 1e-6)
                    cv = q_par.cp_gas_j_kgk / k_gas
                    c_l = (s_node.mass_o * q_par.cp_oil_j_kgk + s_node.mass_w * q_par.cp_water_j_kgk)[iu][gas] / np.maximum(
                        (s_node.mass_o + s_node.mass_w)[iu][gas], 1e-12)
                    xg = x1[gas]
                    n = 1.0 + xg * (q_par.cp_gas_j_kgk - cv) / np.maximum(xg * cv + (1 - xg) * c_l, 1e-9)
                    yc = sachdeva_critical_ratio(xg, rho_l, v_g1, k_gas, n)
                    y = np.maximum(p2[gas] / p1[gas], yc)
                    kk = k_gas / (k_gas - 1)
                    v_g2 = v_g1 * y ** (-1 / k_gas)
                    rho_m2 = 1.0 / (xg * v_g2 + (1 - xg) / rho_l)
                    term = (1 - xg) * (1 - y) / rho_l + xg * kk * (v_g1 - y * v_g2)
                    w_s = cda[gas] * np.sqrt(np.maximum(2.0 * p1[gas] * rho_m2**2 * term, 0.0))
                    q_s = w_s / rr
                    ok = q_s > 1e-12
                    t_ = np.where(ok, 2.0 * cda[gas] ** 2 * dp[gas] / np.maximum(q_s, 1e-12) ** 2, homog[gas])
                    target[gas] = t_
                    crit[gas] = p2[gas] / p1[gas] < yc
                self.orf_crit = crit
            rho_arr[kind_k] = ORIFICE_RELAX * rho_arr[kind_k] + (1 - ORIFICE_RELAX) * target
            net.gravity[kind_li] = rho_up * G * dz
            # throttling-temperature properties of the upstream mixture: dT = (1 - beta T) dP / (rho cp)
            for j, li in enumerate(kind_li):
                k = iu[j]
                self.link_props[int(li)] = (float(rho_node[k]), float(cp_node[k]), float(self.node_beta[k]))

    # ----------------------------------------------------------- readings
    def in_situ_flow(self, inst, q_ref: float) -> float:
        """Flow transmitters on the production path read the in-situ total
        volumetric flow at line conditions, Q_ref rho_ref / rho_ns(local)."""
        dyn, net = self.dyn, self.net
        hid = None
        if inst.element:
            e = dyn.elements.get(inst.element)
            if e is not None and e.id in dyn.layout.pipes:
                info = dyn.layout.pipes[e.id]
                hid = info.node_idx[0]
            elif e is not None and e.id in dyn.layout.element_link:
                li = dyn.layout.element_link[e.id]
                hid = int(net.up[li] if q_ref >= 0 else net.dn[li])
        elif inst.node is not None:
            hid = dyn.layout.node_index.get(inst.node)
        k = self.pos.get(int(hid)) if hid is not None else None
        if k is None:
            return q_ref  # not a production-zone measurement (e.g. chemical line)
        return q_ref * self.rho_ref / float(self.node_rho[k])

    def diagnostics(self) -> list[dict]:
        out: list[dict] = []
        dyn, net = self.dyn, self.net
        s = self.node_state
        if s is None:
            return out
        topo = dyn.topology
        bh = topo.node_order[1]
        k = self.pos.get(dyn.layout.node_index[bh])
        if k is not None and float(s.p[k]) < float(s.pb[k]):
            out.append({"severity": "warning", "code": "INFLOW_BELOW_BUBBLE_POINT",
                        "message": f"Bottomhole pressure ({s.p[k] / 1e5:.1f} bara) is below the bubble point ({s.pb[k] / 1e5:.1f} bara): "
                                   "free gas forms in the near-wellbore region. The dynamic radial reservoir model is single-phase "
                                   "(liquid) - inflow is OVERESTIMATED; the steady reference uses the Vogel IPR.", "location": bh})
        for j, li in enumerate(self.o_li):
            if j < self.orf_crit.size and self.orf_crit[j]:
                out.append({"severity": "info", "code": "CRITICAL_FLOW",
                            "message": f"Critical (choked) multiphase flow through {net.links[int(li)].element_id}: the rate is set by "
                                       "upstream conditions and no longer responds to downstream pressure (Sachdeva model).",
                            "location": net.links[int(li)].element_id})
        p_lo, p_hi = float(np.min(s.p)), float(np.max(s.p))
        t_lo, t_hi = float(np.min(s.t)), float(np.max(s.t))
        for v in self.fluid.validity(p_lo, p_hi, t_lo, t_hi):
            if not v["in_range"]:
                out.append({"severity": "info", "code": "CORRELATION_RANGE",
                            "message": f"{v['correlation']}: operating envelope outside the correlation data range "
                                       f"({'; '.join(v['notes'])}) - extrapolated, uncertainty increased.", "location": None})
        return out

    # -------------------------------------------------------------- report
    def cell_reference_content(self) -> np.ndarray:
        """Reference-volume content of each transport cell, V rho_m / rho_ref."""
        g = self.comp
        rho_cell = np.full(g.n, self.rho_ref)
        acc = np.zeros(g.n)
        wsum = np.zeros(g.n)
        for hid, cells in g.hnode_cells.items():
            k = self.pos.get(int(hid))
            if k is None:
                continue
            for ci, wv in cells:
                acc[ci] += self.node_rho[k] * wv
                wsum[ci] += wv
        rho_cell = np.where(wsum > 0, acc / np.maximum(wsum, 1e-30), rho_cell)
        return g.V * rho_cell / self.rho_ref

    def _cell_weights(self) -> None:
        g = self.comp
        W = np.zeros((g.n, self.prod.size))
        for hid, cells in g.hnode_cells.items():
            k = self.pos.get(int(hid))
            if k is None:
                continue
            for ci, wv in cells:
                W[ci, k] += wv
        s = W.sum(axis=1, keepdims=True)
        self._cellW = np.where(s > 0, W / np.where(s > 0, s, 1.0), 0.0)
        self._cell_has = s[:, 0] > 0

    def set_cell_targets(self, p_old: np.ndarray) -> None:
        """Cell content at the end of the step from the NEW pressures
        (linearised: rho_new = rho + d rho/dP (P_new - P_old))."""
        dp = self.net.P[self.prod] - p_old[self.prod]
        rho_new = self.node_rho + self._drdp * dp
        rho_cell = np.where(self._cell_has, self._cellW @ rho_new, self.rho_ref)
        m = self.comp.V * rho_cell / self.rho_ref
        self.comp.M_target = m
        self.dyn.grid.M_target = m.copy()

    def initialise_content(self) -> None:
        self._cell_weights()
        m = self.cell_reference_content()
        self.comp.M = m.copy()
        self.dyn.grid.M = m.copy()
        self.inventory0 = self.comp.inventory().copy()
        self.comp.in_boundary[:] = 0
        self.comp.out_boundary[:] = 0
        self.comp.out_reservoir[:] = 0

    def mass_balance(self) -> dict:
        """Component mass balance of the production path since initialisation [kg]."""
        g, rr = self.comp, self.rho_ref
        inv = g.inventory() * rr
        inv0 = (self.inventory0 if self.inventory0 is not None else g.inventory()) * rr
        cin = g.in_boundary * rr
        out = (g.out_boundary + g.out_reservoir) * rr
        names = ("oil", "gas", "water")
        res = {}
        for k, n in enumerate(names):
            resid = cin[k] - out[k] - (inv[k] - inv0[k])
            res[n] = {"in_kg": float(cin[k]), "out_kg": float(out[k]), "inventory_kg": float(inv[k]),
                      "inventory_change_kg": float(inv[k] - inv0[k]), "residual_kg": float(resid),
                      "relative_residual": float(abs(resid) / max(cin[k], out[k], abs(inv[k] - inv0[k]), 1e-9))}
        return res

    def pipe_report(self) -> list[dict]:
        if self.pipe_bb is None:
            return []
        b = self.pipe_bb
        out = []
        for j, li in enumerate(b["li"]):
            l = self.net.links[int(li)]
            out.append({"element": l.element_id, "segment": l.segment, "pattern": PATTERN_NAMES.get(int(b["pattern"][j]), "static"),
                        "holdup": float(b["holdup"][j]), "lambda_l": float(b["lambda_l"][j]), "v_sl": float(b["v_sl"][j]),
                        "v_sg": float(b["v_sg"][j]), "rho_s": float(b["rho_s"][j]), "rho_ns": float(b["rho_ns"][j]),
                        "friction_multiplier": float(b["multiplier"][j]), "p_pa": float(b["p"][j]), "t_k": float(b["t"][j]),
                        "gor": float(b["gor"][j]), "water_cut": float(b["wc"][j])})
        return out


__all__ = ["MultiphaseCoupling", "PIPE", "ORIFICE", "CHECK", "math"]
