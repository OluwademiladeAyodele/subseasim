# Choke erosion model

Source: `backend/app/simulation/sand/erosion.py` (physics) and
`backend/app/simulation/sand/system.py` (integration, calibration and
forecast). Inputs are edited on the **Sand & choke inputs** page.

## Scope and honesty statement

**Purpose.** The model estimates the material loss of a **plug and multi-hole
cage** production choke from sand. It is calibrated by inspections.

**Reference and edition.** It follows the generic particle-erosion approach
of **DNV-RP-O501**, *Managing sand production and erosion*. Material constants
are reproduced from the 2015 edition table **for verification by the user**
against the licensed document or vendor data. DNV-RP-O501 provides generic
models (straight pipe, bends, tees, reducers and a choke-gallery model). It
does **not** give a geometry-specific model for cage trims.

**How the trim model is labelled.**

- Uncalibrated, it is a **screening estimate**.
- It becomes a *calibrated estimate* once inspection data are entered.
- It becomes *validated* only after several consistent inspections.

API RP 14E erosional velocity is **not** used as an erosion model.

## 1. Inputs, all from the simulation state

| Quantity | Source |
|---|---|
| Upstream and downstream pressure, temperature | choke nodes of the dynamic network |
| Mass flow through the choke, composition (GOR, WC) | network link and transported composition |
| Free-gas mass fraction, liquid and gas densities | black-oil PVT at upstream conditions |
| Critical pressure ratio and choked state | Sachdeva model (as used for the flow) |
| Choke opening and effective area C_dA | actuator position, with the vendor Cv curve or characteristic and the current wear |
| Sand mass rate at the choke | transported sand × flow |

## 2. Particle velocity at the trim

The particle velocity is the jet velocity at the vena contracta of the
throttling cage holes, from the same Sachdeva solution that sets the flow:

    U = W / (C_dA · ρ_m2),   y = max(p₂/p₁, y_c)
    ρ_m2 = [x v_g1 y^(−1/k) + (1 − x)/ρ_l]⁻¹

For a liquid this reduces to `√(2ΔP/ρ)`. Particles are assumed to reach the
jet velocity. Fine particles that follow the flow and miss the walls are
**not** credited, which is conservative; the calibration factor absorbs this.

## 3. Trim material loss

Mass of material removed per kg of sand:

    E_m = K · Uⁿ · F(α)                          (kg material / kg sand)

| Behaviour | F(α) |
|---|---|
| Ductile (steels, CRA) | `0.6 [sin α + 7.2(sin α − sin²α)]^0.6 [1 − e^(−20α)]` (DNV) |
| Brittle (tungsten carbide) | `2α/π` (linear approximation) |

Volume loss rate:

    dV/dt = C · E_m · ṁ_sand / ρ_material

C is the calibration factor (section 6).

**Material library** (DNV-RP-O501 table; verify before use):

| Material | K | n |
|---|---|---|
| Carbon steel | 2.0e-9 | 2.6 |
| Duplex | 2.0e-9 | 2.6 |
| Inconel | 2.53e-9 | 2.6 |
| WC DC-05 | 1.1e-10 | 2.3 |
| WC CS-10 | 3.5e-10 | 2.2 |
| WC CR-37 | 8.8e-11 | 2.5 |

Custom materials (vendor K, n, density, behaviour) can be entered.

## 4. Where the material is lost: trim, cage holes, plug, body, outlet

**Cage holes.**

- Rows are entered as (axial position, diameter, count).
- The plug lift is `step / steps × stroke`.
- Each hole's open area is the uncovered circular segment.
- The cage share `(1 − plug_share)` of the volume loss is distributed over
  the **open** rows in proportion to their open area (flow share).
- Each hole grows by `Δd = 2 ΔV_hole / (π d t_wall)`.
- At small openings only the lowest rows erode. This matches the
  concentrated wear at throttling holes seen in the operator's cage
  photographs.

**Cv rise.**

- The effective area, and therefore Cv, is proportional to the open area:
  `Cv_worn(step) = Cv_new(step) × A_open,worn / A_open,new`.
- With *erosion feedback* on, the simulated choke uses the worn Cv. Flows,
  pressures, the MPFM and Cv tracking then respond to the predicted wear.

**Plug and seat edge.**

- The plug share of the volume is spread over a band of
  π · D_plug × wall thickness.
- Plug loss leads to seat leakage when closed.

**Body and gallery (screening).**

- Generic impingement of the inlet jet on the gallery:
  `ΔT/dt = E_m(U_inlet, 90°) ṁ / (ρ A_inlet)`.
- Labelled as screening.
- Body and gallery are one location here. In a plug-and-cage angle choke the
  gallery is the annular space inside the body around the cage, so splitting
  them would need geometry that has not been entered.

**Outlet wall (DNV straight-pipe model, steel).**

    E_L [mm/yr] = 2.5×10⁻⁵ U²·⁶ D⁻² ṁ_p

**Rates.** Wear rates are computed directly, so they are independent of the
integration step. Wear is integrated every 10 simulated seconds (immediately
while the choke moves), over the entered operating history, and during
fast-forward.

### API RP 14E erosional velocity (supplementary screening)

    Ve [ft/s] = C / √ρ_m [lb/ft³]      (reported in m/s for ρ_m in kg/m³)

- C is an input, with a default of 100 (API RP 14E, continuous, solids-free
  service; the API gives 125 for intermittent service).
- The check is made at three locations, using the no-slip mixture velocity
  and density from the simulated flow:
  - the body gallery (inlet conditions; needs the gallery diameter);
  - the choke outlet bore (outlet conditions; needs the bore);
  - the flowline.
- A location whose geometry has not been entered is reported as
  unavailable.
- When sand is present the panel warns that the API requires C to be
  reduced for solids-laden flow, so "below Ve" does not mean erosion-free.
- **It is not a sand-erosion model and not a choke-geometry model.** It does
  not enter the health category or the remaining life. The DNV results
  govern.

## 5. Cumulative wear and remaining life

**Criteria.** Each criterion compares the wear used with the site
**allowance** (acceptance criteria):

- hole diameter increase;
- Cv increase at the reference step;
- plug loss;
- body wall loss;
- outlet wall loss.

**Remaining life at the current conditions.**

    t₅₀ = (allowance − used) / current rate
    P10 / P90 = t₅₀ · exp(∓1.2816 σ)

It is also given as **sand mass** to the limit and **liquid volume** to the
limit, which remove the time assumption.

**Uncertainty (log-normal, 1σ in ln).**

| Component | Value |
|---|---|
| Erosion model | uncalibrated `ln 5 / 1.645` (factor-5 range); posterior after inspections |
| Sand rate | measured: the entered uncertainty; predicted: `ln 5 / 1.645` |
| Particle velocity | `n × 5 %` |

The combined σ is the root-sum-square of these components.

**The forecast is never a date.** The UI shows the range and the confidence
category.

## 6. Calibration by inspection

An inspection record holds the service days and the measured maximum hole
increase, Cv increase or plug loss. It is compared with the model's
**uncalibrated** prediction at that service time. The service time must be
covered by the operating history; trim replacement resets the wear epoch.

**Log-normal Bayesian update:**

    ln C = Σ ln(measured/predicted)/σ_obs² / (1/σ₀² + n/σ_obs²)
    σ_C  = (1/σ₀² + n/σ_obs²)^(−½)
    σ₀ = ln 5/1.645,  σ_obs = 0.35

**Confidence categories:**

| Category | Condition |
|---|---|
| unavailable | missing trim material or geometry |
| screening estimate | – |
| engineering estimate | measured sand, uncalibrated erosion model |
| calibrated estimate | ≥ 1 inspection |
| validated | ≥ 2 consistent inspections |

## 7. Extension points

- Vendor or CFD erosion data: supply a custom material and impact angle, or
  replace `CageGeometry.distribute` with a vendor wear map.
- Particle tracking (impact location, angle and velocity) can replace the
  jet-velocity and fixed-angle assumption.
- Experimental erosion-test results can be entered as custom K and n.

## 8. Limitations

- Generic geometry with a single impact angle per trim; no flow-field
  resolution.
- Erosion-corrosion, cavitation, liquid-droplet impingement and hydrate,
  scale or sand plugging are not modelled.
- Body and gallery results are screening only.
- Particle size does not change erosion per kg; it acts only through screen
  retention.

## 9. Verification

`backend/tests/test_sand_choke.py` checks:

- the DNV F(α), erosion ratio and straight-pipe formula against hand
  evaluation;
- tungsten carbide wears far less than steel;
- velocity sensitivity follows Uⁿ;
- the ductile peak angle;
- cage open area against a hand calculation, and volume conservation of hole
  growth;
- only the lowest rows erode at small openings;
- wear gives a Cv increase;
- linearity in sand rate and in operating time;
- the calibration posterior against the closed-form value, with narrowed
  uncertainty;
- feedback raises the simulated Cv, and measured Cv tracking detects it.

`backend/tests/test_api14e.py` checks:

- Ve against the US-unit formula (exact unit definitions);
- scaling with C and with 1/√ρ;
- the three locations from the simulated flow;
- the warning when sand is present;
- that missing geometry is reported, not assumed;
- that the C input reaches the result.
