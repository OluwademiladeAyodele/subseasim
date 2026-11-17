"""Sand production: sanding onset, particle size, screen retention, sand rate.

Onset - critical bottomhole flowing pressure for perforation tunnels
(Willson, Moschovidis, Cameron & Palmer 2002, SPE 78168; Weingarten &
Perkins 1995): the effective tangential stress at the perforation wall,

    sigma_t' = 3 sigma_1 - sigma_3 - 2 P_w - A (P_r - P_w),
    A = alpha (1 - 2 nu) / (1 - nu)            (poro-elastic flow term)

reaches the effective rock strength U when

    CBHFP = (3 sigma_1 - sigma_3 - U - A P_r) / (2 - A)
    critical drawdown = P_r - CBHFP

with U = 3.1 x TWC for a perforation tunnel (TWC = thick-walled-cylinder
collapse strength, OD/ID = 3). Horizontal perforations in a vertical well are
taken in the worst orientation (sigma_1 = overburden, sigma_3 = minimum
horizontal stress). Depletion lowers the horizontal stress along the stress
path:  sigma_h = sigma_h,i - gamma (P_r,i - P_r). Water weakening reduces U by
(1 - w x water cut) - water cut is used as a proxy for near-wellbore water
saturation (documented simplification).

Rate - after onset there is no universal equation (rates vary over orders
of magnitude with rock, completion and history). A CALIBRATED empirical form
is used and labelled as such:

    m_formation = k Q_liquid,res (r - 1)^n,     r = drawdown / critical drawdown

k [kg/m3] must come from field data (sand traps, detectors, well tests); the
prediction is unavailable without it.

Screens - standalone screens retain grains coarser than the aperture
(geometric retention; bridging is not modelled): the produced fraction is
the PSD fraction finer than the aperture, plus all sand through any
damaged screen area.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from app.models.sand import CompletionInputs, GeomechanicsInputs, SandInputs

PA_PER_BAR = 1e5
PERFORATION_STRENGTH_FACTOR = 3.1  # Willson et al. (2002), perforation tunnel vs TWC
LB_KG = 0.45359237
BBL_M3 = 0.158987294928


@dataclass
class Onset:
    available: bool
    missing: list[str] = field(default_factory=list)
    assumed: list[str] = field(default_factory=list)
    cbhfp_pa: float | None = None
    critical_drawdown_pa: float | None = None
    drawdown_pa: float | None = None
    risk_index: float | None = None  # drawdown / critical drawdown
    sigma_v_pa: float | None = None
    sigma_h_pa: float | None = None
    strength_pa: float | None = None  # effective strength U
    a_factor: float | None = None
    notes: list[str] = field(default_factory=list)


def sanding_onset(g: GeomechanicsInputs, p_res: float, p_bh: float, water_cut: float) -> Onset:
    missing = [n for n, v in (("depth (TVD)", g.depth_tvd_m), ("overburden stress gradient", g.overburden_gradient_bar_m),
                              ("minimum horizontal stress gradient", g.min_horizontal_stress_gradient_bar_m)) if v is None]
    assumed: list[str] = []
    if g.twc_strength_mpa is not None:
        twc = g.twc_strength_mpa * 1e6
        src = "TWC (input)"
    elif g.ucs_mpa is not None and g.twc_ucs_ratio is not None:
        twc = g.ucs_mpa * g.twc_ucs_ratio * 1e6
        src = "TWC from UCS x site ratio"
        assumed.append("TWC estimated from UCS with the site TWC/UCS ratio - lower confidence than measured TWC")
    else:
        missing.append("rock strength (TWC, or UCS with a TWC/UCS ratio)")
        twc, src = None, ""
    if missing:
        return Onset(False, missing)
    alpha = g.biot_coefficient if g.biot_coefficient is not None else 1.0
    nu = g.poisson_ratio if g.poisson_ratio is not None else 0.25
    if g.biot_coefficient is None:
        assumed.append("Biot coefficient assumed 1.0")
    if g.poisson_ratio is None:
        assumed.append("Poisson ratio assumed 0.25")
    p_init = g.initial_reservoir_pressure_bara * PA_PER_BAR if g.initial_reservoir_pressure_bara else p_res
    if g.initial_reservoir_pressure_bara is None:
        assumed.append("initial reservoir pressure = current (no depletion effect)")
    gamma = g.stress_path_coefficient if g.stress_path_coefficient is not None else 0.6
    if g.stress_path_coefficient is None and abs(p_init - p_res) > 1e5:
        assumed.append("stress-path coefficient assumed 0.6")
    sv = g.overburden_gradient_bar_m * PA_PER_BAR * g.depth_tvd_m  # type: ignore[operator]
    sh0 = g.min_horizontal_stress_gradient_bar_m * PA_PER_BAR * g.depth_tvd_m  # type: ignore[operator]
    sh = sh0 - gamma * (p_init - p_res)
    s1, s3 = max(sv, sh), min(sv, sh)
    ww = g.water_weakening_fraction or 0.0
    u_eff = PERFORATION_STRENGTH_FACTOR * twc * max(0.05, 1.0 - ww * water_cut)  # type: ignore[operator]
    a = alpha * (1 - 2 * nu) / (1 - nu)
    cbhfp = (3 * s1 - s3 - u_eff - a * p_res) / (2 - a)
    cdd = p_res - cbhfp
    dd = p_res - p_bh
    notes = [f"strength source: {src}", "perforations: horizontal, worst orientation (sigma_1 = overburden, sigma_3 = min horizontal)"]
    if ww > 0:
        notes.append(f"water weakening applied: strength x {max(0.05, 1 - ww * water_cut):.2f} at water cut {water_cut * 100:.0f} %")
    risk = dd / cdd if cdd > 0 else math.inf
    if cdd <= 0:
        notes.append("critical drawdown <= 0: the formation is predicted to fail even at zero drawdown (sand at any rate)")
    return Onset(True, [], assumed, cbhfp, cdd, dd, risk, sv, sh, u_eff, a, notes)


# ------------------------------------------------------------------- PSD
@dataclass
class PSD:
    mu: float  # ln(d50 in m)
    sigma: float

    def fraction_finer(self, d_m: float) -> float:
        if d_m <= 0:
            return 0.0
        return 0.5 * (1 + math.erf((math.log(d_m) - self.mu) / (self.sigma * math.sqrt(2))))

    def quantile(self, f: float) -> float:
        # inverse normal (Acklam-free: bisection on erf)
        lo, hi = -10.0, 10.0
        for _ in range(80):
            mid = 0.5 * (lo + hi)
            if 0.5 * (1 + math.erf(mid / math.sqrt(2))) < f:
                lo = mid
            else:
                hi = mid
        return math.exp(self.mu + self.sigma * 0.5 * (lo + hi))


def fit_psd(s: SandInputs) -> PSD | None:
    """Log-normal PSD from D50 and D10 and/or D90."""
    if s.d50_um is None or (s.d10_um is None and s.d90_um is None):
        return None
    d50 = s.d50_um * 1e-6
    z = 1.2815515655446004
    sig = []
    if s.d90_um is not None and s.d90_um > s.d50_um:
        sig.append(math.log(s.d90_um / s.d50_um) / z)
    if s.d10_um is not None and s.d10_um < s.d50_um:
        sig.append(math.log(s.d50_um / s.d10_um) / z)
    if not sig:
        return None
    return PSD(math.log(d50), sum(sig) / len(sig))


@dataclass
class ScreenResult:
    available: bool
    passing_fraction: float | None = None
    produced_d50_m: float | None = None
    missing: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def screen_passing(c: CompletionInputs, psd: PSD | None) -> ScreenResult:
    if c.completion_type == "cased_perforated_no_screens":
        return ScreenResult(True, 1.0, math.exp(psd.mu) if psd else None, [], ["no sand control: all failed sand is produced"])
    if c.completion_type == "gravel_pack":
        return ScreenResult(False, None, None, ["gravel-pack retention model (not implemented)"], [])
    missing = []
    if c.screen_aperture_um is None:
        missing.append("screen aperture")
    if psd is None:
        missing.append("formation particle-size distribution (D50 and D10 or D90)")
    if missing:
        return ScreenResult(False, None, None, missing)
    ap = c.screen_aperture_um * 1e-6 / c.bridging_factor  # type: ignore[operator]
    f_fine = psd.fraction_finer(ap)  # type: ignore[union-attr]
    dmg = c.screen_damage_fraction
    f = dmg + (1 - dmg) * f_fine
    # median of what passes: intact screen passes the fines; damaged area passes the full PSD
    d50_fines = psd.quantile(0.5 * f_fine) if f_fine > 1e-9 else ap  # type: ignore[union-attr]
    d50_prod = math.exp((dmg * psd.mu + (1 - dmg) * f_fine * math.log(d50_fines)) / max(dmg + (1 - dmg) * f_fine, 1e-12)) if f > 0 else 0.0  # type: ignore[union-attr]
    notes = [f"{f_fine * 100:.1f} % of the formation sand is finer than {ap * 1e6:.0f} um (aperture {c.screen_aperture_um:.0f} um / "
             f"bridging factor {c.bridging_factor:g}) and passes the intact screen"]
    if dmg > 0:
        notes.append(f"{dmg * 100:.1f} % of the screen area damaged: full PSD passes there")
    notes.append("retained sand stays behind the screen (screen plugging / hot-spot erosion of the screen are not modelled)")
    return ScreenResult(True, f, d50_prod, [], notes)


# -------------------------------------------------------------- sand rate
def predicted_formation_rate(s: SandInputs, onset: Onset, q_liquid_res_m3s: float) -> tuple[float | None, list[str]]:
    if not onset.available:
        return None, ["sanding onset unavailable"]
    if s.rate_coefficient_kg_m3 is None:
        return None, ["sand-rate coefficient k (calibrated from field sand data)"]
    r = onset.risk_index if onset.risk_index is not None else 0.0
    if not math.isfinite(r):
        r = 10.0
    excess = max(0.0, r - 1.0)
    return s.rate_coefficient_kg_m3 * max(q_liquid_res_m3s, 0.0) * excess ** s.rate_exponent, []


def measured_rate_kg_s(s: SandInputs, q_liquid_sc_m3s: float, liquid_mass_kg_s: float, total_mass_kg_s: float) -> float | None:
    v = s.measured_value
    if v is None:
        return None
    u = s.measured_unit
    if u == "kg_h":
        return v / 3600.0
    if u == "kg_d":
        return v / 86400.0
    if u == "g_s":
        return v / 1000.0
    if u == "pptb":  # pounds per thousand barrels of liquid (stock tank)
        return v * LB_KG / (1000 * BBL_M3) * q_liquid_sc_m3s
    if u == "ppm_mass_liquid":
        return v * 1e-6 * liquid_mass_kg_s
    if u == "ppm_mass_total":
        return v * 1e-6 * total_mass_kg_s
    if u == "ppm_vol_liquid":  # sand volume per liquid volume at standard conditions
        return v * 1e-6 * q_liquid_sc_m3s * s.grain_density_kg_m3
    return None
