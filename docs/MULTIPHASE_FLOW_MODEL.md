# Multiphase flow model (three-phase black oil)

SubseaSim has two fluid models. Each scenario chooses a default with
`fluid_model`, and a session can switch on the Conditions or Multiphase page.
Switching restarts the scenario.

| Model | Use |
|---|---|
| `single_phase` | Release 1 simplified model. Constant-property liquid; results are flagged invalid below the bubble point. Unchanged. |
| `black_oil` | Three-phase model: oil, gas and water, with gas coming out of solution, multiphase pressure drop, a multiphase choke, and component transport. |

The `xt_230xp22b_multiphase` scenario uses the black-oil model and is the
default for new sessions. `xt_230xp22b` has the same fluid configured but
starts in single-phase mode.

**Classification.** All correlations are generic. They are not fitted to a
laboratory PVT report, so every output is a correlation estimate and is
labelled illustrative.

## 1. Inputs

The fluid is defined by `BlackOilConfig` in the scenario. At run time it is
changed with `PUT /api/sessions/{id}/black-oil` or the UI.

| Input | Unit | Range |
|---|---|---|
| Producing GOR | Sm³/Sm³ (15 °C, 1.01325 bar) | 0 – 2000 |
| Water cut | fraction of liquid at standard conditions | 0 – 0.98 |
| Oil gravity | °API | 10 – 70 |
| Gas specific gravity | air = 1 | 0.55 – 1.5 |
| Water salinity | wt% NaCl equivalent | 0 – 26 |
| Phase heat capacities, gas cp/cv | J/(kg K), – | configurable |
| Pressure-gradient correlation | `beggs_brill` or `no_slip` | – |

Reservoir pressure, reservoir temperature and productivity stay on the
Conditions page.

**Productivity index.** In three-phase mode the productivity index is
interpreted in reservoir volumes, at the mixture density at reservoir
conditions (section 5).

**When an input changes**

- **GOR or water cut** changes the composition of the fluid *entering* the
  well. It is transported along the path (section 5.3).
- **API, gas gravity or salinity** re-characterises the fluid everywhere at
  once.

## 2. PVT correlations

Source: `backend/app/simulation/fluid_properties/black_oil.py`. All functions
are vectorised.

**Components and phases**

- Three components, on a stock-tank basis: stock-tank oil, surface gas and
  water.
- Three phases at line conditions: oil (with dissolved gas Rs), free gas and
  water.
- Free gas per Sm³ of oil is `GOR − Rs(p, T)`. It is zero at or above the
  local bubble point.

| Property | Correlation | Data range of the original correlation |
|---|---|---|
| Rs, Pb, Bo (saturated) | Standing (1947, 1981) | Pb 130–7000 psia; T 100–258 °F; 16.5–63.8 °API; γg 0.59–0.95; Rs 20–1425 scf/STB |
| Bo (undersaturated) | Vasquez & Beggs (1980): c_o = A/p, so Bo = Bob (Pb/p)^A | 15.3–59.5 °API; Rs 9.3–2199 scf/STB; p 141–9515 psia |
| Oil viscosity | Beggs & Robinson (1975), dead and live oil; Vasquez & Beggs (1980) undersaturated | 16–58 °API; 70–295 °F |
| Gas Z factor | Dranchuk & Abou-Kassem (1975), with Sutton (1985) pseudo-criticals | 1.0 < Tpr ≤ 3.0; 0.2 ≤ Ppr < 30 |
| Gas viscosity | Lee, Gonzalez & Eakin (1966) | 100–340 °F; 100–8000 psia |
| Water Bw, ρw, μw | McCain (1990, 1991) | to 260 °F, 5000 psia, 26 wt% |
| Gas–liquid surface tension | Baker & Swerdloff (1956) for gas–oil; constant 0.060 N/m for gas–water; mixed by liquid volume | – |

**Derived quantities**

- Oil density: `ρo = (ρ_STO + Rs ρ_g,sc) / Bo`.
- Gas density: `ρg = p M / (Z R T)`.
- Gas formation volume factor: `Bg = (p_sc/p)(T/T_sc) Z`.

**Mass conservation through the flash.** The mass per Sm³ of stock-tank
liquid is the same at every pressure. This is tested to 1e-12.

**Range checks.** Every snapshot checks the operating envelope against the
table above. Extrapolation is reported on the Multiphase page and as
`CORRELATION_RANGE` diagnostics. One known extrapolation: the 4 °C seabed
temperature is below the Beggs-Robinson and Lee data ranges.

**Not modelled**

- gas solubility in water;
- oil–water emulsion viscosity (liquid viscosity is volume-weighted);
- volatile-oil and condensate behaviour;
- hydrates and wax (chemical dosing is modelled separately).

## 3. Multiphase correlations

Source: `backend/app/simulation/multiphase/correlations.py`.

### 3.1 Beggs & Brill (1973), with Payne et al. (1979) corrections

Inputs: superficial liquid and gas velocities `v_sl` and `v_sg`;
`v_m = v_sl + v_sg`; `λ_L = v_sl / v_m`; `N_Fr = v_m² / (g D)`.

1. **Flow pattern.** The pattern (segregated, transition, intermittent or
   distributed) is taken from the L1–L4 boundaries.
2. **Horizontal holdup.** `H_L(0) = a λ^b / N_Fr^c`, with `H_L(0) ≥ λ`.
3. **Inclination correction.**
   - `ψ = 1 + C [sin 1.8θ − sin³(1.8θ)/3]`.
   - `C = (1 − λ) ln(d' λ^e N_LV^f N_Fr^g)`, with `C ≥ 0`.
   - Transition holdup is interpolated between segregated and intermittent.
4. **Payne corrections.** Holdup is multiplied by 0.924 uphill and 0.685
   downhill, and uphill holdup is kept ≥ λ.
5. **Friction.**
   - `f_tp = f_ns e^S`, with `S = ln y / (−0.0523 + 3.182 ln y − 0.8725 ln²y + 0.01853 ln⁴y)` and `y = λ / H_L²`.
   - For 1 < y < 1.2, `S = ln(2.2y − 1.2)`.
   - `f_ns` is Churchill's friction factor with the pipe roughness. The
     original correlation used smooth pipe; this follows Payne.
6. **Pressure gradient.** `dp/dz = ρ_s g sinθ + f_tp ρ_ns v_m² / (2D)`.
   - The steady solver adds the acceleration term: the gradient is divided by
     `(1 − E_k)`, with `E_k = ρ_s v_m v_sg / p` capped at 0.9.

**Scope.** Beggs & Brill was derived from 1 in and 1.5 in acrylic pipes with
air and water. It is applied here to the flowline and also to the tubing,
which is labelled as an extrapolation.

**No-slip alternative.** `no_slip` sets `H_L = λ` and the multiplier to 1.
It is kept for comparison.

**Considered but not implemented: Hagedorn & Brown.** It needs digitised
charts. It can be added as another `correlation` value.

### 3.2 Sachdeva et al. (1986) choke model

**Critical pressure ratio.**

- Computed from the frozen-composition isentropic expansion: free-gas mass
  fraction x₁, polytropic exponent n, and gas cp/cv = k.
- Solved by bisection on `h(y) = y − f(y)`, which changes sign exactly once on
  (0, 1).

**Mass flux.**

- Computed at `y = max(p₂/p₁, y_c)`.
- With `y < y_c` the flow is **critical (choked)**: the rate is independent of
  downstream pressure.

**Choke area.**

- The effective area `C_dA` is the configured capacity of the element at its
  current position, from the same Cv characteristic the single-phase model
  uses.
- For a liquid-only stream (x₁ = 0) the model reduces exactly to the orifice
  equation `W = C_dA √(2 ρ ΔP)`. This is the single-phase model, so the two
  models agree on a liquid.

**Independent checks (`tests/test_multiphase.py`)**

- The liquid limit equals the orifice equation.
- The pure-gas limit equals the isentropic nozzle ratio `(2/(k+1))^(k/(k−1))`.
- Choked flow is independent of downstream pressure.

## 4. Steady solution (marching)

Source: `backend/app/simulation/multiphase/steady.py`.

**Unknown.** The production mass flow W. At steady state every element carries
the same W, so each component's mass flow is exactly conserved.

**March.** For a candidate W the path is marched from the reservoir:

| Element | Treatment |
|---|---|
| Inflow | Linear IPR in reservoir volumes above the bubble point; Vogel (1968) composite below it |
| Pipe | Heun predictor-corrector over segments of ≤ 150 m (at most 12 per pipe); temperature interpolated between nodes |
| Valve / choke | Sachdeva; a candidate above the critical flow is infeasible |

**Root finding.**

- The arrival pressure is monotone in W.
- Candidates are evaluated as a vectorised batch of 17, the bracket is narrowed
  over up to 6 batches, and the final bracket is linearly interpolated.

**Choked operating point.** When the choke is choked, the rate is the largest
feasible W. The pressures downstream of the choke are found by marching
*backwards* from the boundary.

**Closed path.** With the path closed, the steady reference falls back to
static columns at reservoir-condition density. This is approximate and
labelled.

**Uses of this solution**

- the steady (quasi-steady) simulation mode;
- the "heading to" reference in dynamic mode, recomputed when production valves
  stop moving;
- the initial guess for the dynamic state.

## 5. Dynamic coupling

Source: `backend/app/simulation/multiphase/dynamic.py`.

### 5.1 Mass-based network

**Reference flow.** The dynamic network keeps its pressure/flow structure, but
production flow is the reference flow `Q = W / ρ_ref`, where `ρ_ref` is the
mixture density at reservoir conditions. Reservoir-side flows are therefore
true reservoir volumes.

**Node mass balance.** `d(Vρ_m)/dt = ΣW` becomes:

    (V/ρ_ref)(∂ρ_m/∂P) dP/dt = ΣQ − (V/ρ_ref)(∂ρ_m/∂T) dT/dt

The capacitance `C = V ∂ρ_m/∂P / ρ_ref`, plus wall compliance, contains both
gas compressibility and gas liberation or re-solution. It is evaluated by
forward differences of the PVT model.

**Link momentum.** `(L/A) dW/dt = ΔP − ρ_s g Δz − ΔP_f`:

| Link | Gravity density | Friction |
|---|---|---|
| Pipe | slip density ρ_s (Beggs & Brill) | network pipe law with ρ = ρ_ref, μ = μ_ns, and multiplier `e^S ρ_ref/ρ_ns` |
| Valve / choke | no-slip density ρ_ns | Sachdeva flow at the current pressures, expressed as an equivalent orifice density `2(C_dA)² ΔP / Q_s²`, under-relaxed 0.5 between steps |

For a liquid, the valve/choke expression is exactly `ρ_ref²/ρ_l`.

### 5.2 Semi-implicit treatment

- Coefficients are evaluated from the state at the start of the step; P and Q
  are solved implicitly. The lag does not affect the steady state.
- Coefficients are re-evaluated only when pressures move by ≥ 0.02 bar or
  flows by ≥ 0.1 %, and at least every 30 steps.
- A forced update follows any fluid change.

Typical cost on the XT well: about 1.6 ms per 1 s step at steady operation,
and about 5 ms during transients.

### 5.3 Component transport

A second transport grid carries the mass fractions of stock-tank oil, surface
gas and water along the production path. GOR and water cut at every node come
from these fractions.

**Face flows.** Each step the face flows are rebuilt from the inlet flow, so
that every cell's change of content equals the change of its own volume's
mixture density between the old and new pressures. In other words, line pack
is distributed consistently across cells.

**Conservation.** Each component's mass is conserved exactly:
`in − out − Δinventory = 0`. This holds to round-off (about 1e-15 relative)
through valve closures, choke changes and composition changes. Tests check it.

**Chemical injection.** The chemical concentration grid uses the same
mass-tracked cell contents. In production-node mass balances, injected
chemical is counted at the reference density, which is within 3 % for
methanol.

### 5.4 Temperature

- The heat capacity per reference volume is `ρ_ref × cp_mix`, where cp_mix is
  the mass-weighted cp of the phases.
- Throttling uses the mixture properties upstream:
  `dT = (1 − β_m T) ΔP / (ρ_m cp_m)`, with β_m from the PVT model.
- With free gas present, β_m T > 1, so the choke cools the fluid (the
  Joule-Thomson effect). For a liquid it heats the fluid.

### 5.5 Instruments and reporting

- **Flow transmitters** on the production path read the **in-situ** total
  volumetric flow at line conditions, `Q ρ_ref/ρ_ns(local)`. FT-101 has a
  12 000 m³/d range in the three-phase scenario.
- **Multiphase page.** Shows:
  - standard-condition rates entering the well and arriving at the manifold;
  - per-node PVT and in-situ phase flows;
  - Beggs & Brill pattern and holdup per pipe segment;
  - component mass balances;
  - correlation validity and model limitations.
- **Reference conditions** are stated on every standard rate: 15 °C and
  1.01325 bar (ISO 13443).

## 6. Limitations

- **Quasi-steady phase behaviour and holdup.** Slugging,
  terrain-induced slugging, phase-slip transients and liquid accumulation
  during shut-in are **not simulated**. A shut-in static column uses the
  no-slip density.
- **Reservoir below the bubble point.** The dynamic radial reservoir model is
  single-phase liquid. A bottomhole pressure below the bubble point is flagged
  (`INFLOW_BELOW_BUBBLE_POINT`). Vogel is used only in the steady reference.
- **Reverse flow.** Reverse flow into the well is not supported by the steady
  multiphase march; it is reported.
- **Generic correlations.** Accuracy is typically ±10–30 % on pressure drop for
  Beggs & Brill, and ±5–15 % on Bo and Rs, against field data. Fitting to a PVT
  report and to well-test data is required before any engineering use.

## 7. Verification

**`backend/tests/test_multiphase.py`, against independent references**

- Standing-Katz Z chart (5 points, ±0.02);
- the bubble point recomputed by hand from Standing's equation;
- methane viscosity (NIST, ±5 %);
- Beggs & Brill single-phase limit against Colebrook-White Darcy-Weisbach
  (±2 %);
- Sachdeva liquid limit against the orifice equation (1e-9);
- Sachdeva pure-gas limit against the isentropic critical ratio (1e-6);
- choked-flow independence from downstream pressure.

**Same file, conservation and behaviour**

- component mass conservation through the flash;
- steady phase mass balances, exact;
- standard-rate consistency: gas = GOR × oil, and water cut;
- monotone pressures along the path;
- the response to choke opening and to reservoir pressure;
- convergence of both correlations;
- the dynamic initial state is steady and within 3 % / 3 bar of the march;
- dynamic component balances within 1e-6 through choke, PWV and composition
  transients;
- a composition change travels with the fluid;
- flow transmitters read in-situ volume;
- the single-phase / three-phase switch;
- step cost;
- the API endpoints.

**Frontend:** `frontend/src/multiphase.test.tsx`.
**End-to-end:** the "three-phase production" workflow.

## References

- Beggs, H.D. and Brill, J.P. (1973) *A study of two-phase flow in inclined pipes*. JPT 25(5), 607–617.
- Payne, G.A. et al. (1979) *Evaluation of inclined-pipe two-phase liquid holdup and pressure-loss correlations using experimental data*. JPT 31(9).
- Sachdeva, R., Schmidt, Z., Brill, J.P. and Blais, R.M. (1986) *Two-phase flow through chokes*. SPE 15657.
- Standing, M.B. (1947) API Drilling and Production Practice; Standing (1981) *Volumetric and Phase Behavior of Oil Field Hydrocarbon Systems*, SPE.
- Vasquez, M. and Beggs, H.D. (1980) *Correlations for fluid physical property prediction*. JPT 32(6).
- Beggs, H.D. and Robinson, J.R. (1975) *Estimating the viscosity of crude oil systems*. JPT 27(9).
- Dranchuk, P.M. and Abou-Kassem, J.H. (1975) *Calculation of Z factors for natural gases using equations of state*. JCPT 14(3).
- Sutton, R.P. (1985) *Compressibility factors for high-molecular-weight reservoir gases*. SPE 14265.
- Lee, A.L., Gonzalez, M.H. and Eakin, B.E. (1966) *The viscosity of natural gases*. JPT 18(8).
- McCain, W.D. (1990) *The Properties of Petroleum Fluids*, 2nd ed.; McCain (1991) SPE Reservoir Engineering 6(2).
- Baker, O. and Swerdloff, W. (1956) *Finding surface tension of hydrocarbon liquids*. Oil & Gas J.
- Vogel, J.V. (1968) *Inflow performance relationships for solution-gas drive wells*. JPT 20(1).
- Brill, J.P. and Mukherjee, H. (1999) *Multiphase Flow in Wells*. SPE Monograph 17.
- ISO 13443 (1996) *Natural gas — Standard reference conditions*.
