# MPFM measurement model

**MPFM-201** is a virtual multiphase flow meter on the manifold production
path. In the `xt_230xp22b` scenarios it sits at node `N_ARR`, set by
`location_node` in `MPFMConfig`.

**It measures the simulated flow.** Its readings come from the simulated
three-phase flow at that location: the same pressure, temperature, mass flow
and transported composition used by every other module. No rates are entered
by hand.

**It is a representative model.** It is a documented, generic meter that
combines the two principles most commonly used together in commercial MPFMs:
a venturi differential pressure and a dual-energy gamma measurement of phase
fractions. It does not reproduce any manufacturer's proprietary method. Other
principles (microwave or impedance water-cut, Coriolis, cross-correlation)
are not implemented.

**When it runs.** The meter needs the three-phase (black-oil) fluid model. In
single-phase mode it reports `NOT_MODELLED`.

Source code: `backend/app/simulation/mpfm/meter.py`.

## 1. Sensors, simulated from the true state at the meter

**Inputs from the simulation**

- p, T: node pressure and temperature;
- W: mass flow into the meter node;
- GOR, WC: local transported composition;
- the true black-oil fluid.

**Phase split.** The flash gives the in-situ oil, gas and water volumes,
`q_o, q_g, q_w`, and the free-gas mass fraction `x`.

**Slip.**

- Chisholm slip ratio: `S = (ρ_l/ρ_g)^(1/4)`.
- In-situ gas void fraction: `α = 1 / (1 + S (1−x)/x · ρ_g/ρ_l)`.
- Because S > 1, α is lower than the flowing gas volume fraction: gas slips
  past the liquid.
- Liquid is split into oil and water by volume.

**Venturi differential pressure.** Throat diameter `d_t = β D`, with
`A_t = π d_t²/4`.

    ΔP = (W / (C_d,actual A_t))² (1 − β⁴) / (2 ρ_mom)
    ρ_mom = [ x²/(α ρ_g) + (1−x)²/((1−α) ρ_l) ]⁻¹      (momentum density)

**Dual-energy gamma transmission** across the throat, path length `d_t`:

    A_E = d_t Σ α_i μ_i,E ρ_i        E = low (~32 keV), high (~356 keV)

- `μ_i,E` are representative mass attenuation coefficients for a
  Ba-133-type source, approximate values from NIST XCOM (table in the code).
- The water low-energy coefficient increases with salinity:
  `μ_w = (1−w) μ_water + w μ_NaCl`.
- Counts are `N = N₀ t e^(−A)`, with Poisson (√N) noise, for each energy.

**Pressure and temperature transmitters.** Gaussian noise, with
`pressure_sigma_bar` and `temperature_sigma_k`.

## 2. Flow computer

The flow computer uses only the measured signals and the meter's own
configuration.

1. **Phase fractions.** Solve
   `[μ_oL ρ_o, μ_gL ρ_g, μ_wL ρ_w; μ_oH ρ_o, μ_gH ρ_g, μ_wH ρ_w; 1, 1, 1] α = [A_L/d_t, A_H/d_t, 1]`.
   - Densities come from the **meter's PVT**, evaluated at the measured p and T.
   - Coefficients use the **meter's water salinity**.
   - Raw fractions are kept for the closure diagnostic, then clipped to
     [0, 1] and renormalised.
2. **Mass flow.** `W = C_d A_t √(2 ρ_mom ΔP / (1 − β⁴))`.
   - `meter_slip_model = chisholm`: x is recovered from α using the
     Chisholm slip, and ρ_mom is computed from (x, α).
   - `meter_slip_model = homogeneous`: `ρ_mom = Σ α_i ρ_i`, and the flowing
     fractions are taken equal to the in-situ fractions.
3. **Line-condition volumes.**
   - Chisholm: `q_g = x W/ρ_g`, `q_l = (1−x) W/ρ_l`, with liquid split by α_o : α_w.
   - Homogeneous: `q_i = α_i W / ρ_mix`.
4. **Standard conditions** (15 °C, 1.01325 bar, ISO 13443), from the meter's
   black-oil PVT:
   - `Q_oil,sc = q_o / Bo`;
   - `Q_gas,sc = q_g / Bg + Rs Q_oil,sc` (free gas plus gas dissolved in the oil);
   - `Q_water,sc = q_w / Bw`.
   - Water cut, GOR, GVF, LVF and total liquid follow from these.

**Actual vs standard volumes are never mixed.** The MPFM page shows three
separate tables:

- standard-condition production;
- actual volumes at meter conditions, with the meter's p and T stated;
- mixture quantities.

Mixture density is the in-situ (slip) density, which is what the gamma
densitometer sees.

Outputs are filtered with a first-order lag over the integration time.

## 3. Uncertainty

The uncertainty is a first-order GUM propagation through the flow computer.
Each input is perturbed by its standard uncertainty, the computation is
repeated, and the relative changes are combined in quadrature.

| Input | Standard uncertainty |
|---|---|
| ΔP | `dp_sigma_pct_full_scale` of the range ⊕ 0.25 % of reading |
| Gamma attenuation (each energy) | 1/√N, from the actual count rates |
| Pressure | `pressure_sigma_bar` |
| PVT densities / volume factors | `pvt_uncertainty_pct` |
| Discharge coefficient | `cd_uncertainty_pct` |
| Slip / flow regime (model) | `slip_uncertainty_table`, interpolated in GVF: 0.3 % (liquid) up to 20 % (GVF 0.99) |

**Reporting**

- Phase and total rates are expanded with k = 2 and given as % of reading.
- Water cut is given in absolute percentage points.
- The page shows the 1-sigma contribution of each input (the uncertainty
  budget).

**Refresh rate.** The propagation is refreshed every 30 simulated seconds, and
at once after a quality change, fault, calibration or fluid change.

**Tests**

- The ΔP contribution equals the analytic `½ σ_ΔP / ΔP` for `W ∝ √ΔP`.
- Uncertainty grows with GVF and at low flow.
- Readings with noise stay inside the stated uncertainty.
- Readings are reproducible for a given random seed.

## 4. Diagnostics and quality

| Code | Condition | Quality |
|---|---|---|
| `GAMMA_FAILED` | gamma detector fault | BAD (no phase rates) |
| `PHASE_FRACTION_INCONSISTENT` | raw fraction < −0.10 or > 1.10 | BAD |
| `PHASE_FRACTION_CLOSURE` | raw fraction outside −0.03 … 1.03 | DEGRADED |
| `DP_OVER_RANGE` | ΔP > `dp_max_bar` | BAD |
| `LOW_FLOW` / `LOW_FLOW_CUTOFF` | ΔP < `dp_min_bar` (< 20 % of it: rates reported as zero) | DEGRADED |
| `GVF_OUT_OF_ENVELOPE` | GVF > `gvf_max` (wet-gas regime) | DEGRADED |
| `DP_FROZEN` | ΔP identical over 30 updates (stuck transmitter) | DEGRADED |
| `PT_FAILED` | P/T transmitter fault; last good values used for PVT | DEGRADED |
| `CALIBRATION_DUE` | time since calibration > `calibration_interval_days` | DEGRADED |
| expanded liquid uncertainty > 20 % | – | DEGRADED |

Quality changes are written to the event log.

**Undetectable errors.** Systematic errors the meter cannot detect leave
the quality at **GOOD**, which is realistic:

- a water-salinity or PVT mismatch;
- a slowly drifting discharge coefficient;
- a dP zero offset.

The page shows *measured* next to *true* and marks in red any difference that
exceeds the stated uncertainty. The teaching point is that an instrument
reading is not the process value.

## 5. Faults and calibration

**Instructor faults** (`PUT /api/sessions/{id}/mpfm/faults`) change only the
signals the meter receives. The process is unaffected.

- `dp_offset_bar`: a dP zero offset;
- `dp_stuck`: the transmitter freezes at its last value;
- `gamma_failed`;
- `pt_failed`.

**Calibration** (`POST /api/sessions/{id}/mpfm/calibrate`) represents a field
calibration:

- a dP zero check, which removes the offset;
- the meter PVT updated from a fluid sample: true API, gas gravity, salinity
  and the current GOR and water cut at the meter;
- the discharge coefficient re-established;
- the calibration time recorded.

**What remains after calibration.** Hardware faults (stuck dP, failed gamma or
P/T) stay until they are cleared.

**Drift.** `cd_drift_pct_per_year` lets the actual discharge coefficient
drift away from the nominal value used by the flow computer.

## 6. Sand

**Sand has no effect on the readings.** The representative model has no
physically supported sand mechanism (for example erosion of the venturi, or
gamma attenuation by solids), so none is added. This follows the requirement
not to alter MPFM readings arbitrarily as sand concentration increases.

**Extension point.** A meter model with a documented sand effect can be added
in `compute()`.

## 7. Configuration

| Field | Default | Meaning |
|---|---|---|
| `tag`, `location_node` | MPFM-201, N_ARR | identification and installation point |
| `inlet_diameter_m`, `beta`, `discharge_coefficient` | 0.1016 m (4 in), 0.5, 0.995 | venturi |
| `dp_min_bar`, `dp_max_bar`, `gvf_max` | 0.02, 5.0, 0.96 | operating envelope |
| `pressure_sigma_bar`, `temperature_sigma_k`, `dp_sigma_pct_full_scale` | 0.05, 0.2, 0.05 | transmitter noise |
| `gamma_count_rate_low_cps`, `gamma_count_rate_high_cps`, `integration_time_s` | 2e5, 5e4, 10 | gamma statistics and output filter |
| `update_interval_s` | 2 | meter update period (simulated time) |
| `meter_slip_model` | chisholm | flow-computer slip model |
| `meter_pvt` | = the true fluid | meter's fluid characterisation (a mismatch gives bias) |
| `pvt_uncertainty_pct`, `cd_uncertainty_pct`, `slip_uncertainty_table` | 1.5, 0.5, table | uncertainty inputs |
| `calibration_interval_days`, `cd_drift_pct_per_year` | 180, 0 | calibration management |
| `seed` | 1 | reproducible noise |

## 8. Limitations

- **Representative only.** The model is not validated against a specific
  meter, and the attenuation coefficients and slip law are generic.
- **No sample-by-sample effects.** Flow-regime-dependent errors appear only
  through the slip model and its uncertainty term. Slug-flow
  sample-to-sample effects are not simulated, because the process model has no
  slugging.
- **Single installation.** A single meter is placed at the manifold node; the
  meter's own pressure loss is not added to the network.

## 9. Verification

**`backend/tests/test_mpfm.py`**

- slip, void-fraction and momentum-density identities;
- exact inversion by a noise-free, matched meter;
- actual-to-standard conversion through Bo, Bg, Bw and Rs;
- the WC, GOR, GVF and LVF definitions;
- a homogeneous meter under-reads gas and over-reads liquid in slipping flow;
- a salinity mismatch over-reads water cut, and calibration removes the bias;
- uncertainty behaviour (GVF, low flow, budget, coverage, reproducibility);
- faults and quality: gamma failure, frozen dP, dP offset, P/T failure;
- envelope checks: low-flow cut-off, GVF, calibration due;
- integration:
  - meter truth equals the simulated manifold flow;
  - opening the choke raises the measured oil and stays within uncertainty;
  - shut-in reaches the low-flow cut-off;
  - a water-cut change reaches the meter with the fluid transit time;
  - single-phase mode reports `NOT_MODELLED`;
- the API.

**Frontend:** `frontend/src/mpfm.test.tsx`.
**End-to-end:** the "MPFM: measured vs true, fault injection and calibration"
workflow.

## References

- ISO/TR 21354:2020 / API MPMS Chapter 20.3 — multiphase flow measurement (principles, terminology and uncertainty practice).
- NFOGM & Tekna (2005) *Handbook of Multiphase Flow Metering*, Rev. 2.
- JCGM 100:2008 (GUM) — *Evaluation of measurement data — Guide to the expression of uncertainty in measurement*.
- ISO 5167-4 — venturi tubes.
- Chisholm, D. (1972) *A theoretical basis for the Lockhart-Martinelli correlation for two-phase flow*. Int. J. Heat Mass Transfer 10.
- Hubbell, J.H. and Seltzer, S.M., NIST XCOM / X-ray mass attenuation coefficients database.
- ISO 13443 — standard reference conditions.
