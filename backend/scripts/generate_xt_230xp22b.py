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
valves, and the reference tag numbering as display aliases.

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
    "SCSSV, PMV and the production wing (PWV) ending in the production choke PCV3006; A-annulus with AMV, AWV, crossover "
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
# XOV3032 connects the service-line junction (downstream of AWV) to the tree
# cavity - on the reference the crossover line leaves the service line
# between AWV's branch and the bore.
elems["XOV"]["from"] = "N_ANN_SVC"
elems["XOV"]["name"] = "Crossover valve (annulus service-line junction to tree cavity)"

# Methanol route into the annulus service line is not on the reference page.
drop({"SUP_MEOH_ANN", "N_MIV_IN", "N_MIV_A", "CL-305", "MIV301", "NRV305", "FT-305"})

# Chemical injection points: the reference shows CIV3027 / CIV3025 / CIV3023
# lines joining the production wing between the bore and PWV.
for num in (302, 303):
    elems[f"NRV{num}"]["to"] = "N_PMV_PWV"
# Downhole chemical line joins the bore below the SCSSV on the reference.
elems["NRV304"]["to"] = "N_SCSSV_U"
_inj_node = {"corrosion_inhibitor": "N_PMV_PWV", "biocide": "N_PMV_PWV", "wax_inhibitor": "N_SCSSV_U"}
for c in sc["chemicals"]:
    c["injection_node"] = _inj_node.get(c["id"], c["injection_node"])

# Two methanol injection valves fed from one methanol header: MIV3015 into the
# wing upstream of PWV, MIV3016 between PWV and the choke.
sub["nodes"] += [
    {"id": "SUP_MEOH_MIV", "name": "Methanol to MIV header: SDU supply", "elevation_m": -1150, "zone": "methanol"},
    {"id": "N_MIV_HDR", "name": "Methanol MIV header at tree", "elevation_m": -1195, "zone": "methanol"},
    {"id": "N_MIV1_A", "name": "Methanol: downstream of MIV3015", "elevation_m": -1195, "zone": "methanol"},
    {"id": "N_MIV2_A", "name": "Methanol: downstream of MIV3016", "elevation_m": -1195, "zone": "methanol"},
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
    {"id": "miv_up", "name": "MIV3015 - production wing upstream of PWV", "supply_node": "SUP_MEOH_MIV", "valve": "MIV-302",
     "check_valve": "NRV-306", "injection_node": "N_PMV_PWV", "flow_transmitter": "FT-306"},
    {"id": "miv_dn", "name": "MIV3016 - between PWV and the production choke", "supply_node": "SUP_MEOH_MIV", "valve": "MIV-303",
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
    {"tag": "TT-104", "type": "temperature", "description": "Tree cavity temperature (PTT3005)", "node": "N_PMV_PWV", "range_min": 0, "range_max": 150},
    {"tag": "PT-107", "type": "pressure", "description": "Production wing pressure upstream of PWV (PTT3004)", "node": "N_PMV_PWV", "range_min": 0, "range_max": 690},
    {"tag": "TT-107", "type": "temperature", "description": "Production wing temperature upstream of PWV (PTT3004)", "node": "N_PMV_PWV", "range_min": 0, "range_max": 150},
    {"tag": "PT-002", "type": "pressure", "description": "Downhole gauge B pressure (PTT3003)", "node": "N_BH", "range_min": 0, "range_max": 690},
    {"tag": "TT-002", "type": "temperature", "description": "Downhole gauge B temperature (PTT3003)", "node": "N_BH", "range_min": 0, "range_max": 150},
    {"tag": "PT-106", "type": "pressure", "description": "Production line pressure downstream of choke, 30 m (PTT3009)", "element": "FL-101", "distance_m": 30, "range_min": 0, "range_max": 690},
    {"tag": "TT-106", "type": "temperature", "description": "Production line temperature downstream of choke, 30 m (PTT3009)", "element": "FL-101", "distance_m": 30, "range_min": 0, "range_max": 150},
    {"tag": "PT-404", "type": "pressure", "description": "Annulus service-line junction pressure, upstream of SLV (PT3014)", "node": "N_ANN_SVC", "range_min": 0, "range_max": 690},
    {"tag": "PDT-401", "type": "differential_pressure", "description": "Differential pressure across the service line valve SLV (PD3014)", "high_node": "N_ANN_SVC", "low_node": "N_SVC_L", "range_min": -350, "range_max": 350},
    {"tag": "FT-306", "type": "flow", "description": "Methanol flow through MIV3015 (wing, upstream of PWV)", "element": "MIV302", "range_min": 0, "range_max": 120},
    {"tag": "FT-307", "type": "flow", "description": "Methanol flow through MIV3016 (between PWV and choke)", "element": "MIV303", "range_min": 0, "range_max": 120},
]

# --- control hydraulics (selector valves on the reference) ----------------
LP_VALVES = ["PMV-101", "PWV-101", "AMV-101", "AWV-101", "XOV-101", "SLV-101", "SV-101",
             "CIV-301", "CIV-302", "CIV-303", "CIV-304", "MIV-302", "MIV-303",
             "CHK-101", "CIMV-301", "CIMV-302", "CIMV-303", "CIMV-304"]
sc["control_hydraulics"] = {
    "supplies": [
        {"id": "LP", "name": "LP", "tag": "PT-HYD-LP", "pressure_bara": 207, "minimum_operating_pressure_bara": 110},
        {"id": "HP", "name": "HP", "tag": "PT-HYD-HP", "pressure_bara": 517, "minimum_operating_pressure_bara": 300},
    ],
    "headers": [
        {"id": "LP-A", "name": "LP header SCM A", "tag": "PT-HYD-LPA", "supply": "LP", "scm": "A"},
        {"id": "LP-B", "name": "LP header SCM B", "tag": "PT-HYD-LPB", "supply": "LP", "scm": "B"},
        {"id": "HP-A", "name": "HP header SCM A", "tag": "PT-HYD-HPA", "supply": "HP", "scm": "A"},
        {"id": "HP-B", "name": "HP header SCM B", "tag": "PT-HYD-HPB", "supply": "HP", "scm": "B"},
    ],
    "selector_valves": [
        {"tag": "SEL-LP-A", "name": "LP selector valve to SCM A", "header": "LP-A"},
        {"tag": "SEL-LP-B", "name": "LP selector valve to SCM B", "header": "LP-B"},
        {"tag": "SEL-HP-A", "name": "HP selector valve to SCM A", "header": "HP-A"},
        {"tag": "SEL-HP-B", "name": "HP selector valve to SCM B", "header": "HP-B"},
    ],
    "valve_supply": {**{t: "LP" for t in LP_VALVES}, "SCSSV-101": "HP"},
    "fail_safe_close": [t for t in LP_VALVES if not t.startswith(("CHK", "CIMV"))] + ["SCSSV-101"],
}

# --- display tags (reference numbering) -----------------------------------
V, U, P, A = "verified", "uncertain", "placeholder", "addition"
alias = {
    # valves
    "AWV-101": ("AWV3034", V, ""), "AMV-101": ("AMV3030", V, ""), "PMV-101": ("PMV3004", V, ""),
    "PWV-101": ("PWV3005", V, ""), "SCSSV-101": ("SCSSV3003", V, ""), "CHK-101": ("PCV3006", V, ""),
    "XOV-101": ("XOV3032", V, ""), "SLV-101": ("SLV3035", V, ""),
    "CIV-302": ("CIV3027", U, "Partly legible on the reference."), "CIMV-302": ("CCV3026", U, "Partly legible on the reference."),
    "CIV-303": ("CIV3025", U, "Partly legible on the reference."),
    "CIV-301": ("CIV3023", U, "Partly legible on the reference."), "CIMV-301": ("CCV3022", U, "Partly legible on the reference."),
    "MIV-302": ("MIV3015", U, "Partly legible on the reference."), "MIV-303": ("MIV3016", U, "Partly legible on the reference."),
    "CIV-304": ("CIV3021", U, "Partly legible on the reference."), "CIMV-304": ("CCV3036", U, "Partly legible on the reference."),
    "SV-101": ("SV-101", A, "Swab valve: SubseaSim addition, not drawn on the reference page."),
    "CIMV-303": ("CIMV-303", A, "Metering valve not drawn on the reference page for this line."),
    # transmitters
    "PT-104": ("PT3005", V, "Panel PTT3005."), "TT-104": ("TT3005", V, "Panel PTT3005."),
    "PT-107": ("PT3004", V, "Panel PTT3004."), "TT-107": ("TT3004", V, "Panel PTT3004."),
    "PT-001": ("PT3002", V, "Panel PTT3002 (downhole gauge A)."), "TT-001": ("TT3002", V, "Panel PTT3002 (downhole gauge A)."),
    "PT-002": ("PT3003", V, "Panel PTT3003 (downhole gauge B)."), "TT-002": ("TT3003", V, "Panel PTT3003 (downhole gauge B)."),
    "PT-103": ("PT3008", V, "Panel PTT3008."), "TT-103": ("TT3008", V, "Panel PTT3008."),
    "PT-106": ("PT3009", V, "Panel PTT3009."), "TT-106": ("TT3009", V, "Panel PTT3009."),
    "PT-402": ("PT3030", V, ""),
    "PT-401": ("PT3031", U, "Reads PT3031 or PT3011 on the reference; tap drawn above AMV, modelled on the A-annulus below AMV."),
    "PT-404": ("PT3014", V, ""), "PDT-401": ("PD3014", V, "Measured across SLV (assumed from its position on the reference)."),
    # control hydraulics
    "PT-HYD-LP": ("LPHP1", U, "Supply pressure panel; label partly legible."),
    "PT-HYD-HP": ("HPHP1", U, "Supply pressure panel; label partly legible."),
    "PT-HYD-LPA": ("LP3096", U, "Partly legible."), "PT-HYD-LPB": ("LP3097", U, "Partly legible."),
    "PT-HYD-HPA": ("HP3098", U, "Partly legible."), "PT-HYD-HPB": ("HP3099", U, "Partly legible."),
    "SEL-LP-A": ("SEL-LP-A", P, "Selector valves carry no tag on the reference page."),
    "SEL-LP-B": ("SEL-LP-B", P, "Selector valves carry no tag on the reference page."),
    "SEL-HP-A": ("SEL-HP-A", P, "Selector valves carry no tag on the reference page."),
    "SEL-HP-B": ("SEL-HP-B", P, "Selector valves carry no tag on the reference page."),
}
sc["tag_aliases"] = {k: {"tag": t, "status": s, "note": n} for k, (t, s, n) in alias.items()}

sc["briefing"] = [
    "This page reproduces the reference control-system layout 'Production 230XP22B'. Tags are the reference numbers; open a component to see its SubseaSim engineering tag.",
    "Every reading is calculated by the simulator from the inputs on the Conditions page (reservoir pressure, temperature, productivity, fluid, downstream pressure) and the valve positions - change them and watch the transmitters respond.",
    "Try closing PWV3005: the tree cavity (PTT3005 / PTT3004) builds toward shut-in pressure while the choke outlet (PTT3008 / PTT3009) falls toward flowline pressure.",
    "Selector valves route the LP and HP hydraulic supplies to SCM A and B. Close both LP selector valves and watch LP3096 / LP3097 bleed down until the fail-safe valves close.",
    "Open MIV3015 (upstream of PWV) or MIV3016 (between PWV and the choke) to inject methanol into the production stream; the concentration is tracked downstream.",
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
    panel("PTT3005", ["instrument:PT-104", "instrument:TT-104"], (240, 155, 279, 184), tap=(BORE, 164), flow_path="bore-cavity", group="tree"),
    panel("PTT3004", ["instrument:PT-107", "instrument:TT-107"], (270, 104, 309, 133), tap=(289, WING), flow_path="wing", group="tree"),
    panel("PT3014", ["instrument:PT-404"], (105, 168, 144, 186), tap=(124, 196), flow_path="service-line", group="annulus"),
    panel("PD3014", ["instrument:PDT-401"], (93, 211, 146, 223), group="annulus", note="Differential across SLV (assumed)."),
    panel("PT3030", ["instrument:PT-402"], (161, 212, 199, 230), tap=(ANN, 222), flow_path="annulus-cavity", group="annulus"),
    panel("PT3031", ["instrument:PT-401"], (161, 239, 199, 257), tap=(ANN, 249), flow_path="annulus-cavity", group="annulus",
          note="Drawn above AMV as on the reference; measures the A-annulus below AMV."),
    panel("PTT3002", ["instrument:PT-001", "instrument:TT-001"], (252, 340, 289, 368), tap=(BORE, 350), flow_path="bore-lower-tubing", group="downhole"),
    panel("PTT3003", ["instrument:PT-002", "instrument:TT-002"], (290, 340, 327, 368), group="downhole"),
    panel("PTT3008", ["instrument:PT-103", "instrument:TT-103"], (488, 214, 526, 243), tap=(CHKX, 227), flow_path="choke-outlet", group="downstream"),
    panel("PTT3009", ["instrument:PT-106", "instrument:TT-106"], (488, 250, 526, 279), tap=(CHKX, 260), flow_path="choke-outlet", group="downstream"),
    {"id": "PCV3006-panel", "type": "choke_panel", "model": "element:CHOKE", **box(496, 124, 537, 167), "rotation": 0, "group": "downstream"},
    {"id": "XT3001", "type": "sand_detector", "model": None, **box(490, 175, 537, 195), "rotation": 0, "tap": p(CHKX, 184),
     "flow_path": "choke-outlet", "group": "downstream",
     "note": "XT3001 on the reference (assumed acoustic sand detector). Sand production is not modelled yet - shown as not modelled."},
    comp("XT3001-body", "inline_device", None, (CHKX, 200), 90, flow_path="choke-outlet",
         note="Inline device on the choke outlet (reference). Associated with XT3001."),
    # --- selector valves (lower right)
    comp("SEL-LP-A", "selector_valve", "selector:SEL-LP-A", (468, 326), 0, flow_path="hyd-lp-a"),
    comp("SEL-LP-B", "selector_valve", "selector:SEL-LP-B", (468, 364), 0, flow_path="hyd-lp-b"),
    comp("SEL-HP-A", "selector_valve", "selector:SEL-HP-A", (468, 397), 0, flow_path="hyd-hp-a"),
    comp("SEL-HP-B", "selector_valve", "selector:SEL-HP-B", (468, 433), 0, flow_path="hyd-hp-b"),
    {"id": "LPHP1", "type": "header_panel", "model": "supply:LP", **box(410, 320, 445, 340), "rotation": 0, "tap": p(427, 346), "group": "selector"},
    {"id": "HPHP1", "type": "header_panel", "model": "supply:HP", **box(410, 391, 445, 411), "rotation": 0, "tap": p(427, 417), "group": "selector"},
    {"id": "LP3096", "type": "header_panel", "model": "header:LP-A", **box(487, 302, 522, 321), "rotation": 0, "tap": p(500, 326), "group": "selector"},
    {"id": "LP3097", "type": "header_panel", "model": "header:LP-B", **box(487, 338, 522, 357), "rotation": 0, "tap": p(500, 364), "group": "selector"},
    {"id": "HP3098", "type": "header_panel", "model": "header:HP-A", **box(487, 373, 522, 392), "rotation": 0, "tap": p(500, 397), "group": "selector"},
    {"id": "HP3099", "type": "header_panel", "model": "header:HP-B", **box(487, 409, 522, 428), "rotation": 0, "tap": p(500, 433), "group": "selector"},
    # --- SubseaSim transmitters NOT on the reference page (additions region, no taps:
    #     the panel text states the measurement location)
    panel("PTT-102", ["instrument:PT-102", "instrument:TT-102"], (556, 104, 646, 133), group="additions",
          note="Upstream of the production choke (between PWV and PCV3006)."),
    panel("PDT-101", ["instrument:PDT-101"], (556, 139, 646, 153), group="additions", note="Differential pressure across the production choke."),
    panel("FT-101", ["instrument:FT-101"], (556, 158, 646, 172), group="additions", note="Production flow downstream of the choke."),
    panel("PTT-101", ["instrument:PT-101", "instrument:TT-101"], (556, 178, 646, 207), group="additions",
          note="Tree production bore below PMV (wellhead)."),
    panel("PT-105", ["instrument:PT-105"], (556, 213, 646, 227), group="additions", note="Tree cap above the swab valve."),
    panel("PT-403", ["instrument:PT-403"], (556, 233, 646, 247), group="additions", note="Annulus service line downstream of SLV."),
    panel("PTT-201", ["instrument:PT-201", "instrument:TT-201"], (556, 384, 646, 413), group="additions", note="Flowline arrival at the manifold."),
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
    {"id": "additions", "label": "SubseaSim additions - not on the reference page", **box(550, 90, 652, 446), "frame": True},
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
    "height": round((452 - Y0) * S),
    "reference": {
        "source": "User-supplied photograph of a subsea control-system page 'Production 230XP22B without IWC' (810 x 1080 px).",
        "method": "Component centres and panel boxes measured in photo pixels, keystone-straightened (verticals made vertical, "
                  "measured shear ~0.07 px/px), then scaled uniformly. Relative positions are preserved; text panels are "
                  "enlarged slightly for legibility around the same anchor.",
        "photo_origin_px": [X0, Y0],
        "scale": S,
        "notes": [
            "Tags PT3010, PT3011 and PT3013 (listed in the requirement) could not be located on the photograph and are not assigned.",
            "The SCM Reconnect button on the reference is not reproduced: SCM communications are not modelled.",
            "Chemical names at the right-hand line ends are illegible on the photograph; SubseaSim chemical names are shown.",
            "The framed region right of photo x = 550 (manifold, additional transmitters) is a SubseaSim addition outside the reference page.",
        ],
    },
    "groups": groups,
    "lines": lines,
    "components": components,
    "connectors": connectors,
    "annotations": annotations,
}

if __name__ == "__main__":
    root = HERE.parent / "app" / "scenarios"
    (root / "layouts").mkdir(exist_ok=True)
    with open(root / "data" / "xt_230xp22b.json", "w", encoding="utf-8") as f:
        json.dump(sc, f, indent=2)
    with open(root / "layouts" / "xt_230xp22b.json", "w", encoding="utf-8") as f:
        json.dump(layout_doc, f, indent=2)
    print("written xt_230xp22b scenario + layout")
