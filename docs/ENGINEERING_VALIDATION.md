# Engineering validation

This document is the single view of how each SubseaSim model is verified:

- against what reference;
- by which automated test;
- with what remaining limitation.

The detailed equations are in the per-model documents. Run the checks with:

    backend/.venv/Scripts/python -m pytest          (backend: ~270 tests)
    cd frontend && npx vitest run                   (component tests)
    cd frontend && PW_CHANNEL=msedge npx playwright test   (end-to-end workflows)

**Wording used below**

- **Verified** means checked against an independent reference: a published
  chart or table, a closed-form limit, or a hand calculation.
- **Consistent** means checked against conservation laws or the model's own
  alternative solution.
- **Not validated** means not compared with field or laboratory data for
  the user's equipment.
- **Field data.** None of the models in SubseaSim is validated against field
  data. All scenario data are illustrative.

## 1. Single-phase hydraulics and dynamics

Model documents: `SIMULATION_MODEL.md`, `DYNAMIC_SIMULATION_MODEL.md` and
`PIPELINE_TRANSIENT_MODEL.md`.

| Check | Reference | Test |
|---|---|---|
| Friction factor | Churchill (1977) against Colebrook-White | `test_friction_and_restrictions.py` |
| Steady series solution | Hand-calculated pressure budgets | `test_hydraulics_reference.py` |
| Dynamic → steady convergence, line pack, wave timing | Steady solver; analytic LC ladder | `test_dynamic.py` |
| Determinism (fixed step) | Identical results for any partition | `test_dynamic.py` |
| Unit conversions | Exact definitions | `test_units.py` |

## 2. Christmas tree workstation layout

Document: `CHRISTMAS_TREE_LAYOUT.md`. Tests: `test_xt_workstation.py` and
`xt.test.tsx`.

- Every layout reference resolves to a model component.
- Every valve and every main transmitter is drawn.
- Every item carries one plain engineering tag (PMV-101, PT-104, HSV-101);
  there are no display aliases.
- Positions match the photo measurements within 1.5 px.
- Line ends are connected, and components sit on their flow paths.
- Moving the layout does not change any reading.
- Readings respond to valve operations.

## 3. Three-phase PVT and multiphase flow

Document: `MULTIPHASE_FLOW_MODEL.md`. Test: `test_multiphase.py`.

| Check | Reference | Tolerance |
|---|---|---|
| Gas Z factor (DAK) | Standing-Katz chart, 5 points | ± 0.02 |
| Bubble point (Standing) | Hand evaluation of Standing's equation | 1e-6 |
| Gas viscosity (Lee-Gonzalez-Eakin) | Methane at 1 atm, 20 °C (NIST, 0.0110 cP) | 5 % |
| Beggs & Brill, single-phase limit | Colebrook-White Darcy-Weisbach | 2 % |
| Sachdeva choke, liquid limit | Orifice equation | 1e-9 |
| Sachdeva choke, gas limit | Isentropic critical ratio (2/(k+1))^(k/(k−1)) | 1e-6 |
| Choked flow independent of downstream pressure | Theory | exact |
| Component mass through the flash | Conservation | 1e-12 |
| Steady phase mass balances | Conservation | exact |
| Dynamic phase mass balances through transients | Conservation | < 1e-6 relative (observed ~1e-15) |
| Dynamic steady state against the marching solver | Alternative solution | 3 % flow, 3 bar |

**Not validated:** Beggs & Brill was derived from small-diameter air-water
data, and tubing use is an extrapolation. The PVT correlations are generic
and not fitted to a PVT report.

## 4. Multiphase flow meter

Document: `MPFM_MEASUREMENT_MODEL.md`. Test: `test_mpfm.py`.

- Slip, void-fraction and momentum-density identities.
- A noise-free, matched meter inverts its simulated sensors to the true
  rates.
- Conversion from actual to standard volumes through Bo, Bg, Bw and Rs.
- The GUM dP contribution equals the analytic ½ σ/ΔP.
- Readings fall inside the stated uncertainty, and are reproducible.
- Diagnostics and faults trip as specified.
- In the integrated well, meter truth equals the simulated manifold flow.

**Not validated:** this is a representative meter, not a specific vendor's
instrument.

## 5. Sand production, screens and transport

Documents: `SAND_PRODUCTION_MODEL.md` and `SAND_TRANSPORT_MODEL.md`. Test:
`test_sand_choke.py`.

| Check | Reference |
|---|---|
| Critical BHFP | Hand evaluation of Willson et al. (2002) |
| Strength, depletion and water responses | Direction expected from theory |
| PSD quantiles | Log-normal fit reproduces the entered D10, D50 and D90 |
| Screen retention and damage | Closed form |
| Measured-unit conversions (kg/d, kg/h, g/s, pptb, ppm) | Hand calculation |
| Missing data | Reported as unavailable, with no made-up values |
| Measured sand history: CSV import, conversion, abnormal-increase trigger | Hand calculation; atomic rejection of bad files (`test_sand_measurements.py`) |
| Transport | Transit delay, then sand at the choke equals produced sand within 5 % |
| Sand detector SDT-101 | Reads and alarms once sand arrives; calibration bias, noise floor and minimum velocity as configured |

**Not validated:** the post-onset sand rate is empirical and must be
calibrated with field sand data. Deposition is screened but not simulated.

## 6. Choke erosion and maintenance

Documents: `CHOKE_EROSION_MODEL.md` and `CHOKE_MAINTENANCE_MODEL.md`. Tests:
`test_sand_choke.py` and `sand.test.tsx`.

| Check | Reference |
|---|---|
| DNV F(α), erosion ratio, straight-pipe outlet formula | Hand evaluation of the DNV-RP-O501 equations |
| Tungsten carbide wears far less than steel | Material constants |
| Velocity sensitivity follows Uⁿ | Exact |
| Cage open area; hole growth conserves volume | Geometry |
| Only the lowest rows erode at small openings | Geometry |
| Wear is linear in sand rate and in time | Model property |
| Calibration posterior | Closed-form Bayesian update |
| Health categories in order to Critical, with alarms | Configured thresholds |
| Erosion feedback raises Cv, and measured Cv tracking detects it | Integrated simulation |
| API RP 14E erosional velocity (supplementary) | Hand evaluation in US units; exact unit conversions (`test_api14e.py`) |

**Not validated:** generic geometry and impact angle. The DNV material
constants must be verified against the licensed document or vendor data.
Trim-specific accuracy requires the user's inspection records (the
calibration workflow exists for this).

## 6a. Choke cavitation and flashing screening

Document: `CHOKE_CAVITATION_MODEL.md`. Tests: `test_cavitation.py` and
`sand.test.tsx`.

| Check | Reference |
|---|---|
| Water saturation pressure | IAPWS-IF97 verification values (300, 500, 600 K), 1e-8 |
| FF, vena-contracta pressure, choked liquid ΔP | Hand evaluation of IEC 60534-2-1 |
| Cavitation index σ | Hand evaluation of (P1 − Pv)/(P1 − P2) |
| Regimes (two-phase inlet, outgassing, gaseous / vapour cavitation, flashing) | Pressure ordering expected from theory |
| σ limits never assumed; must decrease | Model property |
| Follows the simulated choke (opening → lower ΔP → higher σ) | Integrated simulation |

**Not validated:** this is screening. FL and the σ limits must come from the
manufacturer for this trim; collapse location and damage rate are not
computed.

## 7. Integrated system test: Exercise 7

Test: `test_training_integrated.py`. It plays the 14-stage integrated
scenario as an intern would, on one shared simulation state:

1. three-phase well, shut in;
2. water cut changed;
3. production started;
4. wing valve opened;
5. the MPFM reads all three phases within its uncertainty;
6. choke 30 → 40 %: the sanding risk index crosses 1;
7. sand detected on SDT-101;
8. choke 40 → 65 %: drawdown increases;
9. sand grows faster than drawdown;
10. sand reaches the choke after its transit time;
11. erosion rates by hole row;
12. cumulative wear over ≥ 365 days;
13. the inspection recommendation;
14. the uncertainty and confidence questions.

Predictions are resolved from what the run did, and every review is
generated from recorded observations.

The existing annulus, chemical injection, integrity-test and dynamic
pressure-behaviour suites run unchanged alongside these.

## 8. What would turn "verified" into "validated"

| Area | Data needed |
|---|---|
| PVT | Laboratory PVT report (Pb, Rs, Bo, viscosities) for the produced fluid |
| Flow model | Well-test rates and pressures at several choke steps |
| Sanding | Core TWC tests, stress data, sand-trap or SDT-101 detector history |
| Choke | Trim material and grade, cage drawings, the vendor Cv-versus-step table, inspection measurements with operating history |
| MPFM | Comparison with test-separator measurements |
| Cavitation | Manufacturer FL vs opening and σ limits for the trim; PVT-report bubble point |

All of these are inputs in the app. The models accept them without any code
change.
