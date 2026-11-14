"""Unit conversions and physical constants.

Internal convention (see docs/ENGINEERING_ASSUMPTIONS.md):
    pressure      Pa, ABSOLUTE
    temperature   K
    volume flow   m3/s (at line conditions)
    mass flow     kg/s
    length        m
    viscosity     Pa.s
    density       kg/m3

Every conversion used anywhere in the backend must live here so that it is
tested once (tests/test_units.py).
"""

from __future__ import annotations

import math

# --- physical constants ------------------------------------------------------
#: Standard gravitational acceleration [m/s2] (ISO 80000-3).
G = 9.80665
#: Standard atmosphere [Pa]. Used ONLY as the reference for gauge pressure.
P_ATM = 101_325.0
#: Pa per bar (exact).
PA_PER_BAR = 1.0e5
#: Offset between Celsius and Kelvin (exact).
K_OFFSET = 273.15
#: Seconds per day.
S_PER_DAY = 86_400.0
#: Seconds per hour.
S_PER_HOUR = 3_600.0
#: Cubic metres per oil-field barrel (42 US gal, exact definition).
M3_PER_BBL = 0.158987294928
#: Pa.s per centipoise (exact).
PAS_PER_CP = 1.0e-3
#: Kv per Cv. Kv [m3/h, bar, SG=1] = 0.865 * Cv [US gpm, psi, SG=1]
#: (IEC 60534 / ISA-75.01 convention, commonly quoted as 0.865).
KV_PER_CV = 0.865
#: Reference density of water used in Kv/Cv definitions [kg/m3].
RHO_WATER_REF = 1000.0


# --- pressure ----------------------------------------------------------------
def bara_to_pa(p_bara: float) -> float:
    return p_bara * PA_PER_BAR


def pa_to_bara(p_pa: float) -> float:
    return p_pa / PA_PER_BAR


def barg_to_pa(p_barg: float) -> float:
    """Gauge (relative to standard atmosphere) -> absolute Pa."""
    return p_barg * PA_PER_BAR + P_ATM


def pa_to_barg(p_pa: float) -> float:
    """Absolute Pa -> gauge bar relative to standard atmosphere."""
    return (p_pa - P_ATM) / PA_PER_BAR


def bar_to_pa_delta(dp_bar: float) -> float:
    """Pressure DIFFERENCE in bar -> Pa (no reference offset)."""
    return dp_bar * PA_PER_BAR


def pa_to_bar_delta(dp_pa: float) -> float:
    return dp_pa / PA_PER_BAR


# --- temperature -------------------------------------------------------------
def c_to_k(t_c: float) -> float:
    return t_c + K_OFFSET


def k_to_c(t_k: float) -> float:
    return t_k - K_OFFSET


# --- flow --------------------------------------------------------------------
def m3d_to_m3s(q_m3d: float) -> float:
    return q_m3d / S_PER_DAY


def m3s_to_m3d(q_m3s: float) -> float:
    return q_m3s * S_PER_DAY


def m3s_to_bbld(q_m3s: float) -> float:
    return q_m3s * S_PER_DAY / M3_PER_BBL


# --- productivity index ------------------------------------------------------
def pi_m3d_per_bar_to_si(j: float) -> float:
    """Productivity index (m3/d)/bar -> (m3/s)/Pa."""
    return j / S_PER_DAY / PA_PER_BAR


def pi_si_to_m3d_per_bar(j_si: float) -> float:
    return j_si * S_PER_DAY * PA_PER_BAR


# --- viscosity ---------------------------------------------------------------
def cp_to_pas(mu_cp: float) -> float:
    return mu_cp * PAS_PER_CP


def pas_to_cp(mu_pas: float) -> float:
    return mu_pas / PAS_PER_CP


# --- restriction capacity ----------------------------------------------------
# All restrictions are reduced to an effective flow capacity C = Cd*A [m2] in
#     Q = C * sqrt(2 * dP / rho)
def kv_to_capacity(kv: float) -> float:
    """Kv [m3/h at 1 bar dP, SG=1] -> effective Cd*A [m2].

    Kv definition: Q[m3/h] = Kv * sqrt(dP[bar] / SG), SG = rho / 1000.
    In SI: Q = Kv/3600 * sqrt(dP/1e5 * 1000/rho) = C * sqrt(2 dP / rho)
    =>  C = Kv/3600 * sqrt(1000 / (2 * 1e5)).
    """
    return kv / S_PER_HOUR * math.sqrt(RHO_WATER_REF / (2.0 * PA_PER_BAR))


def cv_to_capacity(cv: float) -> float:
    return kv_to_capacity(cv * KV_PER_CV)


def loss_coefficient_to_capacity(k: float, bore_diameter_m: float) -> float:
    """Resistance coefficient K (dP = K rho v^2 / 2, v in bore) -> Cd*A [m2].

    dP = K rho Q^2 / (2 A^2)  =>  C = A / sqrt(K).
    """
    if k <= 0:
        raise ValueError("loss coefficient must be positive")
    area = math.pi * bore_diameter_m**2 / 4.0
    return area / math.sqrt(k)
