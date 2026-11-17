"""Three-phase black-oil PVT model (oil, gas, water).

Components (stock-tank basis): stock-tank oil, surface gas, water. Phases at
line conditions: oil (with dissolved gas), free gas, water. The produced
stream is characterised by the producing gas-oil ratio GOR [Sm3/Sm3] and the
water cut WC [-] (both at standard conditions); free gas exists wherever
the solution GOR Rs(p, T) is below the producing GOR.

Correlations (field-unit forms, converted internally; see
docs/MULTIPHASE_FLOW_MODEL.md for equations, sources and validity ranges):

    Rs, Pb, Bo (saturated)  Standing (1947, 1981)
    Bo (undersaturated)     Vasquez & Beggs (1980) oil compressibility
    oil viscosity           Beggs & Robinson (1975) dead / live,
                            Vasquez & Beggs (1980) undersaturated
    gas Z factor            Dranchuk & Abou-Kassem (1975) with Sutton (1985)
                            pseudo-critical properties
    gas viscosity           Lee, Gonzalez & Eakin (1966)
    water Bw, rho, mu       McCain (1990, 1991), salinity in wt% NaCl equiv.
    gas-oil surface tension Baker & Swerdloff (1956), gas-water ~ constant

Simplifications (documented): gas solubility in water neglected; no
gas-condensate / volatile-oil behaviour; correlations are generic (NOT
fitted to a laboratory PVT report) - outputs are labelled as correlation
estimates and checked against each correlation's data range.

Every function is vectorised over numpy arrays of p [Pa abs], T [K], GOR and
WC so that the dynamic model can evaluate all network nodes in one call.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

# --- standard conditions and unit factors -----------------------------------
#: Standard conditions used for "standard" volumes: 15 deg C, 1.01325 bar
#: (ISO 13443). Stated on every standard-rate output.
P_SC = 101_325.0
T_SC = 288.15
PSI_PER_PA = 1.0 / 6894.757293168
SCF_STB_PER_SM3_SM3 = 5.614583333  # 1 Sm3/Sm3 = 5.6146 scf/STB
RHO_AIR_SC = 1.2250  # kg/m3 at 15 C, 1 atm (dry air, M = 28.966)
M_AIR = 28.966e-3  # kg/mol
R_GAS = 8.314462618
RHO_WATER_SC = 999.1  # pure water at 15 C [kg/m3]


def _t_f(t_k):
    return (np.asarray(t_k) - 273.15) * 1.8 + 32.0


def _t_r(t_k):
    return np.asarray(t_k) * 1.8


@dataclass(frozen=True)
class BlackOilParams:
    name: str
    api: float  # stock-tank oil gravity [deg API]
    gas_sg: float  # separator gas specific gravity (air = 1)
    gor_sm3_sm3: float  # producing gas-oil ratio [Sm3/Sm3]
    water_cut: float  # [-] at standard conditions
    water_salinity_wt_pct: float = 3.5
    cp_oil_j_kgk: float = 2100.0
    cp_gas_j_kgk: float = 2300.0
    cp_water_j_kgk: float = 4100.0
    gas_cp_cv: float = 1.27  # ratio of specific heats of the gas (choke model)

    @property
    def oil_sg(self) -> float:
        return 141.5 / (self.api + 131.5)

    @property
    def rho_oil_sc(self) -> float:
        return self.oil_sg * RHO_WATER_SC

    @property
    def rho_gas_sc(self) -> float:
        return self.gas_sg * RHO_AIR_SC

    @property
    def rho_water_sc(self) -> float:
        s = self.water_salinity_wt_pct
        return (62.368 + 0.438603 * s + 1.60074e-3 * s * s) * 16.018463  # McCain, lb/ft3 -> kg/m3


# ---------------------------------------------------------------- oil (Standing)
def solution_gor(p, t_k, api: float, gas_sg: float):
    """Standing Rs at pressure p (saturated oil) [Sm3/Sm3]."""
    p_psia = np.maximum(np.asarray(p) * PSI_PER_PA, 14.7)
    x = 0.0125 * api - 0.00091 * _t_f(t_k)
    rs_scf = gas_sg * ((p_psia / 18.2 + 1.4) * 10.0**x) ** 1.2048
    return rs_scf / SCF_STB_PER_SM3_SM3


def bubble_point(gor, t_k, api: float, gas_sg: float):
    """Standing bubble-point pressure for a solution GOR [Pa abs]."""
    rs_scf = np.maximum(np.asarray(gor) * SCF_STB_PER_SM3_SM3, 1e-6)
    a = 0.00091 * _t_f(t_k) - 0.0125 * api
    pb_psia = 18.2 * ((rs_scf / gas_sg) ** 0.83 * 10.0**a - 1.4)
    return np.maximum(pb_psia, 14.7) / PSI_PER_PA


def _bo_standing(rs, t_k, api: float, gas_sg: float):
    gamma_o = 141.5 / (api + 131.5)
    rs_scf = np.asarray(rs) * SCF_STB_PER_SM3_SM3
    return 0.9759 + 0.00012 * (rs_scf * math.sqrt(gas_sg / gamma_o) + 1.25 * _t_f(t_k)) ** 1.2


def _vb_a(rs_b, t_k, api: float, gas_sg: float):
    """Vasquez-Beggs: c_o = A / p  =>  Bo = Bob (pb / p)^A ; A dimensionless."""
    rs_scf = np.asarray(rs_b) * SCF_STB_PER_SM3_SM3
    return 1e-5 * (-1433.0 + 5.0 * rs_scf + 17.2 * _t_f(t_k) - 1180.0 * gas_sg + 12.61 * api)


def _mu_dead_oil(t_k, api: float):
    """Beggs-Robinson dead-oil viscosity [cP]."""
    z = 3.0324 - 0.02023 * api
    x = 10.0**z * np.maximum(_t_f(t_k), 40.0) ** -1.163
    return 10.0**x - 1.0


def _mu_live_oil(mu_od, rs):
    rs_scf = np.asarray(rs) * SCF_STB_PER_SM3_SM3
    a = 10.715 * (rs_scf + 100.0) ** -0.515
    b = 5.44 * (rs_scf + 150.0) ** -0.338
    return a * mu_od**b


# ---------------------------------------------------------------- gas
def pseudo_critical(gas_sg: float) -> tuple[float, float]:
    """Sutton (1985): (Tpc [K], Ppc [Pa])."""
    tpc_r = 169.2 + 349.5 * gas_sg - 74.0 * gas_sg**2
    ppc_psia = 756.8 - 131.0 * gas_sg - 3.6 * gas_sg**2
    return tpc_r / 1.8, ppc_psia / PSI_PER_PA


_DAK = (0.3265, -1.0700, -0.5339, 0.01569, -0.05165, 0.5475, -0.7361, 0.1844, 0.1056, 0.6134, 0.7210)


def z_factor_dak(ppr, tpr):
    """Dranchuk & Abou-Kassem (1975) Z factor, vectorised Newton on the
    reduced density. Valid 0.2 <= Ppr < 30, 1.0 < Tpr <= 3.0."""
    A1, A2, A3, A4, A5, A6, A7, A8, A9, A10, A11 = _DAK
    ppr = np.atleast_1d(np.asarray(ppr, dtype=float))
    tpr = np.broadcast_to(np.atleast_1d(np.asarray(tpr, dtype=float)), ppr.shape)
    c1 = A1 + A2 / tpr + A3 / tpr**3 + A4 / tpr**4 + A5 / tpr**5
    c2 = A6 + A7 / tpr + A8 / tpr**2
    c3 = A9 * (A7 / tpr + A8 / tpr**2)
    rho = 0.27 * ppr / tpr  # initial guess Z = 1
    for _ in range(60):
        r2 = rho * rho
        e = np.exp(-A11 * r2)
        z = 1.0 + c1 * rho + c2 * r2 - c3 * r2 * r2 * rho + A10 * (1.0 + A11 * r2) * (r2 / tpr**3) * e
        f = z - 0.27 * ppr / (rho * tpr)
        dz = (c1 + 2.0 * c2 * rho - 5.0 * c3 * r2 * r2
              + A10 * (2.0 * rho / tpr**3) * e * (1.0 + A11 * r2 - A11 * A11 * r2 * r2))
        df = dz + 0.27 * ppr / (rho * rho * tpr)
        step = f / df
        rho_new = np.clip(rho - step, 1e-9, 3.0)
        if np.all(np.abs(rho_new - rho) < 1e-12 + 1e-10 * rho):
            rho = rho_new
            break
        rho = rho_new
    r2 = rho * rho
    z = 1.0 + c1 * rho + c2 * r2 - c3 * r2 * r2 * rho + A10 * (1.0 + A11 * r2) * (r2 / tpr**3) * np.exp(-A11 * r2)
    return z


def gas_viscosity_lge(rho_g, t_k, gas_sg: float):
    """Lee, Gonzalez & Eakin (1966) [cP]; rho_g in kg/m3."""
    m = 28.966 * gas_sg
    t_r = _t_r(t_k)
    k = (9.4 + 0.02 * m) * t_r**1.5 / (209.0 + 19.0 * m + t_r)
    x = 3.5 + 986.0 / t_r + 0.01 * m
    y = 2.4 - 0.2 * x
    return 1e-4 * k * np.exp(x * (np.asarray(rho_g) / 1000.0) ** y)


# ---------------------------------------------------------------- water (McCain)
def water_fvf(p, t_k):
    t = _t_f(t_k)
    p_psia = np.asarray(p) * PSI_PER_PA
    dvt = -1.0001e-2 + 1.33391e-4 * t + 5.50654e-7 * t * t
    dvp = -1.95301e-9 * p_psia * t - 1.72834e-13 * p_psia**2 * t - 3.58922e-7 * p_psia - 2.25341e-10 * p_psia**2
    return (1.0 + dvt) * (1.0 + dvp)


def water_viscosity(p, t_k, salinity_wt_pct: float):
    s = salinity_wt_pct
    t = np.maximum(_t_f(t_k), 40.0)
    a = 109.574 - 8.40564 * s + 0.313314 * s**2 + 8.72213e-3 * s**3
    b = 1.12166 - 2.63951e-2 * s + 6.79461e-4 * s**2 + 5.47119e-5 * s**3 - 1.55586e-6 * s**4
    p_psia = np.asarray(p) * PSI_PER_PA
    return a * t**-b * (0.9994 + 4.0295e-5 * p_psia + 3.1062e-9 * p_psia**2)


# ---------------------------------------------------------------- state
@dataclass
class PhaseState:
    """Phase properties and per-unit-stock-tank-liquid volumes at (p, T).

    All arrays share the broadcast shape of the inputs. "Per unit liquid"
    means per 1 Sm3 of stock-tank liquid (oil + water) produced."""

    p: np.ndarray
    t: np.ndarray
    gor: np.ndarray
    wc: np.ndarray
    rs: np.ndarray  # Sm3/Sm3
    pb: np.ndarray  # Pa
    bo: np.ndarray
    bg: np.ndarray  # m3 / Sm3
    bw: np.ndarray
    z: np.ndarray
    rho_o: np.ndarray
    rho_g: np.ndarray
    rho_w: np.ndarray
    mu_o: np.ndarray  # Pa.s
    mu_g: np.ndarray
    mu_w: np.ndarray
    sigma_gl: np.ndarray  # N/m, gas-liquid
    # per 1 Sm3 stock-tank liquid
    vol_o: np.ndarray  # m3 oil phase at line conditions
    vol_g: np.ndarray  # m3 free gas
    vol_w: np.ndarray  # m3 water
    mass_o: np.ndarray  # kg in oil phase (stock-tank oil + dissolved gas)
    mass_g: np.ndarray  # kg free gas
    mass_w: np.ndarray  # kg water

    @property
    def vol_l(self):
        return self.vol_o + self.vol_w

    @property
    def vol(self):
        return self.vol_o + self.vol_g + self.vol_w

    @property
    def mass(self):
        return self.mass_o + self.mass_g + self.mass_w

    @property
    def rho_ns(self):
        """No-slip mixture density [kg/m3]."""
        return self.mass / self.vol

    @property
    def lambda_l(self):
        """No-slip liquid volume fraction (= 1 - GVF)."""
        return self.vol_l / self.vol

    @property
    def gvf(self):
        return self.vol_g / self.vol

    @property
    def rho_l(self):
        return (self.mass_o + self.mass_w) / np.maximum(self.vol_l, 1e-30)

    @property
    def mu_l(self):
        """Liquid viscosity, volume-fraction weighted (no emulsion model)."""
        vl = np.maximum(self.vol_l, 1e-30)
        return (self.mu_o * self.vol_o + self.mu_w * self.vol_w) / vl

    @property
    def free_gas_mass_fraction(self):
        return self.mass_g / self.mass


class BlackOilFluid:
    """Black-oil fluid with a default produced composition (GOR, WC)."""

    is_constant_property = False

    def __init__(self, params: BlackOilParams):
        self.params = params
        self.name = params.name
        self.tpc, self.ppc = pseudo_critical(params.gas_sg)
        self.m_gas = M_AIR * params.gas_sg

    # ------------------------------------------------------------ state
    def state(self, p, t_k, gor=None, wc=None) -> PhaseState:
        q = self.params
        p = np.maximum(np.atleast_1d(np.asarray(p, dtype=float)), 2.0e4)
        t = np.broadcast_to(np.atleast_1d(np.asarray(t_k, dtype=float)), p.shape)
        gor = np.broadcast_to(np.atleast_1d(np.asarray(q.gor_sm3_sm3 if gor is None else gor, dtype=float)), p.shape)
        wc = np.broadcast_to(np.atleast_1d(np.asarray(q.water_cut if wc is None else wc, dtype=float)), p.shape)
        gor = np.maximum(gor, 0.0)
        wc = np.clip(wc, 0.0, 1.0)
        # oil
        pb = bubble_point(np.maximum(gor, 1e-3), t, q.api, q.gas_sg)
        rs_sat = solution_gor(p, t, q.api, q.gas_sg)
        under = p >= pb
        rs = np.where(under, gor, np.minimum(rs_sat, gor))
        bo_sat = _bo_standing(rs, t, q.api, q.gas_sg)
        bob = _bo_standing(gor, t, q.api, q.gas_sg)
        a = np.maximum(_vb_a(gor, t, q.api, q.gas_sg), 0.0)
        bo = np.where(under, bob * (pb / p) ** a, bo_sat)
        mass_o_per_sto = q.rho_oil_sc + rs * q.rho_gas_sc
        rho_o = mass_o_per_sto / bo
        mu_od = _mu_dead_oil(t, q.api)
        mu_ob = _mu_live_oil(mu_od, rs)
        p_psia = p * PSI_PER_PA
        m_exp = 2.6 * p_psia**1.187 * np.exp(-11.513 - 8.98e-5 * p_psia)
        mu_o = np.where(under, mu_ob * (p / pb) ** m_exp, mu_ob)
        # gas
        z = z_factor_dak(p / self.ppc, t / self.tpc).reshape(p.shape)
        bg = (P_SC / p) * (t / T_SC) * z
        rho_g = p * self.m_gas / (z * R_GAS * t)
        mu_g = gas_viscosity_lge(rho_g, t, q.gas_sg)
        # water
        bw = water_fvf(p, t)
        rho_w = q.rho_water_sc / bw
        mu_w = water_viscosity(p, t, q.water_salinity_wt_pct)
        # gas-oil interfacial tension (Baker-Swerdloff), mixed with ~0.06 N/m gas-water by volume
        tf = _t_f(t)
        s68, s100 = 39.0 - 0.2571 * q.api, 37.5 - 0.2571 * q.api
        sod = np.where(tf <= 68.0, s68, np.where(tf >= 100.0, s100, s68 - (tf - 68.0) * (s68 - s100) / 32.0))
        sod = np.where(tf > 100.0, s100, sod)
        so = np.maximum(sod * (1.0 - 0.024 * p_psia**0.45), 1.0)  # dyn/cm
        # per 1 Sm3 stock-tank liquid
        fo, fw = 1.0 - wc, wc
        free = np.maximum(gor - rs, 0.0)
        vol_o, vol_g, vol_w = fo * bo, fo * free * bg, fw * bw
        mass_o, mass_g, mass_w = fo * mass_o_per_sto, fo * free * q.rho_gas_sc, fw * q.rho_water_sc
        vl = np.maximum(vol_o + vol_w, 1e-30)
        sigma = (so * 1e-3 * vol_o + 0.060 * vol_w) / vl
        cp = 1e-3  # cP -> Pa.s
        return PhaseState(p, t, gor, wc, rs, pb, bo, bg, bw, z, rho_o, rho_g, rho_w, mu_o * cp, mu_g * cp, mu_w * cp, sigma,
                          vol_o, vol_g, vol_w, mass_o, mass_g, mass_w)

    # ------------------------------------------------------ mixture helpers
    def mass_per_liquid_sc(self, gor=None, wc=None):
        """Mass of produced fluid per 1 Sm3 of stock-tank liquid [kg/Sm3]."""
        q = self.params
        gor = q.gor_sm3_sm3 if gor is None else gor
        wc = q.water_cut if wc is None else wc
        return (1.0 - wc) * (q.rho_oil_sc + gor * q.rho_gas_sc) + wc * q.rho_water_sc

    def component_mass_fractions(self, gor=None, wc=None) -> tuple[float, float, float]:
        """(stock-tank oil, surface gas, water) mass fractions of the stream."""
        q = self.params
        gor = q.gor_sm3_sm3 if gor is None else gor
        wc = q.water_cut if wc is None else wc
        m = self.mass_per_liquid_sc(gor, wc)
        return ((1 - wc) * q.rho_oil_sc / m, (1 - wc) * gor * q.rho_gas_sc / m, wc * q.rho_water_sc / m)

    def composition_from_mass_fractions(self, xo, xg, xw):
        """Inverse of component_mass_fractions: (GOR, WC) arrays."""
        q = self.params
        xo, xg, xw = (np.asarray(v, dtype=float) for v in (xo, xg, xw))
        v_o = xo / q.rho_oil_sc  # Sm3 oil per kg
        v_w = xw / q.rho_water_sc
        gor = np.where(v_o > 1e-15, (xg / q.rho_gas_sc) / np.maximum(v_o, 1e-15), 0.0)
        wc = v_w / np.maximum(v_o + v_w, 1e-15)
        return gor, wc

    def mixture(self, p, t_k, gor=None, wc=None, dp_rel: float = 2e-3, dt_k: float = 0.2):
        """No-slip density with its pressure and temperature derivatives
        (numerical; include gas liberation/solution) and the mixture mass
        heat capacity. Returns (state, rho, drho_dp, drho_dt, cp)."""
        s = self.state(p, t_k, gor, wc)
        p = s.p
        dp = np.maximum(p * dp_rel, 500.0)
        # forward differences (one extra evaluation each); bubble-point kinks are
        # resolved to within dp_rel of the pressure
        s_hi = self.state(p + dp, s.t, s.gor, s.wc)
        drho_dp = (s_hi.rho_ns - s.rho_ns) / dp
        s_th = self.state(p, s.t + dt_k, s.gor, s.wc)
        drho_dt = (s_th.rho_ns - s.rho_ns) / dt_k
        q = self.params
        cp = (s.mass_o * q.cp_oil_j_kgk + s.mass_g * q.cp_gas_j_kgk + s.mass_w * q.cp_water_j_kgk) / s.mass
        return s, s.rho_ns, drho_dp, drho_dt, cp

    # -------------------------------------------------------- validity
    def validity(self, p_min: float, p_max: float, t_min: float, t_max: float) -> list[dict]:
        """Data ranges of the correlations vs the operating envelope.
        Returns one entry per correlation with in_range flag and notes."""
        q = self.params
        rs_scf = q.gor_sm3_sm3 * SCF_STB_PER_SM3_SM3
        tf_lo, tf_hi = float(_t_f(t_min)), float(_t_f(t_max))
        pb = float(bubble_point(q.gor_sm3_sm3, t_max, q.api, q.gas_sg)) * PSI_PER_PA
        checks = [
            ("Standing Rs / Pb / Bo", [(q.api, 16.5, 63.8, "API"), (q.gas_sg, 0.59, 0.95, "gas SG"), (rs_scf, 20, 1425, "Rs scf/STB"),
                                       (tf_hi, 100, 258, "T degF"), (pb, 130, 7000, "Pb psia")]),
            ("Vasquez-Beggs (undersaturated Bo, mu_o)", [(q.api, 15.3, 59.5, "API"), (q.gas_sg, 0.511, 1.351, "gas SG"),
                                                         (rs_scf, 9.3, 2199, "Rs scf/STB"), (p_max * PSI_PER_PA, 141, 9515, "p psia")]),
            ("Beggs-Robinson oil viscosity", [(q.api, 16, 58, "API"), (tf_lo, 70, 295, "T degF"), (tf_hi, 70, 295, "T degF"),
                                              (rs_scf, 20, 2070, "Rs scf/STB")]),
            ("Dranchuk-Abou-Kassem Z", [(float(t_min / self.tpc), 1.0, 3.0, "Tpr"), (float(t_max / self.tpc), 1.0, 3.0, "Tpr"),
                                        (float(p_max / self.ppc), 0.2, 30.0, "Ppr")]),
            ("Lee-Gonzalez-Eakin gas viscosity", [(tf_lo, 100, 340, "T degF"), (tf_hi, 100, 340, "T degF"), (p_max * PSI_PER_PA, 100, 8000, "p psia")]),
            ("McCain water properties", [(tf_hi, 60, 260, "T degF"), (q.water_salinity_wt_pct, 0, 26, "salinity wt%"), (p_max * PSI_PER_PA, 0, 5000, "p psia")]),
        ]
        out = []
        for name, items in checks:
            bad = [f"{lbl} {v:.3g} outside {lo:g}-{hi:g}" for v, lo, hi, lbl in items if not lo <= v <= hi]
            out.append({"correlation": name, "in_range": not bad, "notes": bad})
        return out
