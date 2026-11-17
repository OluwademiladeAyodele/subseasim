# Scenarios

Scenario files live in `backend/app/scenarios/data/*.json` and are validated against
`backend/app/models/scenario.py` when the server starts (invalid files fail loudly).
**All shipped data are illustrative.**

## Shipped scenarios

### `base_single_phase` — Base case

A single oil producer in 1200 m water depth.

| Item | Value (illustrative) |
|---|---|
| Fluid | ρ 850 kg/m³, μ 5 cP, c_p 2000 J/(kg·K), β 7e-4 1/K, bubble point 40 bara |
| Reservoir | 380 bara, 95 °C at −3700 m TVDSS, PI 20 (m³/d)/bar |
| Tubing | ID 100.5 mm, 1950 m below the SCSSV (−3700 → −1800 m) + 610 m above it (to the tree at −1195 m), U = 10 W/m²K, geothermal ambient 95 → 25.8 → 4 °C (linear 4 °C at the seabed to 95 °C at the reservoir) |
| SCSSV-101 | Flapper, bore 100 mm, K 0.3, stroke 10 s, discrete |
| PMV-101 / PWV-101 | Gate, bore 130 mm, K 0.1, stroke 30 s, discrete |
| CHK-101 | Cv_max 100, equal-percentage R = 30, stroke 180 s, initially 30 % |
| FL-101 | 5 km, ID 152.4 mm, ε 45 µm, rising 45 m to the manifold, U = 3 W/m²K, seabed 4 °C |
| Boundary | Manifold / riser base at 60 bara (−1150 m) |
| Training rule | Warn when opening an isolation valve against > 35 bar |

Resulting operating point (calculated by the model, at 30 % choke): ≈ 985 m³/d,
P_wf ≈ 331 bara, tree ≈ 116 bara, choke ΔP ≈ 51 bar, arrival ≈ 57 °C. With PWV closed the
tree shut-in pressure is ≈ 171 bara (= P_res − ρgΔz).

### `ex03_choke_operation` — Exercise 3

`extends: base_single_phase` with the choke initially at 20 %.

## File format

```jsonc
{
  "id": "my_scenario",
  "extends": "base_single_phase",          // optional: inherit and override
  "name": "...", "description": "...",
  "data_classification": "ILLUSTRATIVE - not field data",
  "fluid":     { "model": "constant_property_liquid", "density_kg_m3": 850, ... },
  "reservoir": { "pressure_bara": 380, "temperature_c": 95, "productivity_index_m3d_per_bar": 20 },
  "boundary":  { "node": "N_ARR", "pressure_bara": 60, "fluid_temperature_c": 4 },
  "reservoir_node": "RES",
  "nodes":    [ { "id": "N_BH", "name": "...", "elevation_m": -3700 }, ... ],
  "elements": [
    { "id": "IPR", "type": "inflow", "from": "RES", "to": "N_BH", "name": "..." },
    { "id": "TBG", "type": "pipe", "role": "tubing", "length_m": ..., "inner_diameter_m": ...,
      "roughness_m": ..., "overall_htc_w_m2k": ..., "ambient_temperature_inlet_c": ...,
      "ambient_temperature_outlet_c": ..., "thermal_cells": 20, ... },
    { "id": "PMV", "type": "valve", "tag": "PMV-101", "valve_type": "master",
      "bore_diameter_m": 0.13, "loss_coefficient_open": 0.1, "supports_intermediate": false,
      "full_stroke_time_s": 30, "initial_position_pct": 100, "available": true, ... },
    { "id": "CHOKE", "type": "choke", "tag": "CHK-101", "cv_max": 100,
      "characteristic": "equal_percentage", "rangeability": 30, ... }
  ],
  "element_overrides": { "CHOKE": { "initial_position_pct": 20 } },   // with extends
  "instruments": [
    { "tag": "PT-101", "type": "pressure", "node": "N_TREE", "range_min": 0, "range_max": 690, "description": "..." },
    { "tag": "PDT-101", "type": "differential_pressure", "high_node": "N_UC", "low_node": "N_DC", ... }
  ],
  "training_rules": { "max_opening_differential_bar": 35 },
  "layout": { "width": 1200, "height": 520, "nodes": {...}, "waypoints": {...},
              "instruments": {...}, "annotations": [...] }
}
```

Rules enforced on load:

* Elements must form one chain from `reservoir_node` to `boundary.node`, starting with
  the single `inflow` element. No branches, loops or unused nodes.
* Tags must be unique. Discrete valves start at 0 or 100 %.
* A pipe's elevation change must not exceed its length.
* Instrument ranges are in bara (pressure), bar (differential), °C, or m³/d.
* `layout` is presentation only. Every node needs coordinates; `waypoints` bend
  pipes; `annotations` add frames, the seabed line and labels.

## Adding a scenario

1. Copy or `extends` an existing file. Give it a new `id`.
2. Keep `data_classification` truthful. Do not add confidential field data without
   authorisation.
3. Restart the backend (the catalogue is loaded once).
4. Run `pytest`. `test_all_scenarios_build_and_solve` checks every scenario.

## Release 2: dynamic scenarios

All `dyn_*` scenarios extend `subsea_dynamic_base`, which extends `base_single_phase`.
The production path is unchanged. The dynamic additions are:

| Scenario | Purpose (the intern performs the operation; every response is calculated) |
|---|---|
| `subsea_dynamic_base` | Full system: radial reservoir transient; vertical Xmas tree with PMV, PWV, swab valve (SV-101) and tree cap (PT-105), production choke at the end of the wing; A-annulus (AMV/AWV/XOV) with the annulus service line valve (SLV-101) at the junction where the methanol line (MIV-301 / NRV-305) joins it; four chemical-injection circuits (metering valve outboard, isolation valve at the bore); tree-cavity transmitter; mid-line and arrival analysers. |
| `xt_230xp22b` | Same dynamic system arranged and tagged as the reference control-system page 'Production 230XP22B' (architecture only - all values simulated): XOV from the service-line junction to the tree cavity, chemical injection into the wing upstream of PWV, methanol injection valves MIV3015 / MIV3016 either side of PWV, downhole chemical below the SCSSV, LP/HP selector valves and SCM A/B headers with fail-safe closure, display aliases for the reference tag numbers, and a separate workstation layout file. See `docs/CHRISTMAS_TREE_LAYOUT.md`. |
| `xt_230xp22b_multiphase` | **Default for new sessions.** The XT workstation with the three-phase black-oil fluid (oil, gas, water; GOR 120 Sm3/Sm3, water cut 30 %, 35 API): Beggs & Brill flow patterns and holdup, Sachdeva choke (can run critical), transported composition, in-situ flow metering, manifold multiphase flow meter MPFM-201 (see `docs/MPFM_MEASUREMENT_MODEL.md`). Single-phase mode available from Conditions / Multiphase. See `docs/MULTIPHASE_FLOW_MODEL.md`. |
| `dyn_a_pressure_buildup` | A. Close PWV-101 and watch PT-101 build up from ~98 bara toward ~221 bara (wellbore storage then reservoir diffusion). |
| `dyn_b_valve_closure` | B. Production valve closure: upstream build-up, downstream drain-down, flow decay along the line. |
| `dyn_c_methanol_injection` | C. Open CIV-301: methanol injection, mixing, transport to AT-510/511/512, mixing cooling at TT-103. |
| `dyn_d_flowrate_change` | D. CI and biocide injecting at steady state. Stop biocide, change the choke, compare arrival times. |
| `dyn_e_injection_shutdown` | E. Methanol at steady state along the line. Close CIV-301: chemical already in the line keeps moving. |
| `dyn_f_leaking_pmv` | Integrity: PMV seat leak and slow PWV actuator; inflow and stroke tests fail. |

New file sections (all optional; Release 1 files are valid unchanged):

* `dynamics`: `mode` (`dynamic`/`steady`), `segment_length_m`, `transport_cells_per_segment`,
  `minimum_node_volume_m3`, `reservoir` (radial transient), `annulus_thermal`,
  `clock_start_s`, `default_response` (per instrument type).
* `subsystems`: `fluids` (zones), `nodes` (with `zone`), `elements` (pipe, valve, choke,
  `check_valve`), `boundaries` (fixed pressures), `instruments` (extra transmitters).
  Branch elements may connect to production nodes (injection points, crossover).
* `chemicals`: one entry per circuit (supply node, injection node, isolation, metering and
  check valve tags, pump, transmitters, display unit, illustrative dosage band, colour).
* `integrity_tests`: presets shown in the Integrity panel.
* `briefing`: text lines shown to the intern.
* Node fields `volume_m3`, `initial_pressure_bara`, `heat_loss_ua_w_k`, `thermal_mass_j_k`;
  pipe fields `wall_thickness_m`, `youngs_modulus_gpa`, `wall_compliance_1_bar`,
  `flow_area_m2`, `hydraulic_segments`; valve fields `actuation_delay_s`,
  `close_stroke_time_s`, `nominal_stroke_time_s`, `seat_leak_area_mm2`; instrument fields
  `element` + `distance_m`, `chemical`, `unit`, `response`.
* `element_overrides` in a child scenario may also patch `subsystems.elements`.

`subsea_dynamic_base.json` is generated by `backend/scripts/generate_subsea_dynamic_base.py`; `xt_230xp22b.json` and its layout `app/scenarios/layouts/xt_230xp22b.json` by `backend/scripts/generate_xt_230xp22b.py` (run both from `backend/`).
Edit the generator rather than the JSON, then run it from `backend/`. Keep node, element and instrument tags consistent,
and run `pytest` (`test_all_scenarios_build_and_solve` builds every scenario in both models).
