"""Generates app/scenarios/data/subsea_dynamic_base.json (run from backend/).

Usage:  python scripts/generate_subsea_dynamic_base.py [output.json]

Layout follows a vertical subsea Xmas tree HMI page: production bore up the
centre with the swab valve and tree cap at the top, production wing to the
right ending in the production choke (which discharges down into the
flowline / jumper), annulus bore to the left (AMV, AWV, crossover), annulus
service line leaving to the left through the service-line valve at the
junction where the methanol injection line joins it, chemical-injection
lines arriving from off-page SDU connectors with the metering valve outboard
and the isolation valve next to the bore, and the downhole chemical line at
the bottom left.
"""
import json
import sys

out = sys.argv[1] if len(sys.argv) > 1 else "app/scenarios/data/subsea_dynamic_base.json"

nodes = [
    {"id": "RES", "name": "Reservoir (drainage boundary, at datum)", "elevation_m": -3700},
    {"id": "N_BH", "name": "Bottomhole / sandface", "elevation_m": -3700},
    {"id": "N_SCSSV_U", "name": "Tubing below SCSSV", "elevation_m": -1800},
    {"id": "N_SCSSV_D", "name": "Tubing above SCSSV (wax-inhibitor mandrel)", "elevation_m": -1800},
    {"id": "N_TREE", "name": "Tree production bore (below PMV)", "elevation_m": -1195},
    {"id": "N_PMV_PWV", "name": "Tree bore cavity between PMV, PWV and swab valve", "elevation_m": -1195,
     "volume_m3": 0.03, "heat_loss_ua_w_k": 15, "thermal_mass_j_k": 8.0e6, "ambient_temperature_c": 4},
    {"id": "N_UC", "name": "Wing block / upstream of production choke", "elevation_m": -1195,
     "volume_m3": 0.02, "heat_loss_ua_w_k": 10, "thermal_mass_j_k": 4.0e6, "ambient_temperature_c": 4},
    {"id": "N_DC", "name": "Downstream of production choke (flowline inlet)", "elevation_m": -1195},
    {"id": "N_ARR", "name": "Flowline arrival (manifold / riser base)", "elevation_m": -1150},
]

fluids = {
    "annulus": {"name": "A-annulus completion brine (with gas-cushion compliance)", "density_kg_m3": 1030, "viscosity_cp": 1.0,
                "specific_heat_j_kgk": 3800, "thermal_expansion_1_k": 3.0e-4, "compressibility_1_bar": 4.4e-5},
    "methanol": {"name": "Methanol (MeOH)", "density_kg_m3": 792, "viscosity_cp": 0.59, "specific_heat_j_kgk": 2500,
                 "thermal_expansion_1_k": 1.2e-3, "compressibility_1_bar": 1.2e-4},
    "corrosion_inhibitor": {"name": "Corrosion inhibitor (illustrative)", "density_kg_m3": 950, "viscosity_cp": 5.0,
                            "specific_heat_j_kgk": 2200, "thermal_expansion_1_k": 8.0e-4, "compressibility_1_bar": 6.0e-5},
    "biocide": {"name": "Biocide (illustrative)", "density_kg_m3": 1050, "viscosity_cp": 2.0,
                "specific_heat_j_kgk": 3500, "thermal_expansion_1_k": 5.0e-4, "compressibility_1_bar": 5.0e-5},
    "wax_inhibitor": {"name": "Wax inhibitor (illustrative)", "density_kg_m3": 880, "viscosity_cp": 8.0,
                      "specific_heat_j_kgk": 2000, "thermal_expansion_1_k": 9.0e-4, "compressibility_1_bar": 7.0e-5},
}

bnodes = [
    # swab valve / tree cap (production fluid, dead-ended above the swab valve)
    {"id": "N_SWAB_CAP", "name": "Tree cap cavity (above swab valve)", "elevation_m": -1194, "zone": "production",
     "volume_m3": 0.01, "initial_pressure_bara": 60},
    # annulus
    {"id": "ANN_BTM", "name": "A-annulus at production packer", "elevation_m": -3600, "zone": "annulus", "initial_pressure_bara": 323},
    {"id": "ANN_TOP", "name": "A-annulus at tubing hanger (below AMV)", "elevation_m": -1195, "zone": "annulus", "initial_pressure_bara": 80},
    {"id": "N_AMV_AWV", "name": "Annulus bore between AMV and AWV", "elevation_m": -1195, "zone": "annulus",
     "volume_m3": 0.01, "initial_pressure_bara": 80},
    {"id": "N_ANN_SVC", "name": "Annulus service-line junction (AWV / SLV / methanol injection)", "elevation_m": -1195,
     "zone": "annulus", "volume_m3": 0.005},
    {"id": "N_SVC_L", "name": "Annulus service line downstream of SLV", "elevation_m": -1195, "zone": "annulus"},
    {"id": "ANN_VENT", "name": "Annulus service / bleed header (host)", "elevation_m": -1150, "zone": "annulus"},
]
belements = [
    {"id": "SV", "type": "valve", "tag": "SV-101", "valve_type": "swab", "name": "Swab valve (vertical access to the production bore)",
     "from": "N_PMV_PWV", "to": "N_SWAB_CAP", "bore_diameter_m": 0.13, "loss_coefficient_open": 0.1,
     "full_stroke_time_s": 30, "actuation_delay_s": 2, "nominal_stroke_time_s": 32, "initial_position_pct": 0},
    {"id": "ANN-A", "type": "pipe", "role": "annulus", "name": "A-annulus (tubing x 9-5/8 in casing)",
     "from": "ANN_BTM", "to": "ANN_TOP", "length_m": 2405, "inner_diameter_m": 0.106, "flow_area_m2": 0.0278,
     "roughness_m": 4.5e-5, "wall_compliance_1_bar": 1.0e-4, "hydraulic_segments": 4},
    {"id": "AMV", "type": "valve", "tag": "AMV-101", "valve_type": "annulus_master", "name": "Annulus master valve",
     "from": "ANN_TOP", "to": "N_AMV_AWV", "bore_diameter_m": 0.05, "loss_coefficient_open": 0.5,
     "full_stroke_time_s": 20, "actuation_delay_s": 2, "nominal_stroke_time_s": 22, "initial_position_pct": 0},
    {"id": "AWV", "type": "valve", "tag": "AWV-101", "valve_type": "annulus_wing", "name": "Annulus wing valve",
     "from": "N_AMV_AWV", "to": "N_ANN_SVC", "bore_diameter_m": 0.05, "loss_coefficient_open": 0.5,
     "full_stroke_time_s": 20, "actuation_delay_s": 2, "nominal_stroke_time_s": 22, "initial_position_pct": 0},
    {"id": "XOV", "type": "valve", "tag": "XOV-101", "valve_type": "crossover", "name": "Crossover valve (annulus to production bore)",
     "from": "N_AMV_AWV", "to": "N_PMV_PWV", "bore_diameter_m": 0.05, "loss_coefficient_open": 0.5,
     "full_stroke_time_s": 20, "actuation_delay_s": 2, "nominal_stroke_time_s": 22, "initial_position_pct": 0},
    {"id": "SLV", "type": "valve", "tag": "SLV-101", "valve_type": "service_line", "name": "Annulus service line valve",
     "from": "N_ANN_SVC", "to": "N_SVC_L", "bore_diameter_m": 0.05, "loss_coefficient_open": 0.5,
     "full_stroke_time_s": 20, "actuation_delay_s": 2, "nominal_stroke_time_s": 22, "initial_position_pct": 100},
    {"id": "ANN-SVC", "type": "pipe", "role": "service_line", "name": "Annulus service line (2 in, 5 km)",
     "from": "N_SVC_L", "to": "ANN_VENT", "length_m": 5000, "inner_diameter_m": 0.0508, "hydraulic_segments": 5},
]
boundaries = [{"node": "ANN_VENT", "pressure_bara": 15, "description": "Annulus bleed header at host (held pressure)"}]

instruments_extra = [
    {"tag": "PT-104", "type": "pressure", "description": "Tree cavity pressure (between PMV, PWV and SV)", "node": "N_PMV_PWV", "range_min": 0, "range_max": 690},
    {"tag": "PT-105", "type": "pressure", "description": "Tree cap pressure (above swab valve)", "node": "N_SWAB_CAP", "range_min": 0, "range_max": 690},
    {"tag": "PT-202", "type": "pressure", "description": "Flowline mid-point pressure (2.5 km)", "element": "FL-101", "distance_m": 2500, "range_min": 0, "range_max": 690},
    {"tag": "TT-202", "type": "temperature", "description": "Flowline mid-point temperature (2.5 km)", "element": "FL-101", "distance_m": 2500, "range_min": 0, "range_max": 150},
    {"tag": "PT-401", "type": "pressure", "description": "A-annulus pressure at tree (below AMV)", "node": "ANN_TOP", "range_min": 0, "range_max": 690},
    {"tag": "TT-401", "type": "temperature", "description": "A-annulus fluid temperature at tree", "node": "ANN_TOP", "range_min": 0, "range_max": 150},
    {"tag": "PT-402", "type": "pressure", "description": "Annulus bore pressure between AMV and AWV", "node": "N_AMV_AWV", "range_min": 0, "range_max": 690},
    {"tag": "PT-403", "type": "pressure", "description": "Annulus service line pressure (downstream of SLV)", "node": "N_SVC_L", "range_min": 0, "range_max": 690},
]

chem_defs = [
    # id, short, name, fluid, inj node, tag no, line ID, pump, static, cv, init%, unit, color, tmin, tmax
    ("methanol", "MEOH", "Methanol (hydrate inhibitor)", "methanol", "N_PMV_PWV", 301, 0.0254, 250, 30, 0.25, 50, "vol%", "#facc15", 2, 10),
    ("corrosion_inhibitor", "CI", "Corrosion inhibitor", "corrosion_inhibitor", "N_UC", 302, 0.0095, 200, 35, 5.0e-4, 50, "ppm", "#84cc16", 20, 80),
    ("biocide", "BIO", "Biocide", "biocide", "N_DC", 303, 0.0095, 150, 35, 2.1e-3, 50, "ppm", "#ec4899", 100, 300),
    ("wax_inhibitor", "WAX", "Wax inhibitor", "wax_inhibitor", "N_SCSSV_D", 304, 0.0095, 300, 30, 2.0e-3, 50, "ppm", "#f97316", 150, 500),
]
chemicals = []
for cid, short, name, fluid, inj, num, d, pump, static, cv, init, unit, color, tmin, tmax in chem_defs:
    sup, nin, na, nb = f"SUP_{short}", f"N_{short}_IN", f"N_{short}_A", f"N_{short}_B"
    bnodes += [
        {"id": sup, "name": f"{name}: subsea distribution unit (supply)", "elevation_m": -1150, "zone": fluid},
        {"id": nin, "name": f"{name}: injection line at tree", "elevation_m": -1195, "zone": fluid},
        {"id": na, "name": f"{name}: between metering and isolation valve", "elevation_m": -1195, "zone": fluid},
        {"id": nb, "name": f"{name}: downstream of isolation valve", "elevation_m": -1195, "zone": fluid},
    ]
    boundaries.append({"node": sup, "pressure_bara": pump, "description": f"{name} pump discharge referred to the SDU"})
    # supply -> umbilical -> metering valve (CIMV, outboard) -> isolation valve (CIV, barrier at the bore) -> NRV -> injection point
    belements += [
        {"id": f"CL-{num}", "type": "pipe", "role": "injection_line", "name": f"{name} umbilical line ({d * 1000:.1f} mm, 5 km)",
         "from": sup, "to": nin, "length_m": 5000, "inner_diameter_m": d, "roughness_m": 1.5e-6, "hydraulic_segments": 5},
        {"id": f"CIMV{num}", "type": "choke", "tag": f"CIMV-{num}", "service": "metering", "name": f"{name} injection metering valve",
         "from": nin, "to": na, "cv_max": cv, "characteristic": "linear", "rangeability": 50, "full_stroke_time_s": 60,
         "initial_position_pct": init},
        {"id": f"CIV{num}", "type": "valve", "tag": f"CIV-{num}", "valve_type": "injection_isolation", "name": f"{name} injection isolation valve",
         "from": na, "to": nb, "bore_diameter_m": 0.01, "loss_coefficient_open": 2.0, "full_stroke_time_s": 10,
         "actuation_delay_s": 2, "nominal_stroke_time_s": 12, "initial_position_pct": 0},
    ]
    if cid == "wax_inhibitor":
        bnodes.append({"id": "N_WAX_DH", "name": "Wax inhibitor: downhole injection mandrel", "elevation_m": -1800, "zone": fluid})
        belements += [
            {"id": "CL-304DH", "type": "pipe", "role": "injection_line", "name": "Wax inhibitor downhole line (6.4 mm, 605 m)",
             "from": nb, "to": "N_WAX_DH", "length_m": 605, "inner_diameter_m": 0.0064, "roughness_m": 1.5e-6, "hydraulic_segments": 2},
            {"id": f"NRV{num}", "type": "check_valve", "tag": f"NRV-{num}", "name": f"{name} non-return valve (downhole)",
             "from": "N_WAX_DH", "to": inj, "cracking_pressure_bar": 2.0, "cv": 0.05},
        ]
    else:
        belements.append({"id": f"NRV{num}", "type": "check_valve", "tag": f"NRV-{num}", "name": f"{name} non-return valve",
                          "from": nb, "to": inj, "cracking_pressure_bar": 0.5, "cv": 0.2 if cid == "methanol" else 0.05})
    instruments_extra += [
        {"tag": f"PT-{num}", "type": "pressure", "description": f"{name} injection pressure at tree", "node": nin, "range_min": 0, "range_max": 690},
        {"tag": f"FT-{num}", "type": "flow", "description": f"{name} injection flow (metering valve)", "element": f"CIMV{num}",
         "range_min": 0, "range_max": 120 if cid == "methanol" else 2},
    ]
    chem = {
        "id": cid, "name": name, "fluid": fluid, "supply_node": sup, "injection_node": inj,
        "isolation_valve": f"CIV-{num}", "control_valve": f"CIMV-{num}", "check_valve": f"NRV-{num}",
        "pressure_transmitter": f"PT-{num}", "flow_transmitter": f"FT-{num}",
        "pump": {"discharge_pressure_bara": pump, "static_pressure_bara": static, "running": True},
        "injection_temperature_c": 4, "display_unit": unit, "target_min": tmin, "target_max": tmax, "color": color,
    }
    if cid == "methanol":
        # Second methanol route: into the ANNULUS service line junction
        # (service-line flushing / annulus bullheading), from the same pump.
        bnodes += [
            {"id": "SUP_MEOH_ANN", "name": "Methanol to annulus service line: SDU supply", "elevation_m": -1150, "zone": fluid},
            {"id": "N_MIV_IN", "name": "Methanol to annulus service line: line at tree", "elevation_m": -1195, "zone": fluid},
            {"id": "N_MIV_A", "name": "Methanol to annulus service line: downstream of MIV", "elevation_m": -1195, "zone": fluid,
             "initial_pressure_bara": 15},
        ]
        boundaries.append({"node": "SUP_MEOH_ANN", "pressure_bara": pump, "description": "Methanol pump discharge (annulus route) at the SDU"})
        belements += [
            {"id": "CL-305", "type": "pipe", "role": "injection_line", "name": "Methanol line to annulus service line (12.7 mm, 5 km)",
             "from": "SUP_MEOH_ANN", "to": "N_MIV_IN", "length_m": 5000, "inner_diameter_m": 0.0127, "roughness_m": 1.5e-6,
             "hydraulic_segments": 5},
            {"id": "MIV301", "type": "valve", "tag": "MIV-301", "valve_type": "injection_isolation",
             "name": "Methanol injection valve (annulus service line)", "from": "N_MIV_IN", "to": "N_MIV_A",
             "bore_diameter_m": 0.01, "loss_coefficient_open": 2.0, "full_stroke_time_s": 10, "actuation_delay_s": 2,
             "nominal_stroke_time_s": 12, "initial_position_pct": 0},
            {"id": "NRV305", "type": "check_valve", "tag": "NRV-305", "name": "Methanol non-return valve (annulus service line)",
             "from": "N_MIV_A", "to": "N_ANN_SVC", "cracking_pressure_bar": 0.5, "cv": 0.1},
        ]
        instruments_extra.append({"tag": "FT-305", "type": "flow", "description": "Methanol flow into annulus service line (MIV)",
                                  "element": "MIV301", "range_min": 0, "range_max": 120})
        chem.update({"annulus_supply_node": "SUP_MEOH_ANN", "annulus_valve": "MIV-301", "annulus_check_valve": "NRV-305",
                     "annulus_flow_transmitter": "FT-305"})
    chemicals.append(chem)

# analysers
analysers = []
resp = lambda res: {"time_constant_s": 20, "update_interval_s": 30, "resolution": res}
for cid, short, name, *_rest in chem_defs:
    unit = _rest[-4]
    rng = (0, 25) if unit == "vol%" else (0, 1000)
    res = 0.01 if unit == "vol%" else 0.1
    code = {"methanol": "51", "corrosion_inhibitor": "52", "biocide": "53", "wax_inhibitor": "54"}[cid]
    analysers.append({"tag": f"AT-{code}1", "type": "concentration", "chemical": cid, "unit": unit,
                      "description": f"{name} concentration, flowline mid-point (2.5 km)", "element": "FL-101", "distance_m": 2500,
                      "range_min": rng[0], "range_max": rng[1], "response": resp(res)})
    analysers.append({"tag": f"AT-{code}2", "type": "concentration", "chemical": cid, "unit": unit,
                      "description": f"{name} concentration at flowline arrival", "node": "N_ARR",
                      "range_min": rng[0], "range_max": rng[1], "response": resp(res)})
analysers.insert(0, {"tag": "AT-510", "type": "concentration", "chemical": "methanol", "unit": "vol%",
                     "description": "Methanol concentration downstream of choke", "node": "N_DC",
                     "range_min": 0, "range_max": 25, "response": resp(0.01)})
instruments_extra += analysers

# ------------------------------------------------------------------ layout
# Bore x=560, annulus x=470, wing y=230, choke column x=900.
P = lambda x, y: {"x": x, "y": y}
BORE, ANN, WING, CHK = 560, 470, 230, 900
layout = {
    "width": 1440, "height": 720,
    "nodes": {
        # production bore (vertical), wing (horizontal), choke at the wing end, flowline down to the seabed
        "RES": P(BORE, 706), "N_BH": P(BORE, 672), "N_SCSSV_U": P(BORE, 612), "N_SCSSV_D": P(BORE, 575),
        "N_TREE": P(BORE, 470), "N_PMV_PWV": P(BORE, WING), "N_SWAB_CAP": P(BORE, 140),
        "N_UC": P(CHK, WING), "N_DC": P(CHK, 330), "N_ARR": P(1300, 460),
        # annulus (left of the bore) and service line leaving left
        "ANN_BTM": P(ANN, 665), "ANN_TOP": P(ANN, 470), "N_AMV_AWV": P(ANN, 300), "N_ANN_SVC": P(ANN, 180),
        "N_SVC_L": P(370, 180), "ANN_VENT": P(60, 180),
        # methanol into the annulus service-line junction (from above)
        "SUP_MEOH_ANN": P(ANN, 48), "N_MIV_IN": P(ANN, 80), "N_MIV_A": P(ANN, 125),
        # chemical lines from off-page SDU connectors: metering valve outboard, isolation valve at the bore
        "SUP_MEOH": P(850, 280), "N_MEOH_IN": P(810, 280), "N_MEOH_A": P(730, 280), "N_MEOH_B": P(650, 280),
        "SUP_CI": P(1190, WING), "N_CI_IN": P(1150, WING), "N_CI_A": P(1070, WING), "N_CI_B": P(990, WING),
        "SUP_BIO": P(1190, 330), "N_BIO_IN": P(1150, 330), "N_BIO_A": P(1070, 330), "N_BIO_B": P(990, 330),
        # downhole chemical line (bottom left), through the annulus to the mandrel
        "SUP_WAX": P(40, 440), "N_WAX_IN": P(140, 440), "N_WAX_A": P(220, 440), "N_WAX_B": P(300, 440),
        "N_WAX_DH": P(520, 575),
    },
    # NOTE: every element whose base-scenario waypoints must be removed is
    # listed with an empty list (layout dicts are deep-merged with the parent)
    "waypoints": {
        "PWV": [],
        "CHOKE": [],
        "FL-101": [P(CHK, 540), P(1300, 540)],
        "XOV": [P(BORE, 300)],
        "NRV301": [P(BORE, 280)],
        "CL-304DH": [P(440, 440), P(440, 575)],
    },
    "symbol_fraction": {"XOV": 0.28, "NRV301": 0.32},
    "instruments": {
        "PT-001": P(660, 672), "TT-001": P(660, 672),
        "PT-101": P(660, 455), "TT-101": P(660, 455),
        "PT-104": P(670, 180), "PT-105": P(650, 120),
        "PT-102": P(CHK, 170), "TT-102": P(CHK, 170),
        "PDT-101": P(1020, 280), "FT-101": P(1130, 280),
        "PT-103": P(800, 400), "TT-103": P(800, 400),
        "PT-202": P(1035, 600), "TT-202": P(1035, 600),
        "PT-201": P(1380, 515), "TT-201": P(1380, 515),
        "PT-401": P(380, 505), "TT-401": P(380, 505), "PT-402": P(380, 300), "PT-403": P(290, 140),
        "PT-301": P(810, 330), "FT-301": P(690, 330), "FT-305": P(390, 95),
        "PT-302": P(1130, 180), "FT-302": P(1010, 180),
        "PT-303": P(1130, 380), "FT-303": P(1010, 380),
        "PT-304": P(110, 395), "FT-304": P(220, 395),
        "AT-510": P(800, 452),
        "AT-511": P(1180, 585), "AT-521": P(1180, 585), "AT-531": P(1180, 585), "AT-541": P(1180, 585),
        "AT-512": P(1368, 372), "AT-522": P(1368, 372), "AT-532": P(1368, 372), "AT-542": P(1368, 372),
    },
    "annotations": [
        {"type": "rect", "x": 350, "y": 95, "w": 610, "h": 395, "label": "SUBSEA PRODUCTION TREE (XT)", "label_position": "top-right"},
        # tree body (valve block) behind the production bore, and the tree cap above the swab valve
        {"type": "body", "x": BORE - 13, "y": 132, "w": 26, "h": 340},
        {"type": "cap", "x": BORE - 34, "y": 124, "w": 68, "h": 9, "label": "TREE CAP"},
        {"type": "line", "x1": 20, "y1": 495, "x2": 1420, "y2": 495, "x": 1000, "y": 489, "label": "SEABED  -1200 m MSL"},
        {"type": "rect", "x": 1240, "y": 440, "w": 120, "h": 40, "label": "MANIFOLD"},
        {"type": "connector", "x": 60, "y": 180, "direction": "left", "label": "Annulus service line (host)"},
        {"type": "connector", "x": ANN, "y": 48, "direction": "up", "label": "MeOH (SDU)"},
        {"type": "connector", "x": 850, "y": 280, "direction": "right", "label": "MeOH (SDU)", "label_at": "below"},
        {"type": "connector", "x": 1190, "y": WING, "direction": "right", "label": "Corr. inhibitor (SDU)", "label_at": "beyond"},
        {"type": "connector", "x": 1190, "y": 330, "direction": "right", "label": "Biocide (SDU)", "label_at": "beyond"},
        {"type": "connector", "x": 40, "y": 440, "direction": "left", "label": "Wax inhibitor (SDU)"},
        {"type": "text", "x": 670, "y": 716, "text": "RESERVOIR  -3700 m TVDSS   (vertical scale compressed - schematic, not to scale)"},
    ],
}

scenario = {
    "extends": "base_single_phase",
    "id": "subsea_dynamic_base",
    "name": "Dynamic subsea system - tree, annulus & chemical injection (illustrative)",
    "description": ("Base-case producer with the DYNAMIC model: compressible line-pack, wellbore storage and a radial reservoir "
                    "transient; vertical Xmas tree with PMV, PWV, swab valve and tree cap, production choke at the end of the "
                    "wing; A-annulus with AMV/AWV/XOV and annulus service line valve; methanol (tree bore and annulus service "
                    "line), corrosion-inhibitor, biocide and wax-inhibitor injection circuits; transmitters for valve integrity "
                    "testing. All data are ILLUSTRATIVE training values."),
    "nodes": nodes,
    "element_overrides": {
        "TBG-LOWER": {"wall_thickness_m": 0.0094, "hydraulic_segments": 8},
        "TBG-UPPER": {"wall_thickness_m": 0.0094, "hydraulic_segments": 3},
        "FL-101": {"wall_thickness_m": 0.0127, "hydraulic_segments": 20},
        "SCSSV": {"actuation_delay_s": 1, "nominal_stroke_time_s": 11},
        "PMV": {"actuation_delay_s": 2, "nominal_stroke_time_s": 32},
        "PWV": {"actuation_delay_s": 2, "nominal_stroke_time_s": 32},
        "CHOKE": {"actuation_delay_s": 1},
    },
    "dynamics": {
        "mode": "dynamic",
        "segment_length_m": 250,
        "transport_cells_per_segment": 5,
        "reservoir": {"net_thickness_m": 20, "porosity": 0.2, "total_compressibility_1_bar": 1.5e-4,
                      "wellbore_radius_m": 0.108, "drainage_radius_m": 300, "radial_cells": 14},
        "annulus_thermal": {"elements": ["ANN-A"], "time_constant_s": 21600, "tubing_weight": 0.6,
                            "tubing_elements": ["TBG-LOWER", "TBG-UPPER"], "geothermal_mean_c": 50},
        "default_response": {
            "pressure": {"time_constant_s": 0.5, "resolution": 0.01},
            "differential_pressure": {"time_constant_s": 0.5, "resolution": 0.01},
            "temperature": {"time_constant_s": 15, "resolution": 0.05},
            "flow": {"time_constant_s": 2, "resolution": 0.1},
        },
    },
    "subsystems": {"fluids": fluids, "nodes": bnodes, "elements": belements, "boundaries": boundaries, "instruments": instruments_extra},
    "chemicals": chemicals,
    "integrity_tests": [
        {"id": "pmv_inflow", "name": "PMV inflow (leak-off) test - tree cavity", "type": "inflow", "test_node": "N_PMV_PWV",
         "pressure_transmitter": "PT-104", "stabilisation_s": 300, "duration_s": 900, "max_change_bar": 3,
         "description": "Close PMV, bleed the cavity to flowline pressure through PWV, close PWV, then monitor PT-104 for "
                        "build-up from tubing pressure across the closed PMV."},
        {"id": "cavity_hold", "name": "Tree cavity pressure-hold test (MeOH pressurised)", "type": "pressure_hold",
         "test_node": "N_PMV_PWV", "pressure_transmitter": "PT-104", "stabilisation_s": 600, "duration_s": 900, "max_change_bar": 5,
         "description": "With PMV, PWV and SV closed, pressurise the cavity with methanol (open CIV-301), close CIV-301, then "
                        "monitor PT-104 for decay across the PMV / PWV / SV seats."},
        {"id": "sv_inflow", "name": "Swab valve inflow test - tree cap", "type": "inflow", "test_node": "N_SWAB_CAP",
         "pressure_transmitter": "PT-105", "stabilisation_s": 120, "duration_s": 600, "max_change_bar": 3,
         "description": "With SV-101 closed and the tree bore at production pressure, monitor the tree cap (PT-105) for "
                        "build-up across the closed swab valve."},
        {"id": "amv_inflow", "name": "AMV inflow test - annulus cavity", "type": "inflow", "test_node": "N_AMV_AWV",
         "pressure_transmitter": "PT-402", "stabilisation_s": 120, "duration_s": 600, "max_change_bar": 3,
         "description": "Close AMV, bleed the AMV-AWV cavity through AWV and SLV, close AWV and monitor PT-402."},
        {"id": "pwv_stroke", "name": "PWV stroke test", "type": "stroke", "valve": "PWV-101", "stroke_tolerance_pct": 15},
        {"id": "pmv_stroke", "name": "PMV stroke test", "type": "stroke", "valve": "PMV-101", "stroke_tolerance_pct": 15},
        {"id": "sv_stroke", "name": "Swab valve stroke test", "type": "stroke", "valve": "SV-101", "stroke_tolerance_pct": 15},
    ],
    "briefing": [
        "Dynamic model: every reading evolves over simulated time from mass, momentum and energy balances.",
        "Try closing PWV-101: the valve finishes moving in ~32 s, but tree and downhole pressures keep building for hours (wellbore storage + reservoir transient).",
        "Open CIV-301 to inject methanol into the tree bore and follow the concentration front to AT-510, AT-511 and AT-512.",
        "Open MIV-301 to send methanol into the annulus service line (flushing to host through SLV-101, or into the annulus with AWV/AMV open).",
    ],
    "layout": layout,
}
with open(out, "w", encoding="utf-8") as f:
    json.dump(scenario, f, indent=2)
print("written", out)
