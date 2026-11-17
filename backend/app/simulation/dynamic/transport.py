"""Chemical transport, mixing and thermal model on the production path.

Grid
----
Each hydraulic pipe segment is subdivided into m transport cells; every
production node with a cavity volume (tree bore, wing block) is one more
cell. Faces between consecutive cells carry the volumetric flow of the
hydraulic link they lie on, so fluid moves ONLY when the hydraulic model
says it moves (no timer, no assumed velocity).

Chemical volume fraction c_k (finite volume, conservative upwind):

    V_i dc_k,i/dt = F_w c_k,upwind(w) - F_e c_k,upwind(e) + Q_inj,k,i     (3)

Temperature (advective upwind form, fluid heat capacity only):

    rho cp V_i dT_i/dt = sum_in rho cp F_in (T_in - T_i)
                       + sum_inj (rho cp)_inj Q_inj (T_inj - T_i)
                       - U pi D dx (T_i - T_amb,i)                        (4)

with T_in raised by isenthalpic throttling at restriction faces,
dT = (1 - beta T) dP / (rho cp). Explicit Euler with sub-cycling so that
the cell Courant number stays below 0.8 (stable, positivity preserving).

The upwind scheme adds numerical dispersion; with N cells along a pipe the
front spreads like an axial-dispersion model with Peclet number ~ 2N. This
is the ONLY dispersion in the model (no physical Taylor dispersion term).
Plug-flow residence time t = V/Q is reported for comparison.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from app.simulation.components.elements import InflowElement, PipeElement
from app.simulation.dynamic.builder import DynamicLayout
from app.simulation.topology.topology import SeriesTopology

MAX_COURANT = 0.8
#: Link kinds that throttle (orifice-type restrictions, check valves).
_RESTR = (1, 3)


@dataclass
class NodeLookup:
    """How to evaluate T / c at a topology node."""

    cell: int | None = None  # node has its own cavity cell
    face: int | None = None  # otherwise: the face the node lies on
    #: restriction link indices on the face BEFORE this node (path order)
    before: list[int] = field(default_factory=list)
    after: list[int] = field(default_factory=list)


@dataclass
class Face:
    left_link: int
    right_link: int
    restrictions: list[int]  # restriction link indices crossed, path order
    nodes: list[str]  # topology nodes on this face, path order
    #: restriction links preceding each node on this face
    before: dict[str, list[int]] = field(default_factory=dict)


class TransportGrid:
    def __init__(self, layout: DynamicLayout, topology: SeriesTopology, n_chem: int, cells_per_segment: dict[str, int],
                 node_volumes: dict[str, float]):
        net = layout.network
        self.layout = layout
        V: list[float] = []
        amb: list[float] = []
        ua: list[float] = []
        pos: list[float] = []  # path coordinate of cell centre [m]
        length: list[float] = []
        owner: list[tuple[str, int]] = []  # (element id or node id, segment)
        hnode_of_cell: list[list[tuple[int, float]]] = []
        faces: list[Face] = []
        pending_links: list[int] = []
        pending_nodes: list[str] = []
        pending_before: dict[str, list[int]] = {}
        self.node_lookup: dict[str, NodeLookup] = {}
        self.cell_of_pipe: dict[str, list[int]] = {}
        path_x = 0.0
        last_link: int | None = None

        def close_face(next_link: int) -> None:
            links = pending_links or []
            left = links[0] if links else next_link
            restr = [li for li in links if net.kind[li] in _RESTR]
            f = Face(left, next_link, restr, list(pending_nodes), dict(pending_before))
            faces.append(f)
            for nid in pending_nodes:
                b = pending_before.get(nid, [])
                self.node_lookup[nid] = NodeLookup(face=len(faces) - 1, before=b, after=[li for li in restr if li not in b])

        inflow = topology.path[0]
        assert isinstance(inflow, InflowElement)
        pending_links.append(layout.element_link[inflow.id])
        node_order = topology.node_order
        for k, e in enumerate(topology.path):
            nid = node_order[k]
            if k > 0:
                # node between element k-1 and element k
                vol = node_volumes.get(nid, 0.0)
                if vol > 0:
                    close_face(pending_links[-1] if pending_links else last_link)  # type: ignore[arg-type]
                    pending_links.clear(); pending_nodes.clear(); pending_before.clear()
                    ci = len(V)
                    hi = layout.node_index[nid]
                    V.append(vol); length.append(0.0); pos.append(path_x)
                    ua_amb = layout.cavity_ua.get(nid)
                    ua.append(ua_amb[0] if ua_amb else 0.0)
                    amb.append(ua_amb[1] if ua_amb else 277.15)
                    owner.append((nid, 0)); hnode_of_cell.append([(hi, 1.0)])
                    self.node_lookup[nid] = NodeLookup(cell=ci)
                else:
                    pending_nodes.append(nid)
                    pending_before[nid] = [li for li in pending_links if net.kind[li] in _RESTR]
            if isinstance(e, InflowElement):
                continue
            if isinstance(e, PipeElement):
                info = layout.pipes[e.id]
                m = cells_per_segment.get(e.id, 1)
                dl_seg = e.geometry.length / info.segments
                dx = dl_seg / m
                cells = []
                for s in range(info.segments):
                    li = info.link_idx[s]
                    for j in range(m):
                        # face before this cell
                        if j == 0:
                            close_face(li)
                            pending_links.clear(); pending_nodes.clear(); pending_before.clear()
                        else:
                            faces.append(Face(li, li, [], []))
                        ci = len(V)
                        cells.append(ci)
                        V.append(info.area * dx)
                        length.append(dx)
                        frac = (s * dl_seg + (j + 0.5) * dx) / e.geometry.length
                        amb.append(e.ambient_in + (e.ambient_out - e.ambient_in) * frac)
                        ua.append(e.overall_htc * math.pi * e.geometry.diameter * dx)
                        pos.append(path_x + s * dl_seg + (j + 0.5) * dx)
                        owner.append((e.id, s))
                        # hydraulic node weights (vertex-centred volumes)
                        a_node, b_node = info.node_idx[s], info.node_idx[s + 1]
                        x = (j + 0.5) / m
                        hnode_of_cell.append([(a_node, 1.0)] if x < 0.5 else [(b_node, 1.0)] if x > 0.5 else [(a_node, 0.5), (b_node, 0.5)])
                    pending_links.append(li)
                    if s < info.segments - 1:
                        pass  # next segment's first cell closes a face on its own link
                path_x += e.geometry.length
                self.cell_of_pipe[e.id] = cells
                last_link = info.link_idx[-1]
            else:
                li = layout.element_link[e.id]
                pending_links.append(li)
                last_link = li
        # outlet face (to the boundary)
        bnode = node_order[-1]
        pending_nodes.append(bnode)
        pending_before[bnode] = [li for li in pending_links if net.kind[li] in _RESTR]
        close_face(pending_links[-1] if pending_links else last_link)  # type: ignore[arg-type]
        self.faces = faces
        self.n = len(V)
        assert len(faces) == self.n + 1, (len(faces), self.n)
        self.V = np.array(V)
        #: solid heat capacity attached to cells (tree body) [J/K]
        self.mass = np.zeros(len(V))
        for ci, (own, _) in enumerate(owner):
            if own in layout.cavity_mass:
                self.mass[ci] = layout.cavity_mass[own]
        self.amb = np.array(amb)
        self.ua = np.array(ua)
        self.pos = np.array(pos)
        self.dx = np.array(length)
        self.owner = owner
        self.face_left = np.array([f.left_link for f in faces], dtype=int)
        self.face_right = np.array([f.right_link for f in faces], dtype=int)
        self.face_restr = [f.restrictions for f in faces]
        self.restr_faces = [i for i, f in enumerate(faces) if f.restrictions]
        # hydraulic node <- cells (volume weights) for node temperatures
        hn: dict[int, list[tuple[int, float]]] = {}
        for ci, ws in enumerate(hnode_of_cell):
            for hi, w in ws:
                hn.setdefault(hi, []).append((ci, w * V[ci]))
        self.hnode_cells = hn
        self._hn_ids = np.array(sorted(hn), dtype=int)
        W = np.zeros((len(self._hn_ids), len(V)))
        for r, hi in enumerate(self._hn_ids):
            for ci, w in hn[hi]:
                W[r, ci] += w
        self._hn_W = W / W.sum(axis=1, keepdims=True)
        self._cell_cache: dict[tuple[str, float], int] = {}
        self.F = np.zeros(len(V) + 1)
        self.n_chem = n_chem
        self.c = np.zeros((n_chem, self.n))
        self.T = self.amb.copy()
        # bookkeeping [m3 of chemical]
        self.injected = np.zeros(n_chem)
        #: Multiphase (mass-based) mode: fluid content of each cell in
        #: reference volumes, transported with the face flows so that
        #: sum(c * M) is conserved exactly while the fluid compresses / expands.
        self.mass_tracking = False
        self.M = self.V.copy()
        #: Content each cell must hold at the END of the next step (set by the
        #: multiphase coupling from the new pressures). The face flows are then
        #: reconstructed from the inlet flow so that every cell's change of
        #: content is exactly the fluid it gained - consistent, conservative.
        self.M_target: np.ndarray | None = None
        #: Concentration of the fluid entering at the reservoir / boundary end.
        self.c_left = np.zeros(n_chem)
        self.c_right = np.zeros(n_chem)
        self.in_boundary = np.zeros(n_chem)
        self.out_boundary = np.zeros(n_chem)
        self.out_reservoir = np.zeros(n_chem)
        self.dT_throttle = np.zeros(self.n + 1)
        self.dT_parts: dict[int, dict[int, float]] = {}

    # ----------------------------------------------------------------- flows
    def face_flows(self, Q: np.ndarray) -> np.ndarray:
        ql, qr = Q[self.face_left], Q[self.face_right]
        return np.where(ql + qr >= 0.0, ql, qr)

    def set_flows(self, Q: np.ndarray) -> np.ndarray:
        """Compute and cache the face flows of the current hydraulic state."""
        self.F = self.face_flows(Q)
        return self.F

    def throttle(self, F: np.ndarray, P: np.ndarray, rho: float, cp: float, beta: float,
                 link_props: dict[int, tuple[float, float, float]] | None = None) -> np.ndarray:
        """Temperature rise of fluid crossing each face in its flow direction.

        ``link_props`` (multiphase): per restriction link (rho, cp, beta) of
        the upstream mixture, overriding the scalar properties."""
        net = self.layout.network
        dT = np.zeros(self.n + 1)
        parts: dict[int, dict[int, float]] = {}
        for fi in self.restr_faces:
            forward = F[fi] >= 0
            if forward:
                t_up = float(self.T[fi - 1]) if fi > 0 else float(self.T[0])
            else:
                t_up = float(self.T[fi]) if fi < self.n else float(self.T[-1])
            pf = {}
            for li in self.face_restr[fi]:
                dp = P[net.up[li]] - P[net.dn[li]]
                loss = dp if forward else -dp
                r_, c_, b_ = link_props[li] if link_props and li in link_props else (rho, cp, beta)
                pf[li] = (1.0 - b_ * t_up) * max(loss, 0.0) / (r_ * c_)
            parts[fi] = pf
            dT[fi] = sum(pf.values())
        self.dT_throttle = dT
        self.dT_parts = parts
        return dT

    def injection_cell(self, face: int, F: np.ndarray) -> int:
        if F[face] >= 0:
            return min(face, self.n - 1)
        return max(face - 1, 0)

    # ------------------------------------------------------------------ step
    def step(self, dt: float | None, F: np.ndarray, dT_face: np.ndarray, injections: list[tuple[int, int, float, float, float]],
             T_res: float, T_bnd: float, rhocp: float, thermal: bool = True) -> None:
        """Advance by dt (None -> steady state).

        injections: (chem index, cell index, Q_inj [m3/s], T_inj [K], (rho cp)_inj).
        """
        if dt is None:
            self._steady(F, dT_face, injections, T_res, T_bnd, rhocp)
            return
        n = self.n
        src_c = np.zeros((self.n_chem, n))
        inj_q = np.zeros(n)
        inj_qt = np.zeros(n)
        for k, ci, q, t_inj, rc in injections:
            if q <= 0:
                continue
            src_c[k, ci] += q
            w = q * rc / rhocp
            inj_q[ci] += w
            inj_qt[ci] += w * t_inj
            self.injected[k] += q * dt
        mt = self.mass_tracking
        if mt and self.M_target is not None:
            dm = (self.M_target - self.M) / dt
            net_src = src_c.sum(axis=0) - dm
            Fr = np.empty_like(F)
            if F[0] >= 0 or F[-1] >= 0:
                Fr[0] = F[0]
                Fr[1:] = F[0] + np.cumsum(net_src)
            else:  # reverse flow: anchor at the boundary end
                Fr[-1] = F[-1]
                Fr[:-1] = F[-1] - np.cumsum(net_src[::-1])[::-1]
            F = Fr
            self.F_mass = Fr
        inL = np.maximum(F[:-1], 0.0)
        inR = np.maximum(-F[1:], 0.0)
        loss = self.ua / rhocp
        Vc = self.M if mt else self.V
        vth = Vc + self.mass / rhocp  # thermal "volume" incl. solid heat capacity
        rate = (inL + inR + src_c.sum(axis=0)) / Vc
        if thermal:
            rate = np.maximum(rate, (inL + inR + inj_q + loss) / vth)
        nsub = max(1, math.ceil(dt * float(rate.max()) / MAX_COURANT))
        h = dt / nsub
        c = self.c
        T = self.T
        M = self.M
        cl, cr = self.c_left[:, None], self.c_right[:, None]
        src_tot = src_c.sum(axis=0)
        for _ in range(nsub):
            # concentration (conservative)
            ext = np.concatenate([cl, c, cr], axis=1)
            cf = np.where(F >= 0.0, ext[:, :-1], ext[:, 1:])
            flux = F * cf
            if mt:
                m_new = np.maximum(M + h * (F[:-1] - F[1:] + src_tot), 1e-12)
                c = (c * M + h * (flux[:, :-1] - flux[:, 1:] + src_c)) / m_new
                M = m_new
                vth = M + self.mass / rhocp
            else:
                c = c + h * (flux[:, :-1] - flux[:, 1:] + src_c) / self.V
            self.out_boundary += h * np.maximum(flux[:, -1], 0.0)
            self.out_reservoir += h * np.maximum(-flux[:, 0], 0.0)
            self.in_boundary += h * (np.maximum(flux[:, 0], 0.0) + np.maximum(-flux[:, -1], 0.0))
            if not thermal:
                continue
            # temperature (advective)
            Tl = np.concatenate([[T_res], T[:-1]]) + dT_face[:-1]
            Tr = np.concatenate([T[1:], [T_bnd]]) + dT_face[1:]
            dTdt = (inL * (Tl - T) + inR * (Tr - T) + inj_qt - inj_q * T - loss * (T - self.amb)) / vth
            T = T + h * dTdt
        self.c = np.clip(c, 0.0, 1.0)
        self.T = T
        if mt:
            self.M = M

    def _steady(self, F, dT_face, injections, T_res, T_bnd, rhocp) -> None:
        n = self.n
        src_c = np.zeros((self.n_chem, n))
        inj_q = np.zeros(n)
        inj_qt = np.zeros(n)
        for k, ci, q, t_inj, rc in injections:
            if q <= 0:
                continue
            src_c[k, ci] += q
            w = q * rc / rhocp
            inj_q[ci] += w
            inj_qt[ci] += w * t_inj
        loss = self.ua / rhocp
        forward = F.sum() >= 0
        order = range(n) if forward else range(n - 1, -1, -1)
        c = np.zeros((self.n_chem, n))
        T = np.zeros(n)
        for i in order:
            if forward:
                fin = max(F[i], 0.0)
                c_up = c[:, i - 1] if i > 0 else self.c_left
                t_up = (T[i - 1] if i > 0 else T_res) + dT_face[i]
            else:
                fin = max(-F[i + 1], 0.0)
                c_up = c[:, i + 1] if i < n - 1 else self.c_right
                t_up = (T[i + 1] if i < n - 1 else T_bnd) + dT_face[i + 1]
            qin = fin + src_c[:, i].sum()
            c[:, i] = (fin * c_up + src_c[:, i]) / qin if qin > 0 else 0.0
            den = fin + inj_q[i] + loss[i]
            T[i] = (fin * t_up + inj_qt[i] + loss[i] * self.amb[i]) / den if den > 0 else self.amb[i]
        self.c = c
        self.T = T

    # -------------------------------------------------------------- queries
    def node_value(self, nid: str, F: np.ndarray, dT_face: np.ndarray, which: str, chem: int = 0,
                   injections_at: dict[str, list[tuple[int, float]]] | None = None) -> float:
        """Temperature (which='T') or concentration ('c') at a topology node."""
        lk = self.node_lookup[nid]
        if lk.cell is not None:
            return float(self.T[lk.cell] if which == "T" else self.c[chem, lk.cell])
        fi = lk.face
        assert fi is not None
        forward = F[fi] >= 0
        if forward:
            up = fi - 1 if fi > 0 else None
        else:
            up = fi if fi < self.n else None
        if which == "c":
            val = 0.0 if up is None else float(self.c[chem, up])
            # mixing at an injection node without its own cavity
            if injections_at and nid in injections_at:
                q_up = abs(float(F[fi]))
                q_k = sum(q for k, q in injections_at[nid] if k == chem)
                q_all = sum(q for _, q in injections_at[nid])
                tot = q_up + q_all
                if tot > 0:
                    val = (q_up * val + q_k) / tot
            return val
        # temperature: upwind cell + throttling of restrictions crossed so far
        if up is None:
            return float(self.T[0] if fi == 0 else self.T[-1])
        t = float(self.T[up])
        pf = self.dT_parts.get(fi, {})
        for li in (lk.before if forward else lk.after):
            t += pf.get(li, 0.0)
        return t

    def hnode_temperature(self) -> tuple[np.ndarray, np.ndarray]:
        """(hydraulic node indices, volume-weighted temperatures)."""
        return self._hn_ids, self._hn_W @ self.T

    def cell_at(self, element_id: str, distance_m: float) -> int:
        key = (element_id, distance_m)
        if key not in self._cell_cache:
            self._cell_cache[key] = self._cell_at(element_id, distance_m)
        return self._cell_cache[key]

    def _cell_at(self, element_id: str, distance_m: float) -> int:
        cells = self.cell_of_pipe[element_id]
        x0 = self.pos[cells[0]] - self.dx[cells[0]] / 2
        for ci in cells:
            if self.pos[ci] - x0 + self.dx[ci] / 2 >= distance_m - 1e-9:
                return ci
        return cells[-1]

    def inventory(self) -> np.ndarray:
        return (self.c * (self.M if self.mass_tracking else self.V)).sum(axis=1)
