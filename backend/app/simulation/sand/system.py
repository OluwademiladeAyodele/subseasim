"""Sand production -> transport -> detection -> choke erosion -> health.

One object per engine (three-phase model). Every quantity is derived from
the same simulation state as the rest of SubseaSim: reservoir and bottomhole
pressure (drawdown), produced phase rates and composition, choke position,
pressures and capacity, transported sand concentration.

Missing site data never get silently replaced: every result carries
``available`` and ``missing`` (inputs required) and ``assumed`` (defaults
used, which lower the confidence).
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field

import numpy as np

from app.models.sand import SandChokeInputs
from app.simulation.choke import cavitation as cav
from app.simulation.multiphase.correlations import sachdeva_critical_ratio
from app.simulation.multiphase.dynamic import SAND_CH
from app.simulation.sand import erosion as er
from app.simulation.sand import measurements as smeas
from app.simulation.sand import production as sp
from app.simulation.fluid_properties.black_oil import bubble_point

S_PER_DAY = 86400.0
S_PER_YEAR = 365.25 * S_PER_DAY
#: Prior uncertainty of the generic trim erosion model (90 % range = factor 5).
SIGMA_K_PRIOR = math.log(5.0) / 1.645
#: Uncertainty assigned to one inspection-based calibration point (log space).
SIGMA_INSPECTION = 0.35
#: Uncertainty of a PREDICTED (geomechanics) sand rate, 90 % range = factor 5.
SIGMA_SAND_PREDICTED = math.log(5.0) / 1.645
Z90 = 1.2815515655446004
LOG_INTERVAL_S = 3600.0


@dataclass
class OperatingPoint:
    """Instantaneous operating conditions used by the sand / erosion models."""

    p_res: float
    p_bh: float
    w_in: float  # kg/s production mass flow entering the well
    q_ref_in: float  # reservoir-condition liquid volume flow [m3/s]
    gor: float
    wc: float
    position_pct: float
    p1: float
    p2: float
    t1: float
    w_choke: float
    gor_choke: float
    wc_choke: float
    sand_frac_choke: float | None  # transported kg sand / kg fluid at the choke (None: steady)
    sand_frac_detector: float | None
    flowline_d: float


@dataclass
class WearLog:
    service_days: list[float] = field(default_factory=list)
    dd: list[np.ndarray] = field(default_factory=list)  # base (uncalibrated) hole growth per row [m]
    plug: list[float] = field(default_factory=list)
    sand_kg: list[float] = field(default_factory=list)
    liquid_sm3: list[float] = field(default_factory=list)

    def add(self, days, dd, plug, sand, liq):
        self.service_days.append(days)
        self.dd.append(dd.copy())
        self.plug.append(plug)
        self.sand_kg.append(sand)
        self.liquid_sm3.append(liq)

    def at(self, days: float) -> tuple[np.ndarray, float] | None:
        if not self.service_days or days > self.service_days[-1] + 1e-6:
            return None
        ts = np.array(self.service_days)
        k = int(np.searchsorted(ts, days))
        if k == 0:
            return self.dd[0], self.plug[0]
        t0, t1 = ts[k - 1], ts[min(k, len(ts) - 1)]
        f = 0.0 if t1 == t0 else (days - t0) / (t1 - t0)
        j = min(k, len(ts) - 1)
        return self.dd[k - 1] + f * (self.dd[j] - self.dd[k - 1]), self.plug[k - 1] + f * (self.plug[j] - self.plug[k - 1])


def production_choke(engine):
    return next((r for r in engine.restrictions.values() if r.kind == "choke" and getattr(r, "subtype", "") == "choke"), None)


def configure_choke(ch, inputs: SandChokeInputs) -> None:
    """The simulated production choke takes the entered trim data (max Cv,
    controllable range, actuator steps, vendor Cv-vs-step table). Applies in
    single- and three-phase mode - it is the same hardware."""
    if ch is None:
        return
    if not hasattr(ch, "_orig_trim"):
        ch._orig_trim = (ch.cv_max, ch.rangeability, ch.cv_table, ch.steps)
    cv_max, rang, table, steps = ch._orig_trim
    c = inputs.choke
    if c.max_cv:
        cv_max = c.max_cv
        if c.min_controllable_cv:
            rang = max(2.0, c.max_cv / c.min_controllable_cv)
    steps = c.actuator_steps or steps
    if c.cv_table and c.actuator_steps:
        table = [(100.0 * s / c.actuator_steps, cv) for s, cv in sorted(c.cv_table)]
        if table[0][0] > 0:
            table = [(0.0, 0.0)] + table
    ch.cv_max, ch.rangeability, ch.cv_table, ch.steps = cv_max, rang, table, steps


class SandChokeSystem:
    def __init__(self, engine, inputs: SandChokeInputs, seed: int = 11):
        self.engine = engine
        self.rng = np.random.default_rng(seed)
        self.inputs = inputs
        self.apply_inputs(inputs)

    # ============================================================ inputs
    def apply_inputs(self, inputs: SandChokeInputs) -> None:
        self.inputs = inputs
        # sand inputs as used by the model (latest measured record in measured mode)
        self.sand_eff, self.driving_measurement = smeas.effective_sand(inputs.sand)
        e = self.engine
        self.choke = production_choke(e)
        configure_choke(self.choke, inputs)
        c = inputs.choke
        self.geom = er.CageGeometry(c)
        self.mat_trim = er.material(c.trim_material, inputs.custom_materials)
        self.mat_body = er.material(c.body_material, inputs.custom_materials)
        self.psd = sp.fit_psd(inputs.sand)
        self.screen = sp.screen_passing(inputs.completion, self.psd)
        # detector calibration bias drawn once (calibrated instrument, unknown residual bias)
        self.det_bias = float(np.exp(self.rng.normal(0.0, inputs.detector.calibration_uncertainty_pct / 100.0)))
        self._reset_state()
        # feedback before the history: the history integration sees the same worn-trim Cv
        # as the live simulation, so every save is self-consistent
        self._install_feedback()
        self._apply_history()
        self._calibrate()
        self.last_op: OperatingPoint | None = None
        self._update_rates_only()

    def _reset_state(self) -> None:
        n = len(self.geom.rows)
        self.dd_base = np.zeros(n)
        self.plug_base = 0.0
        self.body_loss = 0.0
        self.outlet_loss = 0.0
        self.service_s = 0.0
        self.cum = {"formation_kg": 0.0, "produced_kg": 0.0, "retained_kg": 0.0, "choke_kg": 0.0, "detector_meas_kg": 0.0,
                    "liquid_sm3": 0.0, "oil_sm3": 0.0, "gas_sm3": 0.0, "water_sm3": 0.0}
        self.log = WearLog()
        self.rates: dict = {}
        self.det = {"reading_g_s": None, "status": "NOT_READY", "alarm": False}
        self.cv_track: deque = deque(maxlen=500)
        self._last_log = -math.inf
        self.log_cal_c = 0.0
        self.sigma_c = SIGMA_K_PRIOR
        self.calibration_points: list[dict] = []
        self.replacement_days = 0.0
        self._dd_at_replacement = np.zeros(n)
        self._plug_at_replacement = 0.0

    # ======================================================= calibration
    @property
    def c_factor(self) -> float:
        return math.exp(self.log_cal_c)

    def _epoch_base(self, days: float):
        """Base wear accumulated since the last trim replacement at ``days``."""
        cur = self.log.at(days)
        ref = self.log.at(self.replacement_days) if self.replacement_days > 0 else None
        if cur is None:
            return None
        dd, plug = cur
        if ref is not None:
            dd, plug = dd - ref[0], plug - ref[1]
        return dd, plug

    def dd_cal(self) -> np.ndarray:
        dd = self.dd_base - (self._dd_at_replacement if hasattr(self, "_dd_at_replacement") else 0.0)
        return self.c_factor * dd

    def plug_cal(self) -> float:
        return self.c_factor * (self.plug_base - getattr(self, "_plug_at_replacement", 0.0))

    def _calibrate(self) -> None:
        """Bayesian (log-normal) update of the trim-erosion factor C from the
        inspection records whose service time is covered by the wear history."""
        num, den = 0.0, 1.0 / SIGMA_K_PRIOR**2
        pts = []
        epoch = 0.0
        for ins in sorted(self.inputs.inspections, key=lambda r: r.service_days):
            cur = self.log.at(ins.service_days)
            ref = self.log.at(epoch) if epoch > 0 else None
            rec = {"label": ins.label, "service_days": ins.service_days, "used": False, "ratio": None, "note": ""}
            if cur is None:
                rec["note"] = "service time beyond the available wear history (enter the operating history up to this inspection)"
                pts.append(rec)
                continue
            dd, plug = cur
            if ref is not None:
                dd, plug = dd - ref[0], plug - ref[1]
            ratios = []
            if ins.measured_max_hole_increase_mm is not None and dd.size and dd.max() > 0:
                ratios.append(ins.measured_max_hole_increase_mm * 1e-3 / float(dd.max()))
            if ins.measured_plug_loss_mm is not None and plug > 0:
                ratios.append(ins.measured_plug_loss_mm * 1e-3 / plug)
            if ins.measured_cv_increase_pct is not None and self.geom.valid and dd.size:
                ref_pos = self._ref_position()
                pred = (self.geom.wear_factor(ref_pos, dd) - 1.0) * 100.0
                if pred > 1e-6 and ins.measured_cv_increase_pct > 0:
                    ratios.append(ins.measured_cv_increase_pct / pred)
            ratios = [r for r in ratios if r > 0]
            if ratios:
                lr = float(np.mean(np.log(ratios)))
                num += lr / SIGMA_INSPECTION**2
                den += 1.0 / SIGMA_INSPECTION**2
                rec.update({"used": True, "ratio": float(math.exp(lr)),
                            "note": f"measured / predicted (uncalibrated) = {math.exp(lr):.2f}"})
            else:
                rec["note"] = "no comparable measurement (model wear zero or no measured value)"
            pts.append(rec)
            if ins.trim_replaced:
                epoch = ins.service_days
        self.log_cal_c = num / den
        self.sigma_c = 1.0 / math.sqrt(den)
        self.calibration_points = pts
        # wear epoch: last replacement at or before the current service time
        reps = [i.service_days for i in self.inputs.inspections if i.trim_replaced and i.service_days <= self.service_s / S_PER_DAY + 1e-9]
        self.replacement_days = max(reps) if reps else 0.0
        at = self.log.at(self.replacement_days) if self.replacement_days > 0 else None
        self._dd_at_replacement = at[0] if at is not None else np.zeros_like(self.dd_base)
        self._plug_at_replacement = at[1] if at is not None else 0.0

    def _install_feedback(self) -> None:
        ch = self.choke
        if ch is None:
            return
        if self.inputs.choke.erosion_feedback and self.geom.valid:
            ch.wear_factor = lambda pos: self.geom.wear_factor(pos, self.dd_cal())
        else:
            ch.wear_factor = None

    def _ref_position(self) -> float:
        a = self.inputs.acceptance
        steps = self.inputs.choke.actuator_steps
        if a.reference_step is not None and steps:
            return 100.0 * a.reference_step / steps
        return self.choke.actuator.position_pct if self.choke is not None else 50.0

    # ============================================================ history
    def _apply_history(self) -> None:
        """Integrate entered past operating periods (pre-loads wear and cumulative sand)."""
        bo = self.engine.bo
        hist = self.inputs.history
        if not hist:
            self.service_s = self.inputs.initial_service_days * S_PER_DAY
            self.log.add(self.service_s / S_PER_DAY, self.dd_base, self.plug_base, 0.0, 0.0)
            return
        self.log.add(0.0, self.dd_base, self.plug_base, 0.0, 0.0)
        steps = self.inputs.choke.actuator_steps or 100
        for h in hist:
            oil, gas, water = h.oil_sm3_d / S_PER_DAY, h.gas_sm3_d / S_PER_DAY, h.water_sm3_d / S_PER_DAY
            p = bo.params
            w = oil * p.rho_oil_sc + gas * p.rho_gas_sc + water * p.rho_water_sc
            gor = gas / oil if oil > 0 else 0.0
            wc = water / (oil + water) if oil + water > 0 else 0.0
            pos = 100.0 * h.choke_step / steps
            op = OperatingPoint(0, 0, w, 0, gor, wc, pos, h.upstream_pressure_bara * 1e5, h.downstream_pressure_bara * 1e5,
                                h.temperature_c + 273.15, w, gor, wc, None, None, self._flowline_d())
            m_sand = h.sand_kg_d / S_PER_DAY
            nsub = 10
            dt = h.days * S_PER_DAY / nsub
            for _ in range(nsub):
                self._erode(op, m_sand, dt)
                self.service_s += dt
                self.cum["choke_kg"] += m_sand * dt
                self.cum["produced_kg"] += m_sand * dt
                self.cum["liquid_sm3"] += (oil + water) * dt
                self.cum["oil_sm3"] += oil * dt
                self.cum["gas_sm3"] += gas * dt
                self.cum["water_sm3"] += water * dt
            self.log.add(self.service_s / S_PER_DAY, self.dd_base, self.plug_base, self.cum["choke_kg"], self.cum["liquid_sm3"])

    # ========================================================== operating
    def _flowline_d(self) -> float:
        e = self.engine
        for el in e.topology.path:
            if el.kind == "pipe" and el.from_node == (self.choke.to_node if self.choke else None):
                return el.geometry.diameter
        return 0.15

    def operating_point(self) -> OperatingPoint | None:
        e = self.engine
        ch = self.choke
        if ch is None or e.bo is None:
            return None
        topo = e.topology
        bh = topo.node_order[1]
        rr = e.rho_ref
        if getattr(e, "dyn", None) is not None:
            d = e.dyn
            net = d.net
            mp = d.mp
            q_in = float(net.Q[d.layout.element_link[topo.path[0].id]])
            li = d.layout.element_link[ch.id]
            w_ch = rr * float(net.Q[li])
            gor_n, wc_n = mp.node_composition()
            k = mp.pos.get(d.layout.node_index[ch.from_node])
            g_c, w_c = (float(gor_n[k]), float(wc_n[k])) if k is not None else (e.mp_gor, e.mp_wc)
            sg = mp.comp
            F = getattr(sg, "F_mass", d.grid.F)
            try:
                s_c = float(sg.node_value(ch.from_node, F, d.grid.dT_throttle, "c", chem=SAND_CH))
                s_d = float(sg.node_value(ch.to_node, F, d.grid.dT_throttle, "c", chem=SAND_CH))
            except (KeyError, AssertionError):
                s_c = s_d = None
            return OperatingPoint(e.ipr.p_res, d.node_pressure(bh), rr * q_in, q_in, e.mp_gor, e.mp_wc, ch.actuator.position_pct,
                                  d.node_pressure(ch.from_node), d.node_pressure(ch.to_node), d.node_temperature(ch.from_node),
                                  w_ch, g_c, w_c, s_c, s_d, self._flowline_d())
        h = getattr(e, "hyd", None)
        if h is None or not h.ok:
            return None
        q = max(h.q, 0.0)
        temps = e._node_temperatures()
        return OperatingPoint(e.ipr.p_res, h.node_pressure[bh], rr * q, q, e.mp_gor, e.mp_wc, ch.actuator.position_pct,
                              h.node_pressure[ch.from_node], h.node_pressure[ch.to_node], temps[ch.from_node], rr * q,
                              e.mp_gor, e.mp_wc, None, None, self._flowline_d())

    # ---------------------------------------------------------- sand rate
    def sand_source(self, op: OperatingPoint) -> dict:
        """Sand at the sandface (formation), through the screens (produced)."""
        bo = self.engine.bo
        inp = self.inputs
        onset = sp.sanding_onset(inp.geomechanics, op.p_res, op.p_bh, op.wc)
        q_liq_sc = op.w_in / float(bo.mass_per_liquid_sc(op.gor, op.wc)) if op.w_in > 0 else 0.0
        p = bo.params
        liq_mass = q_liq_sc * ((1 - op.wc) * p.rho_oil_sc + op.wc * p.rho_water_sc)
        out = {"onset": onset, "mode": self.sand_eff.mode, "formation_kg_s": None, "produced_kg_s": None, "missing": [], "assumed": list(onset.assumed),
               "q_liquid_sc_m3s": q_liq_sc}
        f = self.screen.passing_fraction if self.screen.available else None
        if self.sand_eff.mode == "measured":
            m = sp.measured_rate_kg_s(self.sand_eff, q_liq_sc, liq_mass, op.w_in)
            if m is None:
                out["missing"].append("measured sand value")
            else:
                out["produced_kg_s"] = m
                out["formation_kg_s"] = m / f if f and f > 0 else None
        else:
            if not onset.available:
                out["missing"] += onset.missing
            m, miss = sp.predicted_formation_rate(inp.sand, onset, op.q_ref_in)
            out["missing"] += [x for x in miss if x != "sanding onset unavailable"]
            if not self.screen.available:
                out["missing"] += self.screen.missing
            if m is not None:
                out["formation_kg_s"] = m
                out["produced_kg_s"] = m * f if f is not None else None
        return out

    # ------------------------------------------------------------ erosion
    def _velocities(self, op: OperatingPoint) -> dict:
        bo = self.engine.bo
        ch = self.choke
        s1 = bo.state(op.p1, op.t1, op.gor_choke, op.wc_choke)
        x = float(s1.free_gas_mass_fraction[0])
        rho_l, rho_g = float(s1.rho_l[0]), float(s1.rho_g[0])
        k = bo.params.gas_cp_cv
        yc = 0.0
        if x > 1e-7:
            cv = bo.params.cp_gas_j_kgk / k
            c_l = (float(s1.mass_o[0]) * bo.params.cp_oil_j_kgk + float(s1.mass_w[0]) * bo.params.cp_water_j_kgk) / max(float(s1.mass_o[0] + s1.mass_w[0]), 1e-12)
            n = 1.0 + x * (bo.params.cp_gas_j_kgk - cv) / (x * cv + (1 - x) * c_l)
            yc = float(sachdeva_critical_ratio(np.array([x]), rho_l, np.array([1 / max(rho_g, 1e-6)]), k, np.array([n]))[0])
        cda = ch.capacity_at(op.position_pct) if ch is not None else 0.0
        u_jet = er.jet_velocity(op.p1, op.p2, max(op.w_choke, 0.0), cda, rho_l, rho_g, x, k, yc)
        s2 = bo.state(op.p2, op.t1, op.gor_choke, op.wc_choke)
        q_dn = max(op.w_choke, 0.0) / float(s2.rho_ns[0])
        q_up = max(op.w_choke, 0.0) / float(s1.rho_ns[0])
        c = self.inputs.choke
        a_out = math.pi * (c.choke_outlet_bore_mm * 1e-3) ** 2 / 4 if c.choke_outlet_bore_mm else None
        a_gal = math.pi * (c.gallery_diameter_mm * 1e-3) ** 2 / 4 if c.gallery_diameter_mm else None
        a_fl = math.pi * op.flowline_d**2 / 4
        return {"u_jet": u_jet, "critical": op.p2 / max(op.p1, 1.0) < yc, "y_crit": yc, "u_outlet": q_dn / a_out if a_out else None,
                "u_gallery": q_up / a_gal if a_gal else None, "u_flowline": q_dn / a_fl, "rho_l": rho_l, "rho_g": rho_g, "x": x,
                "rho_mix_dn": float(s2.rho_ns[0]), "rho_mix_up": float(s1.rho_ns[0]), "v_sl_flowline": max(op.w_choke, 0.0) * (1 - x) / rho_l / a_fl}

    def _erode(self, op: OperatingPoint, m_sand: float, dt: float) -> dict:
        """Integrate wear over dt at a constant operating point; returns rates."""
        c = self.inputs.choke
        v = self._velocities(op)
        r: dict = {"velocities": v, "m_sand_choke": m_sand}
        if self.mat_trim is not None:
            erat = er.erosion_ratio(self.mat_trim, v["u_jet"], c.trim_impact_angle_deg)
            vrate = erat * m_sand / self.mat_trim.density  # m3/s, uncalibrated
            r.update({"erosion_ratio": erat, "trim_volume_rate_m3_s": vrate})
            if self.geom.valid:
                # growth RATE of each row (base, uncalibrated) from the volume-loss rate
                rate_rows = self.geom.distribute(vrate * (1 - c.plug_share), op.position_pct, self.dd_cal())
                self.dd_base = self.dd_base + rate_rows * dt
                r["hole_growth_rate_m_s"] = rate_rows
            if c.plug_diameter_mm and c.cage_wall_thickness_mm:
                band = math.pi * c.plug_diameter_mm * 1e-3 * c.cage_wall_thickness_mm * 1e-3
                prate = vrate * c.plug_share / band
                self.plug_base += prate * dt
                r["plug_rate_m_s"] = prate
        if self.mat_body is not None and v["u_gallery"] is not None and c.gallery_diameter_mm:
            area = math.pi * (c.gallery_diameter_mm * 1e-3) ** 2 / 4
            br = er.impingement_rate_m_s(self.mat_body, v["u_gallery"], m_sand, area)
            self.body_loss += br * dt
            r["body_rate_m_s"] = br
        if v["u_outlet"] is not None and c.choke_outlet_bore_mm:
            orate = er.outlet_wall_rate_mm_y(v["u_outlet"], c.choke_outlet_bore_mm * 1e-3, m_sand) * 1e-3 / S_PER_YEAR
            self.outlet_loss += orate * dt
            r["outlet_rate_m_s"] = orate
        return r

    # ================================================================ step
    #: Wear / detector update period in simulated time (wear changes slowly);
    #: immediate while the choke is moving.
    UPDATE_S = 10.0
    CV_TRACK_S = 600.0

    def step(self, dt: float) -> None:
        self._acc = getattr(self, "_acc", 0.0) + dt
        moving = self.choke is not None and self.choke.actuator.is_moving
        if self._acc < self.UPDATE_S and not moving:
            return
        dt, self._acc = self._acc, 0.0
        self._step(dt)

    def _step(self, dt: float) -> None:
        op = self.operating_point()
        if op is None:
            return
        self.last_op = op
        src = self.sand_source(op)
        self.last_source = src
        e = self.engine
        prod = src["produced_kg_s"] or 0.0
        form = src["formation_kg_s"] or 0.0
        # sand enters the transported flow at the sandface as a mass fraction of the fluid
        if e.dyn is not None and e.dyn.mp is not None:
            e.dyn.mp.comp.c_left[SAND_CH] = min(prod / op.w_in, 0.2) if op.w_in > 1e-6 else 0.0
        m_choke = (op.sand_frac_choke * max(op.w_choke, 0.0)) if op.sand_frac_choke is not None else prod
        m_det = (op.sand_frac_detector * max(op.w_choke, 0.0)) if op.sand_frac_detector is not None else prod
        r = self._erode(op, m_choke, dt)
        self.rates = r
        self.service_s += dt
        bo = e.bo
        q_liq = src["q_liquid_sc_m3s"]
        self.cum["formation_kg"] += form * dt
        self.cum["produced_kg"] += prod * dt
        self.cum["retained_kg"] += max(form - prod, 0.0) * dt
        self.cum["choke_kg"] += m_choke * dt
        self.cum["liquid_sm3"] += q_liq * dt
        self.cum["oil_sm3"] += q_liq * (1 - op.wc) * dt
        self.cum["water_sm3"] += q_liq * op.wc * dt
        self.cum["gas_sm3"] += q_liq * (1 - op.wc) * op.gor * dt
        v = r["velocities"]
        # SDT-101 is on the choke outlet down-leg: outlet-bore velocity when the bore is known
        self._detector(m_det, v["u_outlet"] if v["u_outlet"] is not None else v["u_flowline"], dt)
        if self.service_s - self._last_log >= LOG_INTERVAL_S:
            self.log.add(self.service_s / S_PER_DAY, self.dd_base, self.plug_base, self.cum["choke_kg"], self.cum["liquid_sm3"])
            self._last_log = self.service_s
        if self.service_s - getattr(self, "_last_cv", -math.inf) >= self.CV_TRACK_S:
            self._last_cv = self.service_s
            self._cv_tracking()

    def _update_rates_only(self) -> None:
        op = self.operating_point()
        if op is None:
            return
        self.last_op = op
        self.last_source = self.sand_source(op)
        prod = self.last_source["produced_kg_s"] or 0.0
        m_choke = (op.sand_frac_choke * max(op.w_choke, 0.0)) if op.sand_frac_choke is not None else prod
        dd, plug, b, o = self.dd_base.copy(), self.plug_base, self.body_loss, self.outlet_loss
        self.rates = self._erode(op, m_choke, 0.0)
        self.dd_base, self.plug_base, self.body_loss, self.outlet_loss = dd, plug, b, o

    # ---------------------------------------------------------- detector
    def _detector(self, m_true: float, v: float, dt: float) -> None:
        d = self.inputs.detector
        status = "OK"
        reading = m_true * self.det_bias + self.rng.normal(0.0, d.noise_floor_g_s / 1000.0)
        if d.detector_type == "acoustic_non_intrusive" and v < d.min_velocity_m_s:
            status = "LOW_VELOCITY"
            reading = None
        elif reading is not None and reading < 2 * d.noise_floor_g_s / 1000.0:
            status = "BELOW_DETECTION"
            reading = 0.0
        if reading is not None:
            reading = min(max(reading, 0.0), d.range_max_g_s / 1000.0)
            if reading >= d.range_max_g_s / 1000.0:
                status = "OVER_RANGE"
            self.cum["detector_meas_kg"] += reading * dt
        self.det = {"reading_kg_s": reading, "true_kg_s": m_true, "status": status, "velocity_m_s": v,
                    "alarm": reading is not None and reading * 1000.0 >= d.alarm_threshold_g_s}

    # -------------------------------------------------------- Cv tracking
    def _cv_tracking(self) -> None:
        """Effective Cv from MEASUREMENTS (MPFM mass flow, choke P transmitters)
        vs the new-trim Cv at the same step: >1 indicates trim wear."""
        e = self.engine
        m = e.mpfm
        ch = self.choke
        if m is None or ch is None or m.reading is None or m.quality == "BAD" or e.dyn is None:
            return
        if e.dyn.max_rate_pa_s > 200.0:  # transient: MPFM (manifold) and choke flows differ
            return
        p1 = e.readings.get(self._pt_tag(ch.from_node) or "")
        p2 = e.readings.get(self._pt_tag(ch.to_node) or "")
        if p1 is None or p2 is None or p1.value is None or p2.value is None:
            return
        bo = e.bo
        op = self.last_op
        s1 = bo.state(p1.value, op.t1, op.gor_choke, op.wc_choke)
        x = float(s1.free_gas_mass_fraction[0])
        rho_l, rho_g = float(s1.rho_l[0]), float(s1.rho_g[0])
        k = bo.params.gas_cp_cv
        nominal = ch.cv_table, ch.wear_factor
        ch.wear_factor = None
        cda0 = ch.capacity_at(ch.actuator.position_pct)
        ch.wear_factor = nominal[1]
        if cda0 <= 0:
            return
        from app.simulation.multiphase.correlations import sachdeva_mass_flow

        w_exp, _, _ = sachdeva_mass_flow(p1.value, p2.value, x, rho_l, rho_g, cda0, k, bo.params.cp_gas_j_kgk, bo.params.cp_water_j_kgk)
        w_exp = float(w_exp)
        w_meas = m.filtered.get("mass_kg_s")
        if not w_meas or w_exp <= 0:
            return
        ratio = w_meas / w_exp
        u_mass = (m.uncertainty or {}).get("mass_kg_s", 5.0)
        u = math.hypot(u_mass, 2.0)  # + 1 % (1 sigma) PVT / transmitter allowance, k = 2
        day = self.service_s / S_PER_DAY
        if not self.cv_track or day - self.cv_track[-1]["service_days"] >= self.CV_TRACK_S / S_PER_DAY - 1e-9:
            self.cv_track.append({"service_days": day, "ratio": ratio, "uncertainty_pct": u, "step": ch.actuator.position_pct})

    def _pt_tag(self, node: str) -> str | None:
        """Pressure transmitter measuring at a node (first one configured)."""
        return next((i.tag for i in self.engine.instruments if i.type == "pressure" and i.node == node), None)

    # ======================================================== fast-forward
    def fast_forward(self, days: float) -> None:
        """Quasi-steady integration of wear and cumulative sand / production
        at the CURRENT operating point (training: months of service in seconds)."""
        for _ in self.fast_forward_steps(days):
            pass

    def fast_forward_steps(self, days: float):
        """Generator form of ``fast_forward``: one integration step (<= 1 day)
        per ``next()``, yielding the days done. The operating point is frozen
        at the start, so interleaving with the live simulation (background
        job) gives the same result. Closing the generator early keeps the
        days already integrated."""
        op = self.last_op or self.operating_point()
        if op is None:
            return
        src = self.sand_source(op)
        prod = src["produced_kg_s"] or 0.0
        form = src["formation_kg_s"] or 0.0
        m_choke = (op.sand_frac_choke * max(op.w_choke, 0.0)) if op.sand_frac_choke is not None else prod
        q_liq = src["q_liquid_sc_m3s"]
        n = max(1, int(math.ceil(days)))
        dt = days * S_PER_DAY / n
        for _ in range(n):
            self._erode(op, m_choke, dt)
            self.service_s += dt
            self.cum["formation_kg"] += form * dt
            self.cum["produced_kg"] += prod * dt
            self.cum["retained_kg"] += max(form - prod, 0.0) * dt
            self.cum["choke_kg"] += m_choke * dt
            self.cum["liquid_sm3"] += q_liq * dt
            self.cum["oil_sm3"] += q_liq * (1 - op.wc) * dt
            self.cum["water_sm3"] += q_liq * op.wc * dt
            self.cum["gas_sm3"] += q_liq * (1 - op.wc) * op.gor * dt
            self.log.add(self.service_s / S_PER_DAY, self.dd_base, self.plug_base, self.cum["choke_kg"], self.cum["liquid_sm3"])
            self._last_log = self.service_s
            yield dt / S_PER_DAY
        self._update_rates_only()

    # ============================================================ reporting
    def _criteria(self) -> list[dict]:
        a = self.inputs.acceptance
        r = self.rates
        c_f = self.c_factor
        out = []
        ddc = self.dd_cal()
        if self.geom.valid and self.mat_trim is not None:
            rate_rows = r.get("hole_growth_rate_m_s")
            rate = float(np.max(rate_rows)) * c_f if rate_rows is not None and len(rate_rows) else 0.0
            used = float(ddc.max()) if ddc.size else 0.0
            out.append({"key": "hole", "label": "Cage hole enlargement", "unit": "mm", "used": used * 1e3,
                        "allowance": a.max_hole_diameter_increase_mm, "rate_per_s": rate * 1e3, "calibrated_by_inspection": True})
            ref = self._ref_position()
            cv_inc = (self.geom.wear_factor(ref, ddc) - 1.0) * 100.0
            # rate: Cv increase per second from the current hole-growth rate
            if rate_rows is not None and len(rate_rows):
                ahead = ddc + np.asarray(rate_rows) * c_f * S_PER_DAY
                cv_rate = ((self.geom.wear_factor(ref, ahead) - 1.0) * 100.0 - cv_inc) / S_PER_DAY
            else:
                cv_rate = 0.0
            out.append({"key": "cv", "label": f"Cv increase at {ref:.1f} % opening", "unit": "%", "used": cv_inc,
                        "allowance": a.max_cv_increase_pct, "rate_per_s": cv_rate, "calibrated_by_inspection": True})
        if self.mat_trim is not None and self.inputs.choke.plug_diameter_mm and self.inputs.choke.cage_wall_thickness_mm:
            out.append({"key": "plug", "label": "Plug / seat edge loss", "unit": "mm", "used": self.plug_cal() * 1e3,
                        "allowance": a.max_plug_loss_mm, "rate_per_s": r.get("plug_rate_m_s", 0.0) * c_f * 1e3, "calibrated_by_inspection": True})
        if "body_rate_m_s" in r:
            out.append({"key": "body", "label": "Body / gallery wall loss (screening)", "unit": "mm", "used": self.body_loss * 1e3,
                        "allowance": a.max_body_wall_loss_mm, "rate_per_s": r["body_rate_m_s"] * 1e3, "calibrated_by_inspection": False})
        if "outlet_rate_m_s" in r:
            out.append({"key": "outlet", "label": "Choke outlet wall loss (DNV straight pipe)", "unit": "mm", "used": self.outlet_loss * 1e3,
                        "allowance": a.max_outlet_wall_loss_mm, "rate_per_s": r["outlet_rate_m_s"] * 1e3, "calibrated_by_inspection": False})
        return out

    def _sigma_total(self, calibrated: bool) -> tuple[float, dict]:
        inp = self.inputs
        s_k = self.sigma_c if calibrated else SIGMA_K_PRIOR
        s_sand = (self.sand_eff.measured_uncertainty_pct / 100.0) if self.sand_eff.mode == "measured" else SIGMA_SAND_PREDICTED
        n = self.mat_trim.n if self.mat_trim else 2.6
        s_u = n * 0.05  # 5 % (1 sigma) on the jet velocity
        tot = math.sqrt(s_k**2 + s_sand**2 + s_u**2)
        return tot, {"erosion model (K, geometry)": s_k, "sand rate": s_sand, "particle velocity": s_u}

    def measured_history(self) -> dict:
        p = self.engine.bo.params
        return smeas.report(self.inputs.sand, p.rho_oil_sc, p.rho_water_sc, p.rho_gas_sc, p.gor_sm3_sm3)

    def erosional_velocity(self) -> dict:
        """API RP 14E erosional-velocity screening at the gallery, the choke
        outlet bore and the flowline (no-slip mixture velocity and density)."""
        inp = self.inputs.erosional_velocity
        v = (self.rates or {}).get("velocities")
        op = self.last_op
        if not v and op is not None and self.engine.bo is not None and self.choke is not None:
            v = self._velocities(op)  # needs only the flow, not the erosion inputs
        if not v:
            return {"available": False, "reason": "needs a flowing three-phase operating point at the choke"}
        rows = []
        for key, label, u, rho, need in (
            ("gallery", "Body gallery (upstream of the cage)", v.get("u_gallery"), v["rho_mix_up"], "gallery diameter"),
            ("outlet", "Choke outlet bore", v.get("u_outlet"), v["rho_mix_dn"], "choke outlet bore"),
            ("flowline", "Flowline", v.get("u_flowline"), v["rho_mix_dn"], None),
        ):
            if u is None:
                rows.append({"key": key, "label": label, "available": False, "missing": need})
                continue
            ve = er.api14e_erosional_velocity(rho, inp.c_factor)
            rows.append({"key": key, "label": label, "available": True, "u_mix_m_s": u, "rho_mix_kg_m3": rho,
                         "ve_m_s": ve, "ratio": u / ve, "exceeded": u > ve})
        sand = (self.rates or {}).get("m_sand_choke", 0.0) > 0
        notes = ["Supplementary screening only: API RP 14E is an empirical velocity limit for clean service. It is NOT a "
                 "sand-erosion model and NOT a choke-geometry model - the DNV-RP-O501 results above govern."]
        if sand:
            notes.append("Sand is present: API RP 14E itself says C must be reduced for solids-laden flow, so 'below Ve' does "
                         "not mean erosion-free here.")
        return {"available": True, "status": "Correlation-based screening (supplementary)", "c_factor": inp.c_factor,
                "c_source": inp.c_source, "method": "Ve = C / sqrt(rho_m) (API RP 14E; ft/s, lb/ft3), no-slip mixture density "
                "and velocity at each location", "locations": rows, "sand_present": sand,
                "any_exceeded": any(r.get("exceeded") for r in rows), "notes": notes}

    def cavitation(self, op: OperatingPoint | None = None) -> dict:
        """Cavitation / flashing screening at the current choke operating point."""
        op = op or self.last_op or self.operating_point()
        bo = self.engine.bo
        if op is None or bo is None:
            return {"available": False, "reason": "needs a flowing three-phase (black-oil) operating point at the choke"}
        p = bo.params
        st = bo.state(op.p1, op.t1, op.gor_choke, op.wc_choke)
        pt = cav.CavitationPoint(p1=op.p1, p2=op.p2, t1=op.t1, opening_pct=op.position_pct,
                                 pb_correlation=float(bubble_point(op.gor_choke, op.t1, p.api, p.gas_sg)),
                                 gvf_inlet=float(st.gvf[0]), water_cut=op.wc_choke)
        return cav.screen(pt, self.inputs.cavitation)

    def snapshot(self) -> dict:
        inp = self.inputs
        op = self.last_op
        src = getattr(self, "last_source", None)
        r = self.rates
        crit = self._criteria()
        m_c = r.get("m_sand_choke", 0.0) if r else 0.0
        q_liq = src["q_liquid_sc_m3s"] if src else 0.0
        days = self.service_s / S_PER_DAY
        n_cal = sum(1 for p in self.calibration_points if p["used"])
        for c in crit:
            sig, _ = self._sigma_total(c["calibrated_by_inspection"] and n_cal > 0)
            c["consumed"] = (c["used"] / c["allowance"]) if c["allowance"] else None
            rate = c["rate_per_s"]
            if c["allowance"] and rate > 0:
                rem = max(c["allowance"] - c["used"], 0.0)
                p50 = rem / rate / S_PER_DAY
                c["life_days"] = {"p10": p50 * math.exp(-Z90 * sig), "p50": p50, "p90": p50 * math.exp(Z90 * sig)}
                c["life_sand_kg"] = rem / (rate / m_c) if m_c > 0 else None
                c["life_liquid_sm3"] = rem / (rate / q_liq) if q_liq > 0 else None
                c["rate_per_year"] = rate * S_PER_YEAR
            else:
                c["life_days"] = None
                c["life_sand_kg"] = None
                c["life_liquid_sm3"] = None
                c["rate_per_year"] = rate * S_PER_YEAR
            c["sigma_ln"] = sig
        with_allow = [c for c in crit if c["consumed"] is not None]
        gov = max(with_allow, key=lambda c: c["consumed"]) if with_allow else None
        lives = [c for c in crit if c["life_days"]]
        first = min(lives, key=lambda c: c["life_days"]["p50"]) if lives else None
        health = self._health(crit, gov)
        conf = self._confidence(n_cal)
        rec = self._recommendation(health, gov, first, conf)
        onset = src["onset"] if src else None
        return {
            "available": self.choke is not None,
            "service_days": days,
            "inputs_status": self.input_status(),
            "cavitation": self.cavitation(op),
            "erosional_velocity": self.erosional_velocity(),
            "measured_history": self.measured_history(),
            "sand": None if not src else {
                "mode": src["mode"],
                "formation_kg_d": None if src["formation_kg_s"] is None else src["formation_kg_s"] * S_PER_DAY,
                "produced_kg_d": None if src["produced_kg_s"] is None else src["produced_kg_s"] * S_PER_DAY,
                "at_choke_kg_d": m_c * S_PER_DAY,
                "missing": sorted(set(src["missing"])), "assumed": src["assumed"],
                "onset": None if onset is None else {
                    "available": onset.available, "missing": onset.missing, "assumed": onset.assumed,
                    "critical_drawdown_bar": None if onset.critical_drawdown_pa is None else onset.critical_drawdown_pa / 1e5,
                    "critical_bhfp_bara": None if onset.cbhfp_pa is None else onset.cbhfp_pa / 1e5,
                    "drawdown_bar": None if onset.drawdown_pa is None else onset.drawdown_pa / 1e5,
                    "risk_index": onset.risk_index if onset.risk_index is None or math.isfinite(onset.risk_index) else 99.0,
                    "sigma_v_bar": None if onset.sigma_v_pa is None else onset.sigma_v_pa / 1e5,
                    "sigma_h_bar": None if onset.sigma_h_pa is None else onset.sigma_h_pa / 1e5,
                    "effective_strength_bar": None if onset.strength_pa is None else onset.strength_pa / 1e5,
                    "notes": onset.notes},
                "screen": {"available": self.screen.available, "passing_fraction": self.screen.passing_fraction,
                           "produced_d50_um": None if self.screen.produced_d50_m is None else self.screen.produced_d50_m * 1e6,
                           "missing": self.screen.missing, "notes": self.screen.notes},
                "psd": None if self.psd is None else {"d50_um": math.exp(self.psd.mu) * 1e6, "sigma_ln": self.psd.sigma},
            },
            "detector": {"tag": inp.detector.tag, "type": inp.detector.detector_type, "status": self.det["status"],
                         "reading_g_s": None if self.det.get("reading_kg_s") is None else self.det["reading_kg_s"] * 1000,
                         "true_g_s": None if self.det.get("true_kg_s") is None else self.det["true_kg_s"] * 1000,
                         "alarm": self.det["alarm"], "alarm_threshold_g_s": inp.detector.alarm_threshold_g_s,
                         "velocity_m_s": self.det.get("velocity_m_s"), "cumulative_measured_kg": self.cum["detector_meas_kg"],
                         "uncertainty_pct": 2 * inp.detector.calibration_uncertainty_pct,
                         "location": "choke outlet (downstream of CHK-101)"},
            "transport": self._transport_report(),
            "velocities": None if not r else {k: v for k, v in r["velocities"].items() if not isinstance(v, bool)} | {"critical_flow": r["velocities"]["critical"]},
            "erosion": None if not r else {
                "trim_material": None if self.mat_trim is None else {"key": self.mat_trim.key, "name": self.mat_trim.name, "k": self.mat_trim.k,
                                                                     "n": self.mat_trim.n, "behaviour": self.mat_trim.behaviour, "source": self.mat_trim.source},
                "erosion_ratio_kg_kg": r.get("erosion_ratio"),
                "trim_volume_rate_mm3_d": None if "trim_volume_rate_m3_s" not in r else r["trim_volume_rate_m3_s"] * self.c_factor * 1e9 * S_PER_DAY,
                "rows": [{"axial_position_mm": row.axial_position_mm, "diameter_mm": row.diameter_mm, "count": row.count,
                          "increase_mm": float(self.dd_cal()[i]) * 1e3,
                          "rate_mm_y": float(r.get("hole_growth_rate_m_s", np.zeros(len(self.geom.rows)))[i]) * self.c_factor * 1e3 * S_PER_YEAR
                          if "hole_growth_rate_m_s" in r else None}
                         for i, row in enumerate(self.geom.rows)],
            },
            "criteria": crit,
            "governing": None if gov is None else gov["key"],
            "first_limit": None if first is None else first["key"],
            "health": health,
            "confidence": conf,
            "recommendation": rec,
            "cv_tracking": self._cv_report(),
            "calibration": {"factor_median": self.c_factor, "sigma_ln": self.sigma_c, "points": self.calibration_points,
                            "prior_sigma_ln": SIGMA_K_PRIOR},
            "uncertainty_components": self._sigma_total(n_cal > 0)[1],
            "cumulative": dict(self.cum),
            "wear_history": {"service_days": self.log.service_days[-400:], "max_hole_mm": [float(self.c_factor * (d - self._dd_at_replacement).max()) * 1e3 if d.size else 0.0 for d in self.log.dd[-400:]],
                             "sand_kg": self.log.sand_kg[-400:], "liquid_sm3": self.log.liquid_sm3[-400:]},
            "limitations": [
                "Sanding onset: TWC-based critical drawdown for perforations (worst orientation); rock strength and stresses must be site data.",
                "Post-onset sand rate is EMPIRICAL and must be calibrated - no universal equation exists.",
                "Trim erosion: DNV-RP-O501-type particle erosion with a generic geometry; trim-specific accuracy requires calibration by inspection (or vendor / CFD data).",
                "Particle velocity = jet velocity at the vena contracta; small particles that follow the flow are treated conservatively (no size reduction).",
                "Body / gallery wear is a screening estimate; erosion-corrosion, cavitation and hydrate / scale effects are not modelled.",
                "Sand settling / deposition in the flowline is flagged (screening velocity) but not simulated.",
            ],
        }

    def _transport_report(self) -> dict:
        r = self.rates
        out = {"model": "advected mass fraction on the production transport grid (moves only with the flow)",
               "deposition": []}
        e = self.engine
        if e.dyn is None or e.dyn.mp is None:
            out["model"] = "steady model: sand reaches the choke instantly"
            return out
        rho_s = self.inputs.sand.grain_density_kg_m3
        for p in e.dyn.mp.pipe_report():
            if not p["element"].startswith("FL"):
                continue
            # Durand-type screening velocity for fine sand in the liquid phase
            rho_l = 900.0
            d = self._flowline_d()
            v_crit = 0.6 * math.sqrt(2 * 9.81 * d * max(rho_s / rho_l - 1, 0.1))
            out["deposition"].append({"segment": p["segment"], "v_sl": p["v_sl"], "v_crit": v_crit, "risk": p["v_sl"] < v_crit})
        out["deposition_risk_segments"] = sum(1 for x in out["deposition"] if x["risk"])
        out["deposition_note"] = "Screening only (Durand-type, F_L = 0.6): settling and bed formation are NOT simulated."
        del r
        return out

    def _cv_report(self) -> dict:
        if not self.cv_track:
            return {"available": False, "note": "needs a GOOD MPFM reading, the choke pressure transmitters and a steady process"}
        last = list(self.cv_track)[-12:]
        ratio = float(np.mean([x["ratio"] for x in last]))
        u = float(np.mean([x["uncertainty_pct"] for x in last]))
        dev = (ratio - 1) * 100
        sig = abs(dev) > u
        causes = []
        if dev > u:
            causes = ["trim erosion (cage holes / plug enlarged) - consistent with sand at the choke" if self.cum["choke_kg"] > 0 else
                      "trim erosion - but no sand has reached the choke in the model: check other causes",
                      "MPFM over-reading (check MPFM quality, calibration and PVT)",
                      "choke position error (LVDT / step count) - actual opening larger than indicated",
                      "fluid-property change (GOR / water cut) not in the PVT used"]
        elif dev < -u:
            causes = ["partial plugging (sand / scale / hydrate / wax) - effective area reduced",
                      "MPFM under-reading", "choke position error - actual opening smaller than indicated"]
        return {"available": True, "ratio": ratio, "deviation_pct": dev, "uncertainty_pct": u, "significant": sig,
                "samples": [{"service_days": x["service_days"], "ratio": x["ratio"]} for x in list(self.cv_track)[-200:]],
                "possible_causes": causes,
                "note": "Effective Cv from MEASURED data (MPFM mass flow, choke upstream / downstream transmitters) divided by the new-trim Cv "
                        "at the same step. A sustained rise above the measurement uncertainty indicates trim wear on a plug & cage choke."}

    def _health(self, crit: list[dict], gov: dict | None) -> dict:
        th = self.inputs.thresholds
        reasons = []
        cat = "Normal"
        f = gov["consumed"] if gov else 0.0
        if gov is None:
            cat = "Unavailable"
            reasons.append("no wear criterion can be evaluated: enter trim material, cage geometry and acceptance criteria")
        if f is not None and gov is not None:
            if f >= th.critical:
                cat = "Critical condition"
            elif f >= th.changeout_assessment:
                cat = "Changeout assessment required"
            elif f >= th.inspection_recommended:
                cat = "Inspection recommended"
            elif f >= th.increased_wear:
                cat = "Increased wear"
            reasons.append(f"{gov['label']}: {gov['used']:.3f} of {gov['allowance']:g} {gov['unit']} allowance consumed ({f * 100:.1f} %)")
        hole = next((c for c in crit if c["key"] == "hole"), None)
        if cat in ("Normal",) and hole and hole["rate_per_year"] > th.elevated_rate_mm_y:
            cat = "Elevated erosion risk"
            reasons.append(f"cage-hole growth rate {hole['rate_per_year']:.2f} mm/year exceeds {th.elevated_rate_mm_y:g} mm/year")
        src = getattr(self, "last_source", None)
        if src and src["onset"].available and (src["onset"].risk_index or 0) > 1.0:
            reasons.append(f"drawdown above the critical sanding drawdown (risk index {min(src['onset'].risk_index, 99):.2f})")
            if cat == "Normal":
                cat = "Elevated erosion risk"
        return {"category": cat, "consumed_fraction": f, "reasons": reasons,
                "thresholds": th.model_dump(), "note": "Categories and thresholds are configurable site practice, not universal safety limits."}

    def _confidence(self, n_cal: int) -> dict:
        inp = self.inputs
        factors = []
        if self.mat_trim is None or not self.geom.valid:
            return {"category": "unavailable", "factors": ["trim material and cage geometry are required"]}
        sand_measured = self.sand_eff.mode == "measured" and self.sand_eff.measured_value is not None
        factors.append("sand rate MEASURED" if sand_measured else "sand rate PREDICTED (empirical, needs calibration)")
        factors.append(f"trim erosion model calibrated by {n_cal} inspection(s)" if n_cal else "trim erosion model NOT calibrated by inspection")
        if self.mat_trim.source.startswith("DNV"):
            factors.append("material constants from the DNV-RP-O501 table - verify grade with the vendor")
        if n_cal >= 2 and all(0.7 < (p["ratio"] or 0) / self.c_factor < 1.43 for p in self.calibration_points if p["used"]):
            cat = "validated (site-calibrated, consistent inspections)"
        elif n_cal >= 1:
            cat = "calibrated estimate"
        elif sand_measured:
            cat = "engineering estimate (uncalibrated erosion model)"
        else:
            cat = "screening estimate"
        return {"category": cat, "factors": factors}

    def _recommendation(self, health: dict, gov: dict | None, first: dict | None, conf: dict) -> dict:
        cat = health["category"]
        title = {
            "Normal": "No action required - continue monitoring",
            "Elevated erosion risk": "Elevated erosion risk - review operating conditions",
            "Increased wear": "Increased wear - plan an inspection window",
            "Inspection recommended": "Inspection assessment recommended",
            "Changeout assessment required": "Changeout assessment required",
            "Critical condition": "Critical condition - immediate engineering review",
            "Unavailable": "Prediction unavailable - complete the inputs",
        }[cat]
        why = list(health["reasons"])
        r = self.rates
        if r and r.get("velocities"):
            v = r["velocities"]
            why.append(f"choke jet velocity {v['u_jet']:.1f} m/s{' (critical flow)' if v['critical'] else ''}; sand at the choke "
                       f"{r.get('m_sand_choke', 0.0) * S_PER_DAY:.2f} kg/d")
        if first and first.get("life_days"):
            ld = first["life_days"]
            why.append(f"first limit: {first['label']} in {ld['p50']:.0f} days (P10 {ld['p10']:.0f} - P90 {ld['p90']:.0f} days) "
                       "at the CURRENT conditions; the rate changes with sand rate, opening and differential")
        cvt = self._cv_report()
        if cvt.get("available"):
            why.append(f"measured Cv tracking: {cvt['deviation_pct']:+.1f} % (uncertainty +/- {cvt['uncertainty_pct']:.1f} %) - "
                       + ("SIGNIFICANT" if cvt["significant"] else "not significant"))
        actions = {
            "Normal": ["continue monitoring sand and Cv tracking"],
            "Elevated erosion risk": ["consider reducing drawdown / choke differential", "confirm the sand rate with SDT-101 or a sand trap"],
            "Increased wear": ["schedule an inspection opportunity", "trend Cv tracking", "review vendor erosion limits"],
            "Inspection recommended": ["plan inspection of cage holes and plug", "review vendor limits and inspection evidence",
                                       "record the inspection to calibrate the model"],
            "Changeout assessment required": ["prepare trim changeout", "reduce differential / sand exposure until replaced"],
            "Critical condition": ["engineering review now: risk of loss of choke control or seat leakage",
                                   "consider shut-in / reduced rate per site procedure"],
            "Unavailable": ["enter the missing inputs listed on the Sand & choke inputs page"],
        }[cat]
        text = f"{title}. " + " ".join(s[0].upper() + s[1:] + "." for s in why[:3]) + f" Confidence: {conf['category']}."
        return {"title": title, "text": text, "reasons": why, "actions": actions,
                "disclaimer": "Decision support only - not an automatic changeout instruction. Review vendor limits and inspection evidence."}

    def input_status(self) -> dict:
        inp = self.inputs
        g, c, s, ch, a = inp.geomechanics, inp.completion, self.sand_eff, inp.choke, inp.acceptance

        def sect(req: list[tuple[str, object]]) -> dict:
            miss = [n for n, v in req if v in (None, [], "")]
            return {"complete": not miss, "missing": miss}

        strength = g.twc_strength_mpa or (g.ucs_mpa and g.twc_ucs_ratio)
        return {
            "geomechanics": sect([("depth", g.depth_tvd_m), ("overburden gradient", g.overburden_gradient_bar_m),
                                  ("min horizontal stress gradient", g.min_horizontal_stress_gradient_bar_m), ("rock strength (TWC or UCS + ratio)", strength),
                                  ("initial reservoir pressure", g.initial_reservoir_pressure_bara)]),
            "completion": sect([("screen aperture", c.screen_aperture_um if c.completion_type.endswith("screens") else 1)]),
            "sand": sect([("PSD D50", s.d50_um), ("PSD D10 or D90", s.d10_um or s.d90_um)]
                         + ([("measured sand value", s.measured_value)] if s.mode == "measured" else [("sand-rate coefficient (calibrated)", s.rate_coefficient_kg_m3)])),
            "choke": sect([("max Cv", ch.max_cv), ("actuator steps", ch.actuator_steps), ("trim material", ch.trim_material),
                           ("stroke", ch.stroke_mm), ("cage wall thickness", ch.cage_wall_thickness_mm), ("cage hole rows", ch.hole_rows),
                           ("plug diameter", ch.plug_diameter_mm), ("outlet bore", ch.choke_outlet_bore_mm)]),
            "acceptance": sect([("max hole increase or max Cv increase", a.max_hole_diameter_increase_mm or a.max_cv_increase_pct)]),
        }


__all__ = ["SandChokeSystem"]
