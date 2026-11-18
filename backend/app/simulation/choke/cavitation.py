"""Cavitation and flashing SCREENING at the production choke.

This is a correlation-based screening (model status 2 of the engineering
status ladder), NOT a CFD prediction. It answers three questions for the
current simulated operating point:

1. Is there free gas at the choke inlet? Then the classical liquid
   cavitation criteria do not strictly apply (gas cushions bubble collapse);
   the dominant damage mechanism is erosion by the two-phase jet, which the
   erosion model covers.
2. Live oil: does the pressure fall below the bubble point across the choke
   (outgassing / flashing)? Released gas redissolves slowly, so gas release
   at the vena contracta is "gaseous cavitation", much less violent than
   vapour-bubble collapse.
3. Water phase: does the vena-contracta pressure fall below the water vapour
   pressure (vapour cavitation), or the outlet pressure (flashing)?

Methods (published):

- Vena-contracta pressure and choked liquid differential, IEC 60534-2-1
  (liquid sizing):  P_vc = P1 - (P1 - P2) / FL^2,
  dP_choked = FL^2 (P1 - FF Pv),  FF = 0.96 - 0.28 sqrt(Pv / Pc).
- Cavitation index in the ISA-RP75.23 form  sigma = (P1 - Pv) / (P1 - P2),
  compared with the VALVE-SPECIFIC limits (incipient, constant, manufacturer
  damage limit) entered by the user. No universal sigma limits are assumed.
- Water vapour pressure: IAPWS-IF97 region-4 saturation equation (pure
  water; dissolved salt lowers it slightly, so this is conservative).
- Bubble point: entered from a PVT report, else the Standing correlation
  used by the black-oil model.

FL (liquid pressure-recovery factor) is a property of the trim at the
operating opening and must come from the manufacturer. Without it the
vena-contracta pressure and the choked differential are unavailable and
only the physics-only checks (outlet pressure against Pv and Pb) are made.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

#: Critical pressure of water [Pa] (IAPWS).
PC_WATER = 220.64e5

# IAPWS-IF97 region 4 coefficients n1..n10
_N = (0.11670521452767e4, -0.72421316598208e6, -0.17073846940092e2, 0.12020824702470e5, -0.32325550322333e7,
      0.14915108613530e2, -0.48232657361591e4, 0.40511340542057e6, -0.23855557567849, 0.65017534844798e3)

METHOD = ("Screening: IEC 60534-2-1 liquid pressure recovery (FL, vena-contracta pressure, choked differential) and the "
          "cavitation index sigma = (P1 - Pv)/(P1 - P2) against the valve-specific limits entered; water vapour pressure "
          "IAPWS-IF97; bubble point from the PVT entry or the Standing correlation.")

LIMITATIONS = [
    "Screening correlation only - not a CFD or experimental result. Bubble dynamics, collapse location and damage rate are not computed.",
    "FL and the sigma limits are valve-specific and depend on the opening; use the manufacturer's data for this trim.",
    "Liquid criteria are derived for single-phase liquid; with free gas at the inlet they are indicative only.",
    "Live-oil gas release is treated as outgassing / gaseous cavitation; its damage potential is much lower than vapour cavitation.",
    "Water vapour pressure is for pure water; salinity lowers it slightly (conservative).",
]


def water_saturation_pressure(t_k: float) -> float:
    """IAPWS-IF97 saturation pressure of water [Pa], 273.15 K <= T <= 647.096 K."""
    t = min(max(t_k, 273.15), 647.096)
    n1, n2, n3, n4, n5, n6, n7, n8, n9, n10 = _N
    th = t + n9 / (t - n10)
    a = th * th + n1 * th + n2
    b = n3 * th * th + n4 * th + n5
    c = n6 * th * th + n7 * th + n8
    return (2.0 * c / (-b + math.sqrt(b * b - 4.0 * a * c))) ** 4 * 1e6


def ff_factor(pv: float, pc: float) -> float:
    """IEC 60534-2-1 liquid critical pressure ratio factor."""
    return 0.96 - 0.28 * math.sqrt(max(pv, 0.0) / pc)


def sigma_index(p1: float, p2: float, pv: float) -> float | None:
    dp = p1 - p2
    return (p1 - pv) / dp if dp > 1.0 else None


def interpolate_fl(table: list[tuple[float, float]], opening_pct: float) -> float:
    pts = sorted(table)
    if opening_pct <= pts[0][0]:
        return pts[0][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if opening_pct <= x1:
            return y0 + (y1 - y0) * (opening_pct - x0) / (x1 - x0) if x1 > x0 else y1
    return pts[-1][1]


@dataclass
class CavitationPoint:
    p1: float  # Pa abs, choke inlet
    p2: float  # Pa abs, choke outlet
    t1: float  # K
    opening_pct: float
    pb_correlation: float  # Pa, bubble point of the produced oil (Standing)
    gvf_inlet: float  # free-gas volume fraction at the inlet
    water_cut: float


SIGMA_LEVELS = (("sigma_incipient", "Incipient cavitation"), ("sigma_constant", "Constant cavitation"),
                ("sigma_damage", "Manufacturer damage limit exceeded"))


def _classify(sigma: float | None, inp) -> tuple[str, str | None]:
    """Valve-specific classification of a sigma value; ('Unavailable', why) without limits."""
    lim = {k: getattr(inp, k) for k, _ in SIGMA_LEVELS}
    if not any(v is not None for v in lim.values()):
        return "Unavailable", "valve-specific sigma limits (incipient / constant / damage) not entered"
    if sigma is None:
        return "Not indicated", None
    level = "Not indicated"
    for key, label in SIGMA_LEVELS:
        v = lim[key]
        if v is not None and sigma <= v:
            level = label
    return level, None


def screen(pt: CavitationPoint, inp) -> dict:
    """Screen the operating point; ``inp`` is a CavitationInputs model."""
    p1, p2, t1 = pt.p1, pt.p2, pt.t1
    dp = p1 - p2
    missing: list[str] = []
    assumed: list[str] = []
    notes: list[str] = []
    if inp.fl_table:
        fl = interpolate_fl([(r.opening_pct, r.fl) for r in inp.fl_table], pt.opening_pct)
        fl_src = f"FL table at {pt.opening_pct:.1f} % opening"
    elif inp.fl is not None:
        fl = inp.fl
        fl_src = "single FL value (all openings)"
    else:
        fl, fl_src = None, None
        missing.append("liquid pressure-recovery factor FL of the trim (manufacturer)")
    if inp.bubble_point_bara is not None:
        pb, pb_src = inp.bubble_point_bara * 1e5, "PVT report entry"
    else:
        pb, pb_src = pt.pb_correlation, "Standing correlation (not fitted to a PVT report)"
    pv_w = water_saturation_pressure(t1)
    p_vc = p1 - dp / fl**2 if fl is not None and dp > 0 else None
    if p_vc is not None and p_vc < ff_factor(pv_w, PC_WATER) * pv_w:
        # the IEC relation is valid only down to the vapour-limited minimum; below it the liquid flow is choked
        p_vc = ff_factor(pv_w, PC_WATER) * pv_w
        notes.append("The IEC vena-contracta relation reaches the vapour-pressure limit: the liquid flow is choked (fully developed cavitation or flashing).")
    free_gas = pt.gvf_inlet > 1e-4 or p1 < pb

    # --- oil phase: gas release (bubble point)
    oil: dict = {"pb_bara": pb / 1e5, "pb_source": pb_src, "sigma": sigma_index(p1, p2, pb)}
    if free_gas:
        oil["regime"] = "two_phase_inlet"
        oil["text"] = (f"Free gas at the choke inlet (P1 {p1 / 1e5:.1f} bara vs bubble point {pb / 1e5:.1f} bara, GVF "
                       f"{pt.gvf_inlet * 100:.1f} %): gas keeps coming out of solution across the choke. Liquid cavitation criteria do "
                       "not strictly apply; the damage mechanism is erosion by the two-phase jet (see the erosion model).")
    elif p2 < pb:
        oil["regime"] = "outgassing"
        oil["text"] = (f"Undersaturated oil at the inlet, but the outlet pressure {p2 / 1e5:.1f} bara is below the bubble point "
                       f"{pb / 1e5:.1f} bara: gas comes out of solution across the choke and stays out (flashing / outgassing). "
                       "Expect a high-velocity two-phase jet at the cage-hole exits and in the outlet.")
    elif p_vc is not None and p_vc < pb:
        oil["regime"] = "gaseous_cavitation"
        oil["text"] = (f"Vena-contracta pressure {p_vc / 1e5:.1f} bara is below the bubble point {pb / 1e5:.1f} bara while the "
                       "outlet is above it: gas is released at the vena contracta and redissolves slowly downstream "
                       "(gaseous cavitation - much less violent than vapour-bubble collapse).")
    elif p_vc is None:
        oil["regime"] = "unknown"
        oil["text"] = "Outlet stays above the bubble point; the vena-contracta check needs FL."
    else:
        oil["regime"] = "none"
        oil["text"] = "Pressure stays above the bubble point through the choke: no gas release from the oil."

    # --- water phase: vapour cavitation / flashing
    water: dict | None = None
    if pt.water_cut > 0:
        ff = ff_factor(pv_w, PC_WATER)
        sig_w = sigma_index(p1, p2, pv_w)
        dp_ch = fl**2 * (p1 - ff * pv_w) if fl is not None else None
        level, why = _classify(sig_w, inp)
        if why:
            missing.append(why)
        if p2 < pv_w:
            reg, txt = "flashing", "Outlet pressure is below the water vapour pressure: the water flashes."
        elif p_vc is not None and p_vc < pv_w:
            reg, txt = ("vapour_cavitation", f"Vena-contracta pressure {p_vc / 1e5:.2f} bara is below the water vapour pressure "
                        f"{pv_w / 1e5:.2f} bara and the outlet recovers above it: vapour bubbles form and collapse downstream of the "
                        "vena contracta.")
        elif p_vc is None:
            reg, txt = "unknown", "Vena-contracta pressure needs FL."
        else:
            reg, txt = "none", (f"Vena-contracta pressure {p_vc / 1e5:.1f} bara stays above the water vapour pressure "
                                f"{pv_w / 1e5:.2f} bara.")
        if level not in ("Unavailable", "Not indicated") and reg == "none":
            txt += (f" The valve-specific sigma limits nevertheless indicate {level.lower()}: they are empirical and include the local "
                    "pressure minima in the jets and vortices, which the mean vena-contracta pressure does not show.")
        water = {"pv_bara": pv_w / 1e5, "ff": ff, "sigma": sig_w, "dp_choked_bar": None if dp_ch is None else dp_ch / 1e5,
                 "choked": None if dp_ch is None else dp >= dp_ch, "regime": reg, "text": txt, "level": level}
        if free_gas:
            notes.append("Free gas at the inlet cushions bubble collapse: the water-phase result is indicative only.")

    # --- overall indicator
    order = ["none", "unknown", "gaseous_cavitation", "outgassing", "two_phase_inlet", "vapour_cavitation", "flashing"]
    regimes = [oil["regime"]] + ([water["regime"]] if water else [])
    governing = max(regimes, key=order.index)
    if water and water["level"] not in ("Unavailable", "Not indicated"):
        risk = water["level"] + (" (indicative - free gas at the inlet)" if free_gas else "")
    elif water and water["regime"] in ("vapour_cavitation", "flashing"):
        risk = "Possible - confirm with the valve-specific sigma limits"
    elif governing in ("outgassing", "two_phase_inlet", "gaseous_cavitation"):
        risk = "Gas release - erosion-driven, not vapour cavitation"
    elif governing == "unknown":
        risk = "Unavailable"
    else:
        risk = "Not indicated"

    locations: list[str] = []
    if governing in ("vapour_cavitation", "gaseous_cavitation") or (water and water["level"] not in ("Unavailable", "Not indicated")):
        locations += ["cage-hole exits and the bore just downstream of the vena contracta",
                      "plug nose and seat land (at small openings the jets impinge here)"]
    if governing in ("flashing", "outgassing", "two_phase_inlet"):
        locations += ["cage-hole exit edges (high-velocity two-phase jets)", "body gallery and outlet bore downstream of the cage"]

    # --- sensitivity to the bubble point
    band = inp.bubble_point_uncertainty_pct / 100.0
    sens = None
    if band > 0:
        lo, hi = pb * (1 - band), pb * (1 + band)
        sens = {"pb_low_bara": lo / 1e5, "pb_high_bara": hi / 1e5,
                "outlet_below_pb_low": p2 < lo, "outlet_below_pb_high": p2 < hi,
                "note": (f"bubble point +/-{inp.bubble_point_uncertainty_pct:g} % "
                         + ("(sensitivity band entered by the user)" if inp.bubble_point_bara is not None else "(ASSUMED correlation band)"))}
        if inp.bubble_point_bara is None:
            assumed.append(f"bubble-point uncertainty band +/-{inp.bubble_point_uncertainty_pct:g} % for the Standing correlation")
        if sens["outlet_below_pb_low"] != sens["outlet_below_pb_high"]:
            notes.append("The outgassing conclusion changes within the bubble-point uncertainty band - enter the PVT-report bubble point.")

    return {
        "available": True,
        "status": "Correlation-based screening",
        "method": METHOD,
        "p1_bara": p1 / 1e5, "p2_bara": p2 / 1e5, "dp_bar": dp / 1e5, "t_c": t1 - 273.15, "opening_pct": pt.opening_pct,
        "fl": fl, "fl_source": fl_src, "vena_contracta_bara": None if p_vc is None else p_vc / 1e5,
        "inlet_free_gas": free_gas, "gvf_inlet": pt.gvf_inlet,
        "oil": oil, "water": water, "regime": governing, "risk": risk,
        "limits": {k: getattr(inp, k) for k, _ in SIGMA_LEVELS} | {"source": inp.threshold_source},
        "damage_locations": locations, "sensitivity": sens,
        "missing": missing, "assumed": assumed, "notes": notes, "limitations": LIMITATIONS,
    }
