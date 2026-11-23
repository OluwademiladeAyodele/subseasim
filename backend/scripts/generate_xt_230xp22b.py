"""Generates the XT workstation scenario and its schematic layout (run from backend/).

    python scripts/generate_xt_230xp22b.py

Outputs
    app/scenarios/data/xt_230xp22b.json      engineering configuration
    app/scenarios/layouts/xt_230xp22b.json   schematic layout (positions only)

The engineering configuration starts from the dynamic base scenario
(generate_subsea_dynamic_base.py) and applies the topology shown on the
reference control-system page "Production 230XP22B" (photograph supplied by
the user): crossover valve from the annulus service-line junction into the
tree cavity, chemical injection into the production wing upstream of PWV,
two methanol injection valves (upstream and downstream of PWV), downhole
chemical injection below the SCSSV, A/B SCM hydraulic headers with selector
valves. Tags are plain engineering tags (PMV-101, PT-104, HSV-101), not the
reference numbering.

Every schematic coordinate is entered in PHOTO PIXELS (as measured on the
supplied 810 x 1080 px photograph, keystone-straightened so verticals are
vertical) and mapped with X = (px - 20) * 2.6, Y = (py - 40) * 2.6. See
docs/CHRISTMAS_TREE_LAYOUT.md for the measurement table and uncertainties.
"""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("dynbase", HERE / "generate_subsea_dynamic_base.py")
dynbase = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dynbase)  # type: ignore[union-attr]

sc = copy.deepcopy(dynbase.scenario)

# ======================================================================
# Engineering configuration
# ======================================================================
sc["id"] = "xt_230xp22b"
sc["name"] = "XT workstation - Production 230XP22B layout (illustrative)"
sc["description"] = (
    "Dynamic subsea producer arranged as on the reference control-system page 'Production 230XP22B': production bore with "
    "SCSSV, PMV and the production wing (PWV) ending in the production choke CHK-101; A-annulus with AMV, AWV, crossover "
    "XOV into the tree cavity and the annulus service line valve SLV; chemical injection into the production wing; two "
    "methanol injection valves either side of PWV; downhole chemical injection; SCM A/B hydraulic headers with selector "
    "valves (fail-safe closure on loss of supply). The photograph defines the ARCHITECTURE only: every reading is calculated by the simulator from the configured reservoir, fluid, boundary and valve inputs. All data "
    "are ILLUSTRATIVE training values."
)
sc["schematic"] = "xt_230xp22b"

sub = sc["subsystems"]
nodes = {n["id"]: n for n in sub["nodes"]}
elems = {e["id"]: e for e in sub["elements"]}


def drop(ids: set[str]) -> None:
    sub["nodes"][:] = [n for n in sub["nodes"] if n["id"] not in ids]
    sub["elements"][:] = [e for e in sub["elements"] if e["id"] not in ids]
    sub["boundaries"][:] = [b for b in sub["boundaries"] if b["node"] not in ids]
    sub["instruments"][:] = [i for i in sub["instruments"] if i["tag"] not in ids]


# --- topology as on the reference -----------------------------------------
# XOV-101 connects the service-line junction (downstream of AWV) to the tree
# cavity - on the reference the crossover line leaves the service line
# between AWV's branch and the bore.
elems["XOV"]["from"] = "N_ANN_SVC"
elems["XOV"]["name"] = "Crossover valve (annulus service-line junction to tree cavity)"

# Methanol route into the annulus service line is not on the reference page.
drop({"SUP_MEOH_ANN", "N_MIV_IN", "N_MIV_A", "CL-305", "MIV301", "NRV305", "FT-305"})

# Chemical injection points: the reference shows CIV-302 / CIV-303 / CIV-301
# lines joining the production wing between the bore and PWV.
for num in (302, 303):
    elems[f"NRV{num}"]["to"] = "N_PMV_PWV"
# Downhole chemical line joins the bore below the SCSSV on the reference.
elems["NRV304"]["to"] = "N_SCSSV_U"
_inj_node = {"corrosion_inhibitor": "N_PMV_PWV", "biocide": "N_PMV_PWV", "wax_inhibitor": "N_SCSSV_U"}
for c in sc["chemicals"]:
    c["injection_node"] = _inj_node.get(c["id"], c["injection_node"])

# Two methanol injection valves fed from one methanol header: MIV-302 into the
# wing upstream of PWV, MIV-303 between PWV and the choke.
sub["nodes"] += [
    {"id": "SUP_MEOH_MIV", "name": "Methanol to MIV header: SDU supply", "elevation_m": -1150, "zone": "methanol"},
    {"id": "N_MIV_HDR", "name": "Methanol MIV header at tree", "elevation_m": -1195, "zone": "methanol"},
    {"id": "N_MIV1_A", "name": "Methanol: downstream of MIV-302", "elevation_m": -1195, "zone": "methanol"},
    {"id": "N_MIV2_A", "name": "Methanol: downstream of MIV-303", "elevation_m": -1195, "zone": "methanol"},
]
sub["boundaries"].append({"node": "SUP_MEOH_MIV", "pressure_bara": 250, "description": "Methanol pump discharge (MIV header) at the SDU"})
_miv = dict(type="valve", valve_type="injection_isolation", bore_diameter_m=0.01, loss_coefficient_open=2.0,
            full_stroke_time_s=10, actuation_delay_s=2, nominal_stroke_time_s=12, initial_position_pct=0)
sub["elements"] += [
    {"id": "CL-306", "type": "pipe", "role": "injection_line", "name": "Methanol line to MIV header (12.7 mm, 5 km)",
     "from": "SUP_MEOH_MIV", "to": "N_MIV_HDR", "length_m": 5000, "inner_diameter_m": 0.0127, "roughness_m": 1.5e-6,
     "hydraulic_segments": 5},
    {"id": "MIV302", "tag": "MIV-302", "name": "Methanol injection valve (wing, upstream of PWV)", "from": "N_MIV_HDR", "to": "N_MIV1_A", **_miv},
    {"id": "NRV306", "type": "check_valve", "tag": "NRV-306", "name": "Methanol non-return valve (wing, upstream of PWV)",
     "from": "N_MIV1_A", "to": "N_PMV_PWV", "cracking_pressure_bar": 0.5, "cv": 0.2},
    {"id": "MIV303", "tag": "MIV-303", "name": "Methanol injection valve (between PWV and choke)", "from": "N_MIV_HDR", "to": "N_MIV2_A", **_miv},
    {"id": "NRV307", "type": "check_valve", "tag": "NRV-307", "name": "Methanol non-return valve (between PWV and choke)",
     "from": "N_MIV2_A", "to": "N_UC", "cracking_pressure_bar": 0.5, "cv": 0.2},
]
meoh = next(c for c in sc["chemicals"] if c["id"] == "methanol")
for k in ("annulus_supply_node", "annulus_valve", "annulus_check_valve", "annulus_flow_transmitter"):
    meoh.pop(k, None)
meoh["routes"] = [
    {"id": "miv_up", "name": "MIV-302 - production wing upstream of PWV", "supply_node": "SUP_MEOH_MIV", "valve": "MIV-302",
     "check_valve": "NRV-306", "injection_node": "N_PMV_PWV", "flow_transmitter": "FT-306"},
    {"id": "miv_dn", "name": "MIV-303 - between PWV and the production choke", "supply_node": "SUP_MEOH_MIV", "valve": "MIV-303",
     "check_valve": "NRV-307", "injection_node": "N_UC", "flow_transmitter": "FT-307"},
]

# --- initial state ----------------------------------------------------------
# The photograph is used for the ARCHITECTURE only (component arrangement and
# connectivity). Readings shown on it are NOT reproduced: initial valve
# positions, pressures and temperatures come from the scenario's own
# engineering inputs (reservoir, fluid, boundary, valve line-up) and every
# transmitter value is calculated by the simulator. Normal producing line-up:
# SCSSV, PMV, PWV open, choke throttling, annulus isolated (AMV, AWV, XOV
# closed), service line valve open to the host bleed header.
sc["element_overrides"]["CHOKE"] = {"actuation_delay_s": 1}

# --- instruments added for the reference transmitters ---------------------
sub["instruments"] += [
    {"tag": "TT-104", "type": "temperature", "description": "Tree cavity temperature", "node": "N_PMV_PWV", "range_min": 0, "range_max": 150},
    {"tag": "PT-107", "type": "pressure", "description": "Production wing pressure upstream of PWV", "node": "N_PMV_PWV", "range_min": 0, "range_max": 690},
    {"tag": "TT-107", "type": "temperature", "description": "Production wing temperature upstream of PWV", "node": "N_PMV_PWV", "range_min": 0, "range_max": 150},
    {"tag": "PT-002", "type": "pressure", "description": "Downhole gauge B pressure", "node": "N_BH", "range_min": 0, "range_max": 690},
    {"tag": "TT-002", "type": "temperature", "description": "Downhole gauge B temperature", "node": "N_BH", "range_min": 0, "range_max": 150},
    {"tag": "PT-106", "type": "pressure", "description": "Production line pressure downstream of choke, 30 m", "element": "FL-101", "distance_m": 30, "range_min": 0, "range_max": 690},
    {"tag": "TT-106", "type": "temperature", "description": "Production line temperature downstream of choke, 30 m", "element": "FL-101", "distance_m": 30, "range_min": 0, "range_max": 150},
    {"tag": "PT-404", "type": "pressure", "description": "Annulus service-line junction pressure, upstream of SLV", "node": "N_ANN_SVC", "range_min": 0, "range_max": 690},
    {"tag": "PDT-401", "type": "differential_pressure", "description": "Differential pressure across the service line valve SLV", "high_node": "N_ANN_SVC", "low_node": "N_SVC_L", "range_min": -350, "range_max": 350},
    {"tag": "FT-306", "type": "flow", "description": "Methanol flow through MIV-302 (wing, upstream of PWV)", "element": "MIV302", "range_min": 0, "range_max": 120},
    {"tag": "FT-307", "type": "flow", "description": "Methanol flow through MIV-303 (between PWV and choke)", "element": "MIV303", "range_min": 0, "range_max": 120},
]

# --- control hydraulics (selector valves on the reference) ----------------
LP_VALVES = ["PMV-101", "PWV-101", "AMV-101", "AWV-101", "XOV-101", "SLV-101", "SV-101",
             "CIV-301", "CIV-302", "CIV-303", "CIV-304", "MIV-302", "MIV-303",
             "CHK-101", "CIMV-301", "CIMV-302", "CIMV-303", "CIMV-304"]
sc["control_hydraulics"] = {
    "supplies": [
        {"id": "LP", "name": "LP", "tag": "PT-601", "pressure_bara": 207, "minimum_operating_pressure_bara": 110},
        {"id": "HP", "name": "HP", "tag": "PT-602", "pressure_bara": 517, "minimum_operating_pressure_bara": 300},
    ],
    "headers": [
        {"id": "LP-A", "name": "LP header SCM A", "tag": "PT-611", "supply": "LP", "scm": "A"},
        {"id": "LP-B", "name": "LP header SCM B", "tag": "PT-612", "supply": "LP", "scm": "B"},
        {"id": "HP-A", "name": "HP header SCM A", "tag": "PT-621", "supply": "HP", "scm": "A"},
        {"id": "HP-B", "name": "HP header SCM B", "tag": "PT-622", "supply": "HP", "scm": "B"},
    ],
    "selector_valves": [
        {"tag": "HSV-101", "name": "LP selector valve to SCM A", "header": "LP-A"},
        {"tag": "HSV-102", "name": "LP selector valve to SCM B", "header": "LP-B"},
        {"tag": "HSV-103", "name": "HP selector valve to SCM A", "header": "HP-A"},
        {"tag": "HSV-104", "name": "HP selector valve to SCM B", "header": "HP-B"},
    ],
    "valve_supply": {**{t: "LP" for t in LP_VALVES}, "SCSSV-101": "HP"},
    "fail_safe_close": [t for t in LP_VALVES if not t.startswith(("CHK", "CIMV"))] + ["SCSSV-101"],
}

# --- three-phase black-oil fluid (used by the multiphase variant) -----------
sc["black_oil"] = {
    "name": "Illustrative light oil with associated gas and produced water",
    "oil_api": 35.0, "gas_specific_gravity": 0.75, "producing_gor_sm3_sm3": 120.0, "water_cut_fraction": 0.30,
    "water_salinity_wt_pct": 3.5, "correlation": "beggs_brill",
}

# --- multiphase flow meter on the manifold (three-phase model) -------------
sc["mpfm"] = {"tag": "MPFM-201", "name": "Manifold multiphase flow meter", "location_node": "N_ARR",
              "inlet_diameter_m": 0.1016, "beta": 0.5, "discharge_coefficient": 0.995}

# --- sand & choke inputs ---------------------------------------------------
# Known data supplied by the operator: completion (cased, perforated, standalone
# sand screens) and the production choke (plug & multi-hole cage, max Cv 161, min
# controllable Cv 1.61, 165-step hydraulic stepping actuator). Everything else is
# left EMPTY: predictions stay unavailable until the site data are entered.
sc["sand_choke"] = {
    "completion": {"completion_type": "cased_perforated_standalone_screens"},
    "choke": {"design": "plug_and_cage", "model_label": "Plug & multi-hole cage choke (F500)", "max_cv": 161.0,
              "min_controllable_cv": 1.61, "actuator_steps": 165, "erosion_feedback": True},
    "detector": {"tag": "SDT-101"},
}
# Complete ILLUSTRATIVE set (NOT field data) so training can run before site data exist.
sc["sand_choke_example"] = {
    "geomechanics": {"depth_tvd_m": 3700, "overburden_gradient_bar_m": 0.18, "min_horizontal_stress_gradient_bar_m": 0.15,
                     "max_horizontal_stress_gradient_bar_m": 0.16, "initial_reservoir_pressure_bara": 380, "stress_path_coefficient": 0.6,
                     "twc_strength_mpa": 27.0, "biot_coefficient": 0.9, "poisson_ratio": 0.25, "water_weakening_fraction": 0.3,
                     "porosity": 0.27, "permeability_md": 800},
    "completion": {"completion_type": "cased_perforated_standalone_screens", "perforation_diameter_mm": 18, "shot_density_spm": 40,
                   "perforated_interval_m": 30, "screen_type": "premium_mesh", "screen_aperture_um": 250, "bridging_factor": 2.0},
    "sand": {"grain_density_kg_m3": 2650, "d10_um": 60, "d50_um": 150, "d90_um": 300, "mode": "predictive",
             "rate_coefficient_kg_m3": 0.05, "rate_exponent": 1.5, "measured_unit": "kg_d"},
    "detector": {"tag": "SDT-101"},
    "cavitation": {"fl_table": [{"opening_pct": 10, "fl": 0.95}, {"opening_pct": 50, "fl": 0.9}, {"opening_pct": 100, "fl": 0.85}],
                   "fl_source": "ILLUSTRATIVE - replace with the manufacturer's FL for this trim",
                   "sigma_incipient": 2.0, "sigma_constant": 1.7, "sigma_damage": 1.4,
                   "threshold_source": "ILLUSTRATIVE - replace with the manufacturer's sigma limits for this trim"},
    "choke": {"design": "plug_and_cage", "model_label": "Plug & multi-hole cage choke (F500) - ILLUSTRATIVE geometry",
              "max_cv": 161.0, "min_controllable_cv": 1.61, "actuator_steps": 165, "stroke_mm": 60, "cage_inner_diameter_mm": 90,
              "cage_wall_thickness_mm": 12, "plug_diameter_mm": 90, "choke_outlet_bore_mm": 127, "gallery_diameter_mm": 127,
              "body_wall_thickness_mm": 25, "trim_material": "tungsten_carbide_cs10", "body_material": "inconel",
              "trim_impact_angle_deg": 30, "plug_share": 0.3, "erosion_feedback": True,
              "hole_rows": [{"axial_position_mm": 3, "diameter_mm": 4, "count": 4}, {"axial_position_mm": 8, "diameter_mm": 5, "count": 4},
                            {"axial_position_mm": 14, "diameter_mm": 6, "count": 6}, {"axial_position_mm": 21, "diameter_mm": 8, "count": 6},
                            {"axial_position_mm": 30, "diameter_mm": 10, "count": 8}, {"axial_position_mm": 41, "diameter_mm": 12, "count": 8},
                            {"axial_position_mm": 53, "diameter_mm": 12, "count": 8}]},
    "acceptance": {"max_hole_diameter_increase_mm": 1.5, "max_cv_increase_pct": 15, "max_plug_loss_mm": 2.0,
                   "max_body_wall_loss_mm": 3.0, "max_outlet_wall_loss_mm": 3.0, "reference_step": 82},
}

# --- tags: plain engineering tags everywhere (no reference-HMI aliases) ------
sc["tag_aliases"] = {}

sc["briefing"] = [
    "This page follows the arrangement of the reference control-system page 'Production 230XP22B', with SubseaSim engineering tags.",
    "Every reading is calculated by the simulator from the inputs on the Conditions page (reservoir pressure, temperature, productivity, fluid, downstream pressure) and the valve positions - change them and watch the transmitters respond.",
    "Try closing PWV-101: the tree cavity (PTT-104 / PTT-107) builds toward shut-in pressure while the choke outlet (PTT-103 / PTT-106) falls toward flowline pressure.",
    "Selector valves route the LP and HP hydraulic supplies to SCM A and B. Close both LP selector valves and watch PT-611 / PT-612 bleed down until the fail-safe valves close.",
    "Open MIV-302 (upstream of PWV) or MIV-303 (between PWV and the choke) to inject methanol into the production stream; the concentration is tracked downstream.",
]

# --- process-view layout (full system page) for the changed topology -------
lay = sc["layout"]
lay["waypoints"]["XOV"] = []
lay["waypoints"]["NRV304"] = [dynbase.P(560, 612)]
lay["nodes"].update({
    "SUP_MEOH_MIV": dynbase.P(700, 48), "N_MIV_HDR": dynbase.P(700, 90),
    "N_MIV1_A": dynbase.P(640, 150), "N_MIV2_A": dynbase.P(760, 150),
})
for k in ("SUP_MEOH_ANN", "N_MIV_IN", "N_MIV_A"):
    lay["nodes"].pop(k, None)
lay["instruments"].pop("FT-305", None)
lay["instruments"].update({
    "FT-306": dynbase.P(620, 95), "FT-307": dynbase.P(800, 95),
    "PT-404": dynbase.P(420, 140), "PDT-401": dynbase.P(300, 225),
})
lay["annotations"] = [a for a in lay["annotations"] if not (a.get("type") == "connector" and a.get("label") == "MeOH (SDU)" and a.get("y") == 48)]
lay["annotations"].append({"type": "connector", "x": 700, "y": 48, "direction": "up", "label": "MeOH to MIVs (SDU)"})

# ======================================================================
# Schematic layout (positions only)
# ======================================================================
X0, Y0, S = 20.0, 40.0, 2.6


def p(px: float, py: float) -> list[float]:
    return [round((px - X0) * S, 1), round((py - Y0) * S, 1)]


def pts(*xy: tuple[float, float]) -> list[list[float]]:
    return [p(*q) for q in xy]


def box(px0: float, py0: float, px1: float, py1: float) -> dict:
    a, b = p(px0, py0), p(px1, py1)
    return {"x": a[0], "y": a[1], "w": round(b[0] - a[0], 1), "h": round(b[1] - a[1], 1)}


def comp(cid: str, ctype: str, model: str | None, at: tuple[float, float], rotation: float = 0, label=None, **kw) -> dict:
    x, y = p(*at)
    d = {"id": cid, "type": ctype, "model": model, "x": x, "y": y, "rotation": rotation}
    if label is not None:
        d["label"] = {"dx": round(label[0] * S, 1), "dy": round(label[1] * S, 1), "anchor": label[2] if len(label) > 2 else "middle"}
    d.update(kw)
    return d


def valve(cid, ctype, element, at, rotation=0, label=(0, -15), flow_path=None, half=4.0):
    """Valve with a/b ports ``half`` photo-px either side along the flow direction."""
    x, y = at
    if rotation == 90:
        ports = {"a": p(x, y - half), "b": p(x, y + half)}
    else:
        ports = {"a": p(x - half, y), "b": p(x + half, y)}
    return comp(cid, ctype, f"element:{element}", at, rotation, label, ports=ports, flow_path=flow_path)


def panel(cid, models, b, tap=None, flow_path=None, group=None, note=""):
    d = {"id": cid, "type": "tag_panel", "model": None, "models": models, **box(*b), "rotation": 0}
    if tap is not None:
        d["tap"] = p(*tap)
    if flow_path:
        d["flow_path"] = flow_path
    if group:
        d["group"] = group
    if note:
        d["note"] = note
    return d


BORE, ANN, WING, CHKX = 233, 202, 145, 481

lines = [
    # production (maroon on the reference)
    {"id": "bore-cap", "cls": "production", "points": pts((BORE, 86), (BORE, WING)), "elements": ["SV"]},
    {"id": "bore-cavity", "cls": "production", "points": pts((BORE, WING), (BORE, 279)), "elements": ["PMV"]},
    {"id": "bore-upper-tubing", "cls": "production", "points": pts((BORE, 279), (BORE, 326)), "elements": ["TBG-UPPER"]},
    {"id": "bore-lower-tubing", "cls": "production", "points": pts((BORE, 326), (BORE, 446)), "elements": ["TBG-LOWER"]},
    {"id": "wing", "cls": "production", "points": pts((BORE, WING), (CHKX, WING)), "elements": ["PWV"],
     "from_ref": "PMV.a", "to_ref": "CHOKE.a"},
    {"id": "choke-outlet", "cls": "production", "points": pts((CHKX, WING), (CHKX, 292), (585, 292), (585, 318)), "elements": ["CHOKE", "FL-101"]},
    {"id": "flowline", "cls": "production", "points": pts((585, 318), (585, 330)), "elements": ["FL-101"]},
    # annulus (teal on the reference)
    {"id": "annulus-cap", "cls": "annulus", "points": pts((ANN, 86), (ANN, 139)), "elements": []},
    {"id": "annulus-cavity", "cls": "annulus", "points": pts((ANN, 139), (ANN, 279)), "elements": ["AMV"]},
    {"id": "annulus-a", "cls": "annulus", "points": pts((ANN, 279), (ANN, 446)), "elements": ["ANN-A"]},
    {"id": "awv-branch", "cls": "annulus", "points": pts((ANN, 139), (144, 139), (144, 196)), "elements": ["AWV"]},
    {"id": "service-line", "cls": "service", "points": pts((144, 196), (34, 196)), "elements": ["SLV"]},
    {"id": "xov-annulus-side", "cls": "service", "points": pts((144, 196), (171, 196)), "elements": ["XOV"]},
    {"id": "xov-production-side", "cls": "production", "points": pts((171, 196), (BORE, 196)), "elements": ["XOV"]},
    # chemical injection into the production wing (upper right)
    {"id": "chem-ci", "cls": "chemical", "chemical": "corrosion_inhibitor", "points": pts((405, 176), (301, 176), (301, WING)), "elements": ["CIV302"]},
    {"id": "chem-bio", "cls": "chemical", "chemical": "biocide", "points": pts((405, 203), (285, 203), (285, WING)), "elements": ["CIV303"]},
    {"id": "chem-meoh", "cls": "chemical", "chemical": "methanol", "points": pts((405, 232), (277, 232), (277, WING)), "elements": ["CIV301"]},
    {"id": "miv-header", "cls": "methanol", "chemical": "methanol", "points": pts((350, 300), (350, 265)), "elements": ["MIV302", "MIV303"]},
    {"id": "miv-up", "cls": "methanol", "chemical": "methanol", "points": pts((350, 265), (425, 265), (425, WING)), "elements": ["MIV302"]},
    {"id": "miv-dn", "cls": "methanol", "chemical": "methanol", "points": pts((350, 290), (455, 290), (455, WING)), "elements": ["MIV303"]},
    # downhole chemical line (lower left)
    {"id": "chem-downhole", "cls": "downhole_chemical", "chemical": "wax_inhibitor", "points": pts((64, 356), (226, 356), (BORE, 363)), "elements": ["CIV304"]},
    # control hydraulics (selector valves box)
    {"id": "hyd-lp-supply", "cls": "hydraulic", "points": pts((427, 346), (449, 346)), "elements": [], "model": "supply:LP"},
    {"id": "hyd-lp-branch", "cls": "hydraulic", "points": pts((449, 326), (449, 364)), "elements": [], "model": "supply:LP"},
    {"id": "hyd-lp-a", "cls": "hydraulic", "points": pts((449, 326), (500, 326)), "elements": [], "model": "header:LP-A"},
    {"id": "hyd-lp-b", "cls": "hydraulic", "points": pts((449, 364), (500, 364)), "elements": [], "model": "header:LP-B"},
    {"id": "hyd-hp-supply", "cls": "hydraulic", "points": pts((427, 417), (449, 417)), "elements": [], "model": "supply:HP"},
    {"id": "hyd-hp-branch", "cls": "hydraulic", "points": pts((449, 397), (449, 433)), "elements": [], "model": "supply:HP"},
    {"id": "hyd-hp-a", "cls": "hydraulic", "points": pts((449, 397), (500, 397)), "elements": [], "model": "header:HP-A"},
    {"id": "hyd-hp-b", "cls": "hydraulic", "points": pts((449, 433), (500, 433)), "elements": [], "model": "header:HP-B"},
]

components = [
    # --- tree valves
    valve("SV", "swab_valve", "SV", (BORE, 112), 90, label=(8, 0, "start"), flow_path="bore-cap"),
    valve("PMV", "master_valve", "PMV", (BORE, 279), 90, label=(9, 1, "start"), flow_path="bore-cavity"),
    valve("SCSSV", "scssv", "SCSSV", (BORE, 326), 90, label=(9, 1, "start"), flow_path="bore-upper-tubing"),
    valve("PWV", "wing_valve", "PWV", (441, WING), 0, label=(0, -13), flow_path="wing"),
    comp("CHOKE", "choke", "element:CHOKE", (CHKX, WING), 0, None, ports={"a": p(CHKX - 6, WING), "b": p(CHKX, WING + 8)}, flow_path="choke-outlet"),
    valve("AMV", "annulus_valve", "AMV", (ANN, 279), 90, label=(-9, 1, "end"), flow_path="annulus-cavity"),
    valve("AWV", "annulus_valve", "AWV", (165, 139), 0, label=(0, -13), flow_path="awv-branch"),
    valve("XOV", "crossover_valve", "XOV", (171, 196), 0, label=(0, -13), flow_path="xov-annulus-side"),
    valve("SLV", "service_line_valve", "SLV", (82, 196), 0, label=(0, -13), flow_path="service-line"),
    # --- chemical injection (upper right)
    valve("CIV302", "injection_valve", "CIV302", (315, 176), 0, label=(14, -8, "start"), flow_path="chem-ci"),
    valve("CIMV302", "metering_valve", "CIMV302", (375, 176), 0, label=(0, -12), flow_path="chem-ci"),
    valve("CIV303", "injection_valve", "CIV303", (316, 203), 0, label=(14, -8, "start"), flow_path="chem-bio"),
    valve("CIMV303", "metering_valve", "CIMV303", (375, 203), 0, label=(0, -9), flow_path="chem-bio"),
    valve("CIV301", "injection_valve", "CIV301", (317, 232), 0, label=(14, -8, "start"), flow_path="chem-meoh"),
    valve("CIMV301", "metering_valve", "CIMV301", (375, 232), 0, label=(0, -12), flow_path="chem-meoh"),
    valve("MIV302", "injection_valve", "MIV302", (370, 265), 0, label=(14, -8, "start"), flow_path="miv-up"),
    valve("MIV303", "injection_valve", "MIV303", (370, 290), 0, label=(14, -8, "start"), flow_path="miv-dn"),
    valve("CIV304", "injection_valve", "CIV304", (130, 356), 0, label=(0, -13), flow_path="chem-downhole"),
    valve("CIMV304", "metering_valve", "CIMV304", (97, 356), 0, label=(0, -12), flow_path="chem-downhole"),
    # non-return valves (not drawn on the reference: SubseaSim additions, kept small)
    comp("NRV302", "check_valve", "element:NRV302", (301, 160), 90, flow_path="chem-ci"),
    comp("NRV303", "check_valve", "element:NRV303", (285, 172), 90, flow_path="chem-bio"),
    comp("NRV301", "check_valve", "element:NRV301", (277, 190), 90, flow_path="chem-meoh"),
    comp("NRV306", "check_valve", "element:NRV306", (425, 175), 270, flow_path="miv-up"),
    comp("NRV307", "check_valve", "element:NRV307", (455, 175), 270, flow_path="miv-dn"),
    comp("NRV304", "check_valve", "element:NRV304", (205, 356), 0, flow_path="chem-downhole"),
    # --- transmitter panels (reference positions)
    panel("PTT-104", ["instrument:PT-104", "instrument:TT-104"], (248, 155, 287, 184), tap=(BORE, 164), flow_path="bore-cavity", group="tree"),
    panel("PTT-107", ["instrument:PT-107", "instrument:TT-107"], (270, 104, 309, 133), tap=(289, WING), flow_path="wing", group="tree"),
    panel("PT-404", ["instrument:PT-404"], (105, 168, 144, 186), tap=(124, 196), flow_path="service-line", group="annulus"),
    panel("PDT-401", ["instrument:PDT-401"], (93, 211, 146, 223), group="annulus", note="Differential across SLV (assumed)."),
    panel("PT-402", ["instrument:PT-402"], (161, 212, 199, 230), tap=(ANN, 222), flow_path="annulus-cavity", group="annulus"),
    panel("PT-401", ["instrument:PT-401"], (161, 239, 199, 257), tap=(ANN, 249), flow_path="annulus-cavity", group="annulus",
          note="Drawn above AMV as on the reference; measures the A-annulus below AMV."),
    panel("PTT-001", ["instrument:PT-001", "instrument:TT-001"], (252, 340, 289, 368), tap=(BORE, 350), flow_path="bore-lower-tubing", group="downhole"),
    panel("PTT-002", ["instrument:PT-002", "instrument:TT-002"], (290, 340, 327, 368), group="downhole"),
    panel("PTT-103", ["instrument:PT-103", "instrument:TT-103"], (488, 214, 526, 243), tap=(CHKX, 227), flow_path="choke-outlet", group="downstream"),
    panel("PTT-106", ["instrument:PT-106", "instrument:TT-106"], (488, 250, 526, 279), tap=(CHKX, 260), flow_path="choke-outlet", group="downstream"),
    {"id": "SDT-101", "type": "sand_detector", "model": None, **box(490, 175, 537, 195), "rotation": 0, "tap": p(CHKX, 184),
     "flow_path": "choke-outlet", "group": "downstream",
     "note": "SDT-101 acoustic sand detector on the choke outlet; reading from the sand-detector model."},
    comp("SDT-101-body", "inline_device", None, (CHKX, 200), 90, flow_path="choke-outlet",
         note="Sand detector SDT-101 clamp-on sensor on the choke outlet."),
    {"id": "CHK-101-panel", "type": "choke_panel", "model": "element:CHOKE", **box(496, 124, 537, 167), "rotation": 0, "group": "downstream"},
    # --- selector valves (lower right)
    comp("HSV-101", "selector_valve", "selector:HSV-101", (468, 326), 0, flow_path="hyd-lp-a"),
    comp("HSV-102", "selector_valve", "selector:HSV-102", (468, 364), 0, flow_path="hyd-lp-b"),
    comp("HSV-103", "selector_valve", "selector:HSV-103", (468, 397), 0, flow_path="hyd-hp-a"),
    comp("HSV-104", "selector_valve", "selector:HSV-104", (468, 433), 0, flow_path="hyd-hp-b"),
    {"id": "PT-601", "type": "header_panel", "model": "supply:LP", **box(410, 320, 445, 340), "rotation": 0, "tap": p(427, 346), "group": "selector"},
    {"id": "PT-602", "type": "header_panel", "model": "supply:HP", **box(410, 391, 445, 411), "rotation": 0, "tap": p(427, 417), "group": "selector"},
    {"id": "PT-611", "type": "header_panel", "model": "header:LP-A", **box(487, 302, 522, 321), "rotation": 0, "tap": p(500, 326), "group": "selector"},
    {"id": "PT-612", "type": "header_panel", "model": "header:LP-B", **box(487, 338, 522, 357), "rotation": 0, "tap": p(500, 364), "group": "selector"},
    {"id": "PT-621", "type": "header_panel", "model": "header:HP-A", **box(487, 373, 522, 392), "rotation": 0, "tap": p(500, 397), "group": "selector"},
    {"id": "PT-622", "type": "header_panel", "model": "header:HP-B", **box(487, 409, 522, 428), "rotation": 0, "tap": p(500, 433), "group": "selector"},
    # --- SubseaSim transmitters NOT on the reference page (additions region, no taps:
    #     the panel text states the measurement location)
    panel("PTT-102", ["instrument:PT-102", "instrument:TT-102"], (556, 104, 646, 133), group="additions",
          note="Upstream of the production choke (between PWV and CHK-101)."),
    panel("PDT-101", ["instrument:PDT-101"], (556, 139, 646, 153), group="additions", note="Differential pressure across the production choke."),
    panel("FT-101", ["instrument:FT-101"], (556, 158, 646, 172), group="additions", note="Production flow downstream of the choke."),
    panel("PTT-101", ["instrument:PT-101", "instrument:TT-101"], (556, 178, 646, 207), group="additions",
          note="Tree production bore below PMV (wellhead)."),
    panel("PT-105", ["instrument:PT-105"], (556, 213, 646, 227), group="additions", note="Tree cap above the swab valve."),
    panel("PT-403", ["instrument:PT-403"], (556, 233, 646, 247), group="additions", note="Annulus service line downstream of SLV."),
    panel("PTT-201", ["instrument:PT-201", "instrument:TT-201"], (556, 384, 646, 413), group="additions", note="Flowline arrival at the manifold."),
    # --- manifold multiphase flow meter (SubseaSim addition), inline before the manifold
    {"id": "MPFM-201", "type": "mpfm", "model": "mpfm:MPFM-201", "x": p(585, 306)[0], "y": p(585, 306)[1], "w": 150.0, "h": 34.0,
     "rotation": 90, "flow_path": "choke-outlet", "group": "additions",
     "note": "Manifold multiphase flow meter (venturi + dual-energy gamma, representative model)."},
    # --- page buttons on the reference that have a working equivalent
    {"id": "btn-scm-diagnostic", "type": "button", "model": "page:diagnostics", **box(420, 74, 470, 87), "rotation": 0,
     "note": "SCM Diagnostic (reference) - opens the Diagnostics page."},
]

connectors = [
    {"id": "con-service", "x": p(34, 196)[0], "y": p(34, 196)[1], "direction": "left", "label": "Service line", "model": None},
    {"id": "con-ci", "x": p(405, 176)[0], "y": p(405, 176)[1], "direction": "right", "label": "CI", "model": "chemical:corrosion_inhibitor"},
    {"id": "con-bio", "x": p(405, 203)[0], "y": p(405, 203)[1], "direction": "right", "label": "BIO", "model": "chemical:biocide"},
    {"id": "con-meoh", "x": p(405, 232)[0], "y": p(405, 232)[1], "direction": "right", "label": "MeOH", "model": "chemical:methanol"},
    {"id": "con-miv", "x": p(350, 300)[0], "y": p(350, 300)[1], "direction": "down", "label": "MeOH (MIVs)", "model": "chemical:methanol"},
    {"id": "con-downhole", "x": p(64, 356)[0], "y": p(64, 356)[1], "direction": "left", "label": "Downhole chemical", "model": "chemical:wax_inhibitor"},
    {"id": "con-tubing", "x": p(BORE, 446)[0], "y": p(BORE, 446)[1], "direction": "down", "label": "Tubing to reservoir", "model": None, "label_side": "right"},
    {"id": "con-annulus", "x": p(ANN, 446)[0], "y": p(ANN, 446)[1], "direction": "down", "label": "A-annulus", "model": None},
]

groups = [
    {"id": "annulus", "label": "Annulus & service line", **box(28, 100, 212, 262), "frame": False},
    {"id": "tree", "label": "Production tree", **box(214, 80, 495, 300), "frame": False},
    {"id": "chemical", "label": "Chemical injection", **box(330, 246, 415, 305), "frame": False},
    {"id": "downstream", "label": "Choke & downstream", **box(470, 120, 545, 290), "frame": False},
    {"id": "selector", "label": "Selector Valves", **box(385, 296, 535, 446), "frame": True},
    {"id": "downhole", "label": "Downhole", **box(55, 334, 330, 446), "frame": False},
    {"id": "additions", "label": "Additional measurements", **box(550, 90, 652, 446), "frame": True},
]

annotations = [
    {"type": "title", **dict(zip(("x", "y"), p(300, 56))), "text": "Production 230XP22B"},
    {"type": "bar", **box(183, 84, 247, 88), "label": "Tree cap"},
    {"type": "body", **box(223, 102, 246, 227), "label": "Tree block"},
    {"type": "manifold", **box(560, 330, 640, 372), "label": "MANIFOLD"},
]

layout_doc = {
    "id": "xt_230xp22b",
    "title": "Production 230XP22B",
    "subtitle": "Christmas tree workstation - layout traced from the reference control-system page",
    "width": round((652 - X0) * S),
    "height": round((460 - Y0) * S),
    "reference": {
        "source": "User-supplied photograph of a subsea control-system page 'Production 230XP22B without IWC' (810 x 1080 px).",
        "method": "Component centres and panel boxes measured in photo pixels, keystone-straightened (verticals made vertical, "
                  "measured shear ~0.07 px/px), then scaled uniformly. Relative positions are preserved; text panels are "
                  "enlarged slightly for legibility around the same anchor.",
        "photo_origin_px": [X0, Y0],
        "scale": S,
        "notes": [
            "The SCM Reconnect button on the reference is not reproduced: SCM communications are not modelled.",
            "Chemical names at the right-hand line ends are illegible on the photograph; SubseaSim chemical names are shown.",
            "The framed region right of photo x = 550 (manifold, additional transmitters) holds measurements added beyond the reference page.",
        ],
    },
    "groups": groups,
    "lines": lines,
    "components": components,
    "connectors": connectors,
    "annotations": annotations,
}

multiphase = {
    "extends": "xt_230xp22b",
    "id": "xt_230xp22b_multiphase",
    "name": "XT workstation - three-phase production (oil, gas, water)",
    "description": ("The XT workstation system with a three-phase black-oil fluid: gas comes out of solution in the upper tubing, "
                    "the production choke can run critical, and the flowline carries oil, gas and water in a Beggs & Brill flow "
                    "pattern. Generic correlations (Standing, Vasquez-Beggs, Beggs-Robinson, DAK, Lee, McCain) - ILLUSTRATIVE, "
                    "not fitted to a PVT report."),
    "fluid_model": "black_oil",
    # FT-101 reads the IN-SITU gas + liquid volumetric flow downstream of the choke in the
    # three-phase model: wider range than the single-phase liquid meter
    "instruments": [
        ({**i, "range_max": 12000, "description": "Production flow downstream of choke (in-situ gas + liquid volume, line conditions)"}
         if i["tag"] == "FT-101" else i)
        for i in json.load(open(HERE.parent / "app" / "scenarios" / "data" / "base_single_phase.json", encoding="utf-8"))["instruments"]
    ],
    "briefing": [
        "Three-phase model: open Multiphase to see oil, gas and water rates at standard conditions, the flow pattern and liquid holdup along the path, and the phase mass balances.",
        "Change the water cut or GOR on Conditions: the new composition travels up the well and along the flowline with the fluid.",
        "Close the choke in steps and watch the flow move from critical (choked) to sub-critical as the differential falls.",
    ],
}

training = {
    "extends": "xt_230xp22b_multiphase",
    "id": "training_integrated",
    "name": "Training - integrated three-phase production, sand and choke erosion",
    "description": ("Guided exercise scenario: the three-phase XT well starts SHUT IN (production wing valve closed) with a complete "
                    "ILLUSTRATIVE sand / choke input set, so the whole chain - production, MPFM, sanding, sand transport, choke "
                    "erosion and the maintenance recommendation - can be followed in one session. Not field data."),
    "element_overrides": {"PWV": {"initial_position_pct": 0}},
    "sand_choke": sc["sand_choke_example"],
    "briefing": ["Start Training > 'Exercise 7 - Integrated production, sand and choke health' to be guided step by step."],
}

# ---- tree-workstation training scenarios (single-phase, dynamic) -----------
TRAINING_XT = {
    "ex03_choke_operation": {
        "name": "Exercise 3 - Choke operation (illustrative)",
        "description": "Tree workstation, single-phase producer in the quasi-steady model with the production choke at 20 % opening. "
                       "Used by training Exercise 3. All data ILLUSTRATIVE.",
        "dynamics": {"mode": "steady"},
        "element_overrides": {"CHOKE": {"initial_position_pct": 20}},
        "briefing": ["Start Training > 'Exercise 3 - Choke operation' to be guided step by step."],
    },
    "training_startup": {
        "name": "Training - well start-up from shut-in",
        "description": "Tree workstation, single-phase producer fully SHUT IN (SCSSV, PMV, PWV closed; choke at 0 %). Used by "
                       "Exercise 2. All data ILLUSTRATIVE.",
        "element_overrides": {"SCSSV": {"initial_position_pct": 0}, "PMV": {"initial_position_pct": 0},
                              "PWV": {"initial_position_pct": 0}, "CHOKE": {"initial_position_pct": 0}},
        "briefing": ["Start Training > 'Exercise 2 - Well start-up from shut-in' to be guided step by step."],
    },
    "training_leaking_pmv": {
        "name": "Training - PMV-101 leak test",
        "description": "Tree workstation, single-phase producer; PMV-101 has a small seat leak (Cd.A 0.0001 mm2) to be found by an "
                       "inflow test. Used by Exercise 8. All data ILLUSTRATIVE - acceptance limits are training values.",
        "element_overrides": {"PMV": {"seat_leak_area_mm2": 0.0001}},
        "briefing": ["Start Training > 'Exercise 8 - Leak test of the production master valve' to be guided step by step."],
    },
}


if __name__ == "__main__":
    root = HERE.parent / "app" / "scenarios"
    (root / "layouts").mkdir(exist_ok=True)
    with open(root / "data" / "xt_230xp22b.json", "w", encoding="utf-8") as f:
        json.dump(sc, f, indent=2)
    with open(root / "data" / "xt_230xp22b_multiphase.json", "w", encoding="utf-8") as f:
        json.dump(multiphase, f, indent=2)
    with open(root / "data" / "training_integrated.json", "w", encoding="utf-8") as f:
        json.dump(training, f, indent=2)
    for sid, extra in TRAINING_XT.items():
        with open(root / "data" / f"{sid}.json", "w", encoding="utf-8") as f:
            json.dump({"extends": "xt_230xp22b", "id": sid, **extra}, f, indent=2)
    with open(root / "layouts" / "xt_230xp22b.json", "w", encoding="utf-8") as f:
        json.dump(layout_doc, f, indent=2)
    print("written xt_230xp22b scenario + layout")
