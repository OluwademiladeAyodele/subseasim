"""Choke erosion physics (DNV-RP-O501-style particle erosion).

Generic particle erosion (DNV-RP-O501, Sand erosion in pipes and production
equipment; edition used for the constants below: 2015, constants to be
verified against the user's licensed copy / vendor data):

    E_m = K U_p^n F(alpha)          [kg of target material per kg of sand]

    ductile (steels, CRA):  F = 0.6 [sin a + 7.2 (sin a - sin^2 a)]^0.6 [1 - exp(-20 a)]
    brittle (tungsten carbide, ceramics): F = 2 a / pi  (linear approximation)

Particle velocity U_p is the choke jet velocity at the vena contracta of the
throttling cage holes, from the Sachdeva multiphase choke solution already
used for the flow (U = W / (C_dA rho_m2)); for a liquid this is
sqrt(2 dP / rho). The material removed per kg of sand is distributed over
the OPEN cage holes in proportion to their flow (open area) and to the plug
edge (configurable share); hole diameters grow by
    d(d) = 2 dV / (pi d t_wall),
and the eroded open area raises the choke Cv (Cv proportional to open area).

Downstream (outlet) wall: DNV straight-pipe model
    E_L [mm/year] = 2.5e-5 U^2.6 D^-2 m_p          (steel, U m/s, D m, m_p kg/s)
Body / gallery: generic impingement on the projected inlet-jet area
(screening).

A calibration factor C (log-normal, prior median 1) multiplies the trim
material loss; inspections update it (see app/simulation/sand/system.py).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from app.models.sand import ChokeTrimInputs, CustomMaterial

S_PER_YEAR = 365.25 * 86400.0


@dataclass(frozen=True)
class Material:
    key: str
    name: str
    k: float
    n: float
    density: float
    behaviour: str  # ductile / brittle
    source: str


#: DNV-RP-O501 (2015) Table 3-1 style constants. VERIFY against the licensed
#: document / vendor data before engineering use (values are reproduced for
#: training and are editable as custom materials).
MATERIALS: dict[str, Material] = {
    "carbon_steel": Material("carbon_steel", "Carbon / low-alloy steel", 2.0e-9, 2.6, 7800, "ductile", "DNV-RP-O501 (verify)"),
    "stainless_duplex": Material("stainless_duplex", "Duplex / stainless steel", 2.0e-9, 2.6, 7850, "ductile", "DNV-RP-O501 (verify)"),
    "inconel": Material("inconel", "Inconel (nickel alloy, CRA)", 2.53e-9, 2.6, 8440, "ductile", "DNV-RP-O501 (verify)"),
    "tungsten_carbide_dc05": Material("tungsten_carbide_dc05", "Tungsten carbide DC-05", 1.1e-10, 2.3, 15250, "brittle", "DNV-RP-O501 (verify)"),
    "tungsten_carbide_cs10": Material("tungsten_carbide_cs10", "Tungsten carbide CS-10", 3.5e-10, 2.2, 14800, "brittle", "DNV-RP-O501 (verify)"),
    "tungsten_carbide_cr37": Material("tungsten_carbide_cr37", "Tungsten carbide CR-37", 8.8e-11, 2.5, 14600, "brittle", "DNV-RP-O501 (verify)"),
}


def material(key: str | None, custom: list[CustomMaterial]) -> Material | None:
    if key is None:
        return None
    for c in custom:
        if c.name == key:
            return Material(c.name, c.name, c.k, c.n, c.density_kg_m3, c.behaviour, "custom (user input)")
    return MATERIALS.get(key)


def f_alpha(alpha_rad: float, behaviour: str) -> float:
    if behaviour == "brittle":
        return 2.0 * alpha_rad / math.pi
    s = math.sin(alpha_rad)
    return 0.6 * (s + 7.2 * (s - s * s)) ** 0.6 * (1 - math.exp(-20 * alpha_rad))


def erosion_ratio(mat: Material, u: float, alpha_deg: float) -> float:
    """kg target material removed per kg of sand."""
    return mat.k * max(u, 0.0) ** mat.n * f_alpha(math.radians(alpha_deg), mat.behaviour)


def outlet_wall_rate_mm_y(u: float, d_m: float, m_sand_kg_s: float) -> float:
    """DNV straight-pipe model (steel)."""
    return 2.5e-5 * max(u, 0.0) ** 2.6 * d_m**-2 * max(m_sand_kg_s, 0.0)


def impingement_rate_m_s(mat: Material, u: float, m_sand: float, area_m2: float, alpha_deg: float = 90.0) -> float:
    """Wall-thickness loss rate for a jet impinging over ``area_m2``."""
    return erosion_ratio(mat, u, alpha_deg) * max(m_sand, 0.0) / (mat.density * max(area_m2, 1e-9))


# ------------------------------------------------------------ cage geometry
def _segment_area(r: float, h: float) -> float:
    """Area of a circle of radius r uncovered to chord height h (0..2r)."""
    if h <= 0:
        return 0.0
    if h >= 2 * r:
        return math.pi * r * r
    return r * r * math.acos((r - h) / r) - (r - h) * math.sqrt(max(2 * r * h - h * h, 0.0))


class CageGeometry:
    """Plug & multi-hole cage: open hole area vs plug lift; per-row wear."""

    def __init__(self, c: ChokeTrimInputs):
        self.c = c
        self.rows = sorted(c.hole_rows, key=lambda r: r.axial_position_mm)
        self.d0 = np.array([r.diameter_mm * 1e-3 for r in self.rows])
        self.z = np.array([r.axial_position_mm * 1e-3 for r in self.rows])
        self.n = np.array([r.count for r in self.rows], dtype=float)
        self.stroke = (c.stroke_mm or 0) * 1e-3

    @property
    def valid(self) -> bool:
        return bool(self.rows) and self.stroke > 0 and (self.c.cage_wall_thickness_mm or 0) > 0

    def open_areas(self, position_pct: float, dd: np.ndarray | None = None) -> np.ndarray:
        """Open area of each row [m2] at an opening, with hole growth dd [m]."""
        lift = self.stroke * min(max(position_pct, 0.0), 100.0) / 100.0
        d = self.d0 + (dd if dd is not None else 0.0)
        out = np.empty(len(self.rows))
        for i in range(len(self.rows)):
            r = d[i] / 2
            # hole centre at z; plug edge at lift uncovers from the bottom of the hole
            h = lift - (self.z[i] - r)
            out[i] = self.n[i] * _segment_area(r, h)
        return out

    def wear_factor(self, position_pct: float, dd: np.ndarray) -> float:
        a0 = self.open_areas(position_pct).sum()
        if a0 <= 0:
            return 1.0
        return float(self.open_areas(position_pct, dd).sum() / a0)

    def distribute(self, volume_m3: float, position_pct: float, dd: np.ndarray) -> np.ndarray:
        """Hole-diameter growth of each row for a trim material volume removed
        at the cage holes, shared in proportion to each row's open area."""
        a = self.open_areas(position_pct, dd)
        tot = a.sum()
        if tot <= 0 or volume_m3 <= 0:
            return np.zeros(len(self.rows))
        t = (self.c.cage_wall_thickness_mm or 1.0) * 1e-3
        d = self.d0 + dd
        share = a / tot
        v_hole = volume_m3 * share / np.maximum(self.n, 1)
        return 2 * v_hole / (math.pi * d * t)


#: 1 lb/ft3 in kg/m3 and 1 ft in m (exact definitions).
LB_FT3 = 0.45359237 / 0.3048**3
FT = 0.3048


def api14e_erosional_velocity(rho_mix_kg_m3: float, c_factor: float) -> float:
    """API RP 14E erosional velocity  Ve = C / sqrt(rho_m)  (Ve ft/s, rho_m lb/ft3),
    returned in m/s for a mixture density in kg/m3. A SCREENING indicator for
    clean (solids-free) service only - not a sand-erosion or choke model."""
    return c_factor / math.sqrt(rho_mix_kg_m3 / LB_FT3) * FT


def jet_velocity(p1: float, p2: float, w: float, cda: float, rho_l: float, rho_g: float, x: float, k: float,
                 y_crit: float) -> float:
    """Mixture velocity at the vena contracta of the choke [m/s] (Sachdeva)."""
    if w <= 0 or cda <= 0:
        return 0.0
    y = max(p2 / max(p1, 1.0), y_crit)
    v_g1 = 1.0 / max(rho_g, 1e-6)
    v_g2 = v_g1 * max(y, 1e-6) ** (-1.0 / k) if x > 0 else 0.0
    rho_m2 = 1.0 / (x * v_g2 + (1 - x) / rho_l) if x > 0 else rho_l
    return w / (cda * rho_m2)
