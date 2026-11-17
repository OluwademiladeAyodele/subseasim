"""Virtual multiphase flow meter (MPFM) - representative venturi + dual-energy
gamma meter.

NOT a reproduction of any manufacturer's proprietary measurement method. It
is a documented, generic implementation of the two principles most commonly
combined in commercial MPFMs (see docs/MPFM_MEASUREMENT_MODEL.md):

1. SENSORS (simulated from the TRUE process state at the meter location)
   - venturi differential pressure from the slip (momentum) density:
         dP = (W / (C_d A_t))^2 (1 - beta^4) / (2 rho_mom)
         rho_mom = [x^2 / (alpha rho_g) + (1 - x)^2 / ((1 - alpha) rho_l)]^-1
     with the in-situ gas fraction alpha from the Chisholm slip ratio
     S = (rho_l / rho_g)^(1/4);
   - dual-energy gamma transmission: attenuation at a low and a high photon
     energy, A_E = d sum(alpha_i mu_i,E rho_i), counted with Poisson
     statistics N = N0 t exp(-A); the low-energy water attenuation depends
     on salinity;
   - pressure and temperature transmitters with noise.
2. FLOW COMPUTER (uses only the measured signals and its OWN configuration)
   - phase fractions from the 3 x 3 system [low energy; high energy;
     alpha_o + alpha_w + alpha_g = 1] with the meter's attenuation
     coefficients and PVT densities;
   - total mass flow from the venturi with the meter's slip model
     (Chisholm or homogeneous);
   - phase volumes at line conditions, then standard conditions with the
     meter's black-oil PVT (Bo, Rs, Bg, Bw).
3. UNCERTAINTY: first-order (GUM) propagation of the input uncertainties
   through the flow computer, plus a slip / flow-regime model term that
   grows with GVF, expanded with k = 2.

Sand is NOT given any effect on the readings: the representative model has
no physically supported sand mechanism (documented).
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field

import numpy as np

from app.models.scenario import MPFMConfig
from app.simulation.fluid_properties.black_oil import BlackOilFluid, BlackOilParams

S_PER_DAY = 86_400.0
#: The uncertainty propagation (7 flow-computer evaluations) is refreshed at
#: most this often in simulated time, or at once after a quality change,
#: fault or calibration: it changes only as the operating point drifts.
UNCERTAINTY_REFRESH_S = 30.0

#: Representative mass attenuation coefficients [m2/kg] (= cm2/g x 0.1),
#: approximate values from NIST XCOM for a Ba-133-type source: ~32 keV
#: (low, photo-electric sensitive) and ~356 keV (high, Compton dominated).
MU_LOW = {"oil": 0.0245, "gas": 0.0255, "water": 0.0350, "nacl": 0.330}
MU_HIGH = {"oil": 0.0113, "gas": 0.0118, "water": 0.0111, "nacl": 0.0097}


def water_mu(salinity_wt_pct: float) -> tuple[float, float]:
    w = salinity_wt_pct / 100.0
    return ((1 - w) * MU_LOW["water"] + w * MU_LOW["nacl"], (1 - w) * MU_HIGH["water"] + w * MU_HIGH["nacl"])


def chisholm_slip(rho_l, rho_g):
    return max(1.0, (rho_l / max(rho_g, 1e-6)) ** 0.25)


def void_fraction(x: float, rho_l: float, rho_g: float, s: float) -> float:
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    return 1.0 / (1.0 + s * (1 - x) / x * rho_g / rho_l)


def quality_from_void(alpha: float, rho_l: float, rho_g: float, s: float) -> float:
    if alpha <= 0:
        return 0.0
    if alpha >= 1:
        return 1.0
    return 1.0 / (1.0 + (1.0 / alpha - 1.0) * rho_l / (s * rho_g))


def momentum_density(x: float, alpha: float, rho_l: float, rho_g: float) -> float:
    if x <= 0 or alpha <= 0:
        return rho_l
    if x >= 1 or alpha >= 1:
        return rho_g
    return 1.0 / (x * x / (alpha * rho_g) + (1 - x) ** 2 / ((1 - alpha) * rho_l))


@dataclass
class MPFMFaults:
    dp_offset_bar: float = 0.0
    dp_stuck: bool = False
    gamma_failed: bool = False
    pt_failed: bool = False


@dataclass
class Truth:
    p: float
    t: float
    w: float  # kg/s
    gor: float
    wc: float
    q_oil: float  # m3/s line conditions
    q_gas: float
    q_water: float
    oil_sc: float  # Sm3/s
    gas_sc: float
    water_sc: float
    gvf: float  # no-slip volumetric gas fraction
    alpha: float  # in-situ gas void fraction (slip)
    dp: float  # venturi dP [Pa]
    a_low: float  # attenuation (dimensionless)
    a_high: float
    rho_mix: float = 0.0  # local in-situ (slip) mixture density [kg/m3]


@dataclass
class MeterReading:
    q_oil: float
    q_gas: float
    q_water: float
    oil_sc: float
    gas_sc: float
    water_sc: float
    w: float
    rho_mix: float
    alpha: tuple[float, float, float]  # oil, gas, water (in-situ)
    alpha_raw: tuple[float, float, float]


class MPFM:
    def __init__(self, cfg: MPFMConfig, fluid: BlackOilFluid, gor: float, wc: float):
        self.cfg = cfg
        self.true_fluid = fluid
        mp = cfg.meter_pvt
        p = fluid.params
        self.meter_params = BlackOilParams(
            f"{cfg.tag} meter PVT", mp.oil_api or p.api, mp.gas_specific_gravity or p.gas_sg,
            mp.producing_gor_sm3_sm3 if mp.producing_gor_sm3_sm3 is not None else gor,
            mp.water_cut_fraction if mp.water_cut_fraction is not None else wc,
            mp.water_salinity_wt_pct if mp.water_salinity_wt_pct is not None else p.water_salinity_wt_pct,
            p.cp_oil_j_kgk, p.cp_gas_j_kgk, p.cp_water_j_kgk, p.gas_cp_cv)
        self.meter_fluid = BlackOilFluid(self.meter_params)
        self.d1 = cfg.inlet_diameter_m
        self.dt = cfg.inlet_diameter_m * cfg.beta
        self.at = math.pi * self.dt**2 / 4
        self.e = 1.0 - cfg.beta**4
        self.rng = np.random.default_rng(cfg.seed)
        self.faults = MPFMFaults()
        self.cal_time_s = 0.0
        self.cd_true = cfg.discharge_coefficient
        self.last_update = -math.inf
        self.truth: Truth | None = None
        self.reading: MeterReading | None = None
        self.filtered: dict[str, float] = {}
        self.uncertainty: dict[str, float] = {}
        self.quality = "NOT_READY"
        self.flags: list[dict] = []
        self.dp_hist: deque[float] = deque(maxlen=30)
        self.dp_stuck_value: float | None = None
        self.last_pt: tuple[float, float] | None = None
        self.meas_inputs: dict[str, float] = {}
        self._last_prop = -math.inf
        self._prop_dirty = True

    # -------------------------------------------------------------- truth
    def true_state(self, p: float, t: float, w: float, gor: float, wc: float) -> Truth:
        f = self.true_fluid
        s = f.state(p, t, gor, wc)
        w = max(w, 0.0)
        q_liq = w / float(f.mass_per_liquid_sc(gor, wc))
        q_o, q_g, q_w = q_liq * float(s.vol_o[0]), q_liq * float(s.vol_g[0]), q_liq * float(s.vol_w[0])
        m_g = q_liq * float(s.mass_g[0])
        x = m_g / w if w > 0 else float(s.free_gas_mass_fraction[0])
        rho_l, rho_g = float(s.rho_l[0]), float(s.rho_g[0])
        slip = chisholm_slip(rho_l, rho_g)
        alpha = void_fraction(x, rho_l, rho_g, slip)
        rho_mom = momentum_density(x, alpha, rho_l, rho_g)
        dp = (w / (self.cd_true * self.at)) ** 2 * self.e / (2 * rho_mom) if w > 0 else 0.0
        # liquid split by volume in the liquid phase
        ql = q_o + q_w
        fo = q_o / ql if ql > 0 else (1 - wc)
        a_o, a_w = (1 - alpha) * fo, (1 - alpha) * (1 - fo)
        mu_wl, mu_wh = water_mu(f.params.water_salinity_wt_pct)
        rho_o, rho_w = float(s.rho_o[0]), float(s.rho_w[0])
        a_low = self.dt * (a_o * MU_LOW["oil"] * rho_o + alpha * MU_LOW["gas"] * rho_g + a_w * mu_wl * rho_w)
        a_high = self.dt * (a_o * MU_HIGH["oil"] * rho_o + alpha * MU_HIGH["gas"] * rho_g + a_w * mu_wh * rho_w)
        tot = q_o + q_g + q_w
        return Truth(p, t, w, gor, wc, q_o, q_g, q_w, (1 - wc) * q_liq, gor * (1 - wc) * q_liq, wc * q_liq,
                     q_g / tot if tot > 0 else float(s.gvf[0]), alpha, dp, a_low, a_high,
                     # in-situ (slip) mixture density - what a gamma densitometer sees
                     a_o * rho_o + alpha * rho_g + a_w * rho_w)

    # ------------------------------------------------------- flow computer
    def compute(self, p: float, t: float, dp: float, a_low: float, a_high: float, pvt_scale: float = 1.0,
                cd: float | None = None, slip_scale: float = 1.0) -> MeterReading:
        """Flow-computer calculation from measured signals (no access to the truth)."""
        mf = self.meter_fluid
        s = mf.state(p, t)
        rho_o, rho_g, rho_w = float(s.rho_o[0]) * pvt_scale, float(s.rho_g[0]) * pvt_scale, float(s.rho_w[0]) * pvt_scale
        mu_wl, mu_wh = water_mu(self.meter_params.water_salinity_wt_pct)
        A = np.array([[MU_LOW["oil"] * rho_o, MU_LOW["gas"] * rho_g, mu_wl * rho_w],
                      [MU_HIGH["oil"] * rho_o, MU_HIGH["gas"] * rho_g, mu_wh * rho_w],
                      [1.0, 1.0, 1.0]])
        b = np.array([a_low / self.dt, a_high / self.dt, 1.0])
        raw = np.linalg.solve(A, b)
        a = np.clip(raw, 0.0, 1.0)
        a = a / a.sum() if a.sum() > 0 else np.array([1.0, 0.0, 0.0])
        a_o, a_g, a_w = (float(v) for v in a)
        rho_l = (a_o * rho_o + a_w * rho_w) / max(a_o + a_w, 1e-12) if a_o + a_w > 0 else rho_o
        cd = cd if cd is not None else self.cfg.discharge_coefficient
        if self.cfg.meter_slip_model == "chisholm":
            slip = 1.0 + (chisholm_slip(rho_l, rho_g) - 1.0) * slip_scale
            x = quality_from_void(a_g, rho_l, rho_g, slip)
            rho_mom = momentum_density(x, a_g, rho_l, rho_g)
        else:
            x = None
            rho_mom = a_o * rho_o + a_g * rho_g + a_w * rho_w
        w = cd * self.at * math.sqrt(max(2.0 * rho_mom * max(dp, 0.0) / self.e, 0.0))
        rho_mix = a_o * rho_o + a_g * rho_g + a_w * rho_w
        if x is None:  # homogeneous: flowing fractions = in-situ fractions
            q_tot = w / rho_mix if rho_mix > 0 else 0.0
            q_o, q_g, q_w = a_o * q_tot, a_g * q_tot, a_w * q_tot
        else:
            q_g = x * w / rho_g if rho_g > 0 else 0.0
            q_l = (1 - x) * w / rho_l if rho_l > 0 else 0.0
            fo = a_o / (a_o + a_w) if a_o + a_w > 0 else 1.0
            q_o, q_w = q_l * fo, q_l * (1 - fo)
        bo, bg, bw, rs = float(s.bo[0]), float(s.bg[0]), float(s.bw[0]), float(s.rs[0])
        oil_sc = q_o / bo
        return MeterReading(q_o, q_g, q_w, oil_sc, q_g / bg + rs * oil_sc, q_w / bw, w, rho_mix, (a_o, a_g, a_w),
                            tuple(float(v) for v in raw))  # type: ignore[arg-type]

    @staticmethod
    def derived(r: MeterReading) -> dict[str, float]:
        liq = r.oil_sc + r.water_sc
        tot = r.q_oil + r.q_gas + r.q_water
        return {
            "oil_sm3_d": r.oil_sc * S_PER_DAY, "gas_sm3_d": r.gas_sc * S_PER_DAY, "water_sm3_d": r.water_sc * S_PER_DAY,
            "liquid_sm3_d": liq * S_PER_DAY,
            "oil_m3_d": r.q_oil * S_PER_DAY, "gas_m3_d": r.q_gas * S_PER_DAY, "water_m3_d": r.q_water * S_PER_DAY,
            "liquid_m3_d": (r.q_oil + r.q_water) * S_PER_DAY,
            "mass_kg_s": r.w, "mixture_density_kg_m3": r.rho_mix,
            "water_cut": r.water_sc / liq if liq > 0 else 0.0,
            "gor_sm3_sm3": r.gas_sc / r.oil_sc if r.oil_sc > 1e-12 else 0.0,
            "gvf": r.q_gas / tot if tot > 0 else 0.0, "lvf": (r.q_oil + r.q_water) / tot if tot > 0 else 0.0,
        }

    def truth_derived(self, tr: Truth) -> dict[str, float]:
        liq = tr.oil_sc + tr.water_sc
        tot = tr.q_oil + tr.q_gas + tr.q_water
        return {
            "oil_sm3_d": tr.oil_sc * S_PER_DAY, "gas_sm3_d": tr.gas_sc * S_PER_DAY, "water_sm3_d": tr.water_sc * S_PER_DAY,
            "liquid_sm3_d": liq * S_PER_DAY,
            "oil_m3_d": tr.q_oil * S_PER_DAY, "gas_m3_d": tr.q_gas * S_PER_DAY, "water_m3_d": tr.q_water * S_PER_DAY,
            "liquid_m3_d": (tr.q_oil + tr.q_water) * S_PER_DAY, "mass_kg_s": tr.w,
            "mixture_density_kg_m3": tr.rho_mix,
            "water_cut": tr.water_sc / liq if liq > 0 else tr.wc, "gor_sm3_sm3": tr.gor,
            "gvf": tr.gvf, "lvf": 1 - tr.gvf,
        }

    # ---------------------------------------------------------- uncertainty
    def _slip_sigma(self, gvf: float) -> float:
        tab = sorted(self.cfg.slip_uncertainty_table)
        g = [a for a, _ in tab]
        v = [b for _, b in tab]
        return float(np.interp(gvf, g, v)) / 100.0

    def propagate(self, p: float, t: float, dp: float, a_low: float, a_high: float) -> dict[str, float]:
        """Expanded (k = 2) relative uncertainty of each output [%]."""
        c = self.cfg
        base = self.derived(self.compute(p, t, dp, a_low, a_high))
        keys = ("oil_sm3_d", "gas_sm3_d", "water_sm3_d", "liquid_sm3_d", "mass_kg_s")
        sig_dp = math.hypot(c.dp_sigma_pct_full_scale / 100 * c.dp_max_bar * 1e5, 0.0025 * dp)
        n_low = c.gamma_count_rate_low_cps * c.integration_time_s * math.exp(-a_low)
        n_high = c.gamma_count_rate_high_cps * c.integration_time_s * math.exp(-a_high)
        inputs = [
            ("dp", sig_dp, lambda d: self.compute(p, t, dp + d, a_low, a_high)),
            ("gamma_low", 1 / math.sqrt(max(n_low, 1.0)), lambda d: self.compute(p, t, dp, a_low + d, a_high)),
            ("gamma_high", 1 / math.sqrt(max(n_high, 1.0)), lambda d: self.compute(p, t, dp, a_low, a_high + d)),
            ("pressure", c.pressure_sigma_bar * 1e5, lambda d: self.compute(p + d, t, dp, a_low, a_high)),
            ("pvt", c.pvt_uncertainty_pct / 100, lambda d: self.compute(p, t, dp, a_low, a_high, pvt_scale=1 + d)),
            ("cd", c.cd_uncertainty_pct / 100, lambda d: self.compute(p, t, dp, a_low, a_high, cd=c.discharge_coefficient * (1 + d))),
        ]
        var = {k: 0.0 for k in keys}
        budget: dict[str, dict[str, float]] = {k: {} for k in keys}
        for name, sig, fn in inputs:
            if sig <= 0:
                continue
            try:
                pert = self.derived(fn(sig))
            except np.linalg.LinAlgError:
                continue
            for k in keys:
                if abs(base[k]) > 1e-12:
                    rel = (pert[k] - base[k]) / base[k]
                    var[k] += rel * rel
                    budget[k][name] = abs(rel) * 100
        slip = self._slip_sigma(base["gvf"])
        for k in keys:
            var[k] += slip * slip
            budget[k]["slip / flow regime"] = slip * 100
        out = {k: 2.0 * math.sqrt(var[k]) * 100 for k in keys}
        # water cut: absolute uncertainty (percentage points), from the gamma inputs
        wc0 = base["water_cut"]
        wcv = 0.0
        for name, sig, fn in inputs[1:3] + inputs[4:5]:
            try:
                wcv += (self.derived(fn(sig))["water_cut"] - wc0) ** 2
            except np.linalg.LinAlgError:
                pass
        out["water_cut_abs_pct"] = 2.0 * math.sqrt(wcv) * 100
        out["gvf"] = base["gvf"]
        self.budget = budget
        return out

    # ---------------------------------------------------------------- step
    def due(self, t: float) -> bool:
        return t - self.last_update >= self.cfg.update_interval_s - 1e-9

    def update(self, t_now: float, p: float, t: float, w: float, gor: float, wc: float) -> list[tuple[str, str]]:
        """One meter update from the true local state. Returns (old, new)
        quality transitions for the event log."""
        c = self.cfg
        dt = t_now - self.last_update if math.isfinite(self.last_update) else c.update_interval_s
        self.last_update = t_now
        # real Cd drifts with time since the last calibration
        self.cd_true = c.discharge_coefficient * (1 + c.cd_drift_pct_per_year / 100 * (t_now - self.cal_time_s) / (365.25 * S_PER_DAY))
        tr = self.true_state(p, t, w, gor, wc)
        self.truth = tr
        flags: list[dict] = []
        f = self.faults
        # --- sensors
        if f.pt_failed:
            if self.last_pt is None:
                p_m, t_m = p, t
            else:
                p_m, t_m = self.last_pt
            flags.append({"severity": "warning", "code": "PT_FAILED", "message": "Meter P/T transmitter failed: last good P and T are used for PVT."})
        else:
            p_m = p + self.rng.normal(0, c.pressure_sigma_bar * 1e5)
            t_m = t + self.rng.normal(0, c.temperature_sigma_k)
            self.last_pt = (p_m, t_m)
        dp_m = tr.dp + self.rng.normal(0, c.dp_sigma_pct_full_scale / 100 * c.dp_max_bar * 1e5) + f.dp_offset_bar * 1e5
        if f.dp_stuck:
            if self.dp_stuck_value is None:
                self.dp_stuck_value = self.dp_hist[-1] if self.dp_hist else dp_m
            dp_m = self.dp_stuck_value
        else:
            self.dp_stuck_value = None
        self.dp_hist.append(dp_m)

        def counts(a: float, n0: float) -> float:
            n = n0 * c.integration_time_s * math.exp(-a)
            nm = max(self.rng.normal(n, math.sqrt(max(n, 1.0))), 1.0)
            return -math.log(nm / (n0 * c.integration_time_s))

        a_low = counts(tr.a_low, c.gamma_count_rate_low_cps)
        a_high = counts(tr.a_high, c.gamma_count_rate_high_cps)
        self.meas_inputs = {"p_pa": p_m, "t_k": t_m, "dp_pa": dp_m, "a_low": a_low, "a_high": a_high}
        # --- flow computer
        quality = "GOOD"
        reading: MeterReading | None = None
        if f.gamma_failed:
            quality = "BAD"
            flags.append({"severity": "error", "code": "GAMMA_FAILED",
                          "message": "Gamma detector failed: phase fractions unavailable - no phase rates."})
        else:
            try:
                reading = self.compute(p_m, t_m, dp_m, a_low, a_high)
            except np.linalg.LinAlgError:
                quality = "BAD"
                flags.append({"severity": "error", "code": "INVERSION_FAILED", "message": "Phase-fraction inversion singular."})
        dp_bar = dp_m / 1e5
        if reading is not None:
            raw = reading.alpha_raw
            if min(raw) < -0.10 or max(raw) > 1.10:
                quality = "BAD"
                flags.append({"severity": "error", "code": "PHASE_FRACTION_INCONSISTENT",
                              "message": f"Measured phase fractions inconsistent (oil {raw[0]:.2f}, gas {raw[1]:.2f}, water {raw[2]:.2f} "
                                         "before clipping): check gamma calibration / water salinity."})
            elif min(raw) < -0.03 or max(raw) > 1.03:
                quality = "DEGRADED" if quality == "GOOD" else quality
                flags.append({"severity": "warning", "code": "PHASE_FRACTION_CLOSURE",
                              "message": "Phase fractions outside 0-1 before clipping: possible salinity / calibration mismatch."})
            if dp_bar < c.dp_min_bar:
                quality = "DEGRADED" if quality == "GOOD" else quality
                cutoff = dp_bar < 0.2 * c.dp_min_bar
                flags.append({"severity": "warning", "code": "LOW_FLOW_CUTOFF" if cutoff else "LOW_FLOW",
                              "message": f"Venturi dP {dp_bar * 1000:.1f} mbar below the {c.dp_min_bar * 1000:.0f} mbar minimum"
                                         + (": below cut-off, rates reported as zero." if cutoff else ": uncertainty increased.")})
                if cutoff:
                    reading = MeterReading(0, 0, 0, 0, 0, 0, 0, reading.rho_mix, reading.alpha, reading.alpha_raw)
            if dp_bar > c.dp_max_bar:
                quality = "BAD"
                flags.append({"severity": "error", "code": "DP_OVER_RANGE", "message": f"Venturi dP {dp_bar:.2f} bar above the {c.dp_max_bar:g} bar range."})
            gvf = self.derived(reading)["gvf"]
            if gvf > c.gvf_max:
                quality = "DEGRADED" if quality == "GOOD" else quality
                flags.append({"severity": "warning", "code": "GVF_OUT_OF_ENVELOPE",
                              "message": f"GVF {gvf * 100:.1f} % above the {c.gvf_max * 100:.0f} % operating envelope (wet-gas regime)."})
        if len(self.dp_hist) == self.dp_hist.maxlen and np.ptp(np.array(self.dp_hist)) == 0.0:
            quality = "DEGRADED" if quality == "GOOD" else quality
            flags.append({"severity": "warning", "code": "DP_FROZEN",
                          "message": "Venturi dP signal has not changed over the last 30 updates: transmitter stuck / frozen?"})
        if f.pt_failed and quality == "GOOD":
            quality = "DEGRADED"
        days = (t_now - self.cal_time_s) / S_PER_DAY
        if days > c.calibration_interval_days:
            quality = "DEGRADED" if quality == "GOOD" else quality
            flags.append({"severity": "info", "code": "CALIBRATION_DUE",
                          "message": f"{days:.0f} days since calibration (interval {c.calibration_interval_days:.0f} d)."})
        # --- outputs, filtered over the integration time
        if reading is not None and quality != "BAD":
            d = self.derived(reading)
            k = 1.0 - math.exp(-dt / c.integration_time_s)
            for key, v in d.items():
                prev = self.filtered.get(key)
                self.filtered[key] = v if prev is None or not math.isfinite(prev) else prev + k * (v - prev)
            self.reading = reading
            if self._prop_dirty or quality != self.quality or t_now - self._last_prop >= UNCERTAINTY_REFRESH_S:
                try:
                    self.uncertainty = self.propagate(p_m, t_m, max(dp_m, 1.0), a_low, a_high)
                except (ValueError, np.linalg.LinAlgError):
                    self.uncertainty = {}
                self._last_prop = t_now
                self._prop_dirty = False
            if self.uncertainty.get("liquid_sm3_d", 0) > 20 and quality == "GOOD":
                quality = "DEGRADED"
        else:
            self.reading = None
        old = self.quality
        self.quality = quality
        self.flags = flags
        return [(old, quality)] if old != quality and old != "NOT_READY" else []

    # ---------------------------------------------------------- operations
    def set_faults(self, **kw) -> None:
        for k, v in kw.items():
            if v is not None:
                setattr(self.faults, k, v)
        if not self.faults.dp_stuck:
            self.dp_stuck_value = None
        self._prop_dirty = True

    def calibrate(self, t_now: float, fluid: BlackOilFluid, gor: float, wc: float) -> None:
        """Field calibration: dP zero check (removes offset), meter PVT updated
        from a fresh fluid sample (true composition and salinity), discharge
        coefficient re-established."""
        self.faults.dp_offset_bar = 0.0
        p = fluid.params
        self.meter_params = BlackOilParams(f"{self.cfg.tag} meter PVT", p.api, p.gas_sg, gor, wc, p.water_salinity_wt_pct,
                                           p.cp_oil_j_kgk, p.cp_gas_j_kgk, p.cp_water_j_kgk, p.gas_cp_cv)
        self.meter_fluid = BlackOilFluid(self.meter_params)
        self.cal_time_s = t_now
        self.cd_true = self.cfg.discharge_coefficient
        self.dp_hist.clear()
        self._prop_dirty = True

    def set_true_fluid(self, fluid: BlackOilFluid) -> None:
        self.true_fluid = fluid
        self._prop_dirty = True

    # ------------------------------------------------------------ snapshot
    def snapshot(self, t_now: float) -> dict:
        c = self.cfg
        tr = self.truth
        true_d = self.truth_derived(tr) if tr is not None else None
        meas = dict(self.filtered) if self.reading is not None and self.quality != "BAD" else None
        diff = None
        if meas and true_d:
            diff = {k: (meas[k] - true_d[k]) for k in meas if k in true_d and isinstance(true_d[k], float)}
        mp = self.meter_params
        return {
            "tag": c.tag, "name": c.name, "location_node": c.location_node,
            "principle": "Representative venturi dP + dual-energy gamma phase fractions (not a vendor algorithm)",
            "geometry": {"inlet_diameter_m": c.inlet_diameter_m, "beta": c.beta, "throat_diameter_m": self.dt,
                         "discharge_coefficient": c.discharge_coefficient},
            "quality": self.quality, "flags": self.flags,
            "measured": meas, "true": true_d, "difference": diff, "uncertainty_pct": self.uncertainty or None,
            "uncertainty_budget": getattr(self, "budget", None),
            "signals": {"p_pa": self.meas_inputs.get("p_pa"), "t_k": self.meas_inputs.get("t_k"), "dp_pa": self.meas_inputs.get("dp_pa"),
                        "attenuation_low": self.meas_inputs.get("a_low"), "attenuation_high": self.meas_inputs.get("a_high"),
                        "true_dp_pa": tr.dp if tr else None, "true_p_pa": tr.p if tr else None, "true_t_k": tr.t if tr else None},
            "phase_fractions": None if self.reading is None else {
                "measured": dict(zip(("oil", "gas", "water"), self.reading.alpha)),
                "raw": dict(zip(("oil", "gas", "water"), self.reading.alpha_raw)),
                "true_gas_void_fraction": tr.alpha if tr else None},
            "meter_slip_model": c.meter_slip_model,
            "meter_pvt": {"oil_api": mp.api, "gas_specific_gravity": mp.gas_sg, "water_salinity_wt_pct": mp.water_salinity_wt_pct,
                          "producing_gor_sm3_sm3": mp.gor_sm3_sm3, "water_cut": mp.water_cut},
            "true_fluid": {"oil_api": self.true_fluid.params.api, "gas_specific_gravity": self.true_fluid.params.gas_sg,
                           "water_salinity_wt_pct": self.true_fluid.params.water_salinity_wt_pct},
            "faults": {"dp_offset_bar": self.faults.dp_offset_bar, "dp_stuck": self.faults.dp_stuck,
                       "gamma_failed": self.faults.gamma_failed, "pt_failed": self.faults.pt_failed},
            "calibration": {"last_s": self.cal_time_s, "days_since": (t_now - self.cal_time_s) / S_PER_DAY,
                            "interval_days": c.calibration_interval_days, "cd_actual": self.cd_true,
                            "cd_drift_pct_per_year": c.cd_drift_pct_per_year},
            "envelope": {"dp_min_bar": c.dp_min_bar, "dp_max_bar": c.dp_max_bar, "gvf_max": c.gvf_max},
            "reference_conditions": "Standard volumes at 15 degC and 1.01325 bar (ISO 13443); 'm3/d' values are at meter (line) conditions.",
            "sand_effect": "Not modelled: the representative meter model has no physically supported sand mechanism.",
        }


__all__ = ["MPFM", "Truth", "field"]
