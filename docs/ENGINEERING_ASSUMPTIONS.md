# Engineering assumptions — Release 1

This document states the conventions, equations, assumptions and limitations of the
SubseaSim Release 1 engineering model. If code and this document disagree, it is a defect.

> SubseaSim is an educational simulator. Its models are simplified, use illustrative
> data, are not validated against any real installation, and must never be used for
> operational decisions.

## 1. Units and pressure reference

| Quantity | Internal (engine, API) | Displayed |
|---|---|---|
| Pressure | Pa **absolute** | bara (default) or barg, always labelled |
| Pressure difference | Pa | bar |
| Temperature | K | °C |
| Volumetric flow | m³/s at line conditions | m³/d (default), m³/h, bbl/d |
| Mass flow | kg/s | kg/s |
| Viscosity | Pa·s | cP |
| Productivity index | (m³/s)/Pa | (m³/d)/bar |

* **Gauge pressure** is defined only for display: `barg = bara − 1.01325`, relative to
  the standard atmosphere (101 325 Pa). The engine never stores gauge values.
  (Subsea transmitters are typically absolute; "gauge" here means relative to the
  surface standard atmosphere, not to local hydrostatic pressure.)
* Scenario files use engineering units with the unit in every key name
  (`pressure_bara`, `temperature_c`, `length_m` …). The API uses SI with explicit
  names (`reservoir_pressure_pa`, `reservoir_temperature_k`, `productivity_index_si`).
* All conversions live in `backend/app/core/units.py` and `frontend/src/lib/units.ts`
  and are tested on both sides.
* Flow is reported at line conditions. For the incompressible gas-free liquid of
  Release 1 this equals stock-tank volume; it is **not** labelled Sm³/d because no
  formation volume factor is modelled.

## 2. Fluid

* Single-phase, incompressible, Newtonian liquid with **constant** density,
  viscosity and specific heat (`ConstantPropertyLiquid`).
* Represents an *illustrative* undersaturated crude. Valid only above the configured
  bubble-point pressure. If any calculated pressure falls below it, the diagnostics
  flag `BELOW_BUBBLE_POINT` (results are shown but marked untrustworthy).
* The thermal-expansion coefficient β is used **only** in the throttling-temperature
  relation; density is still held constant (a documented thermodynamic inconsistency
  of second order, acceptable for training).
* No gas, water cut, PVT (Bo, Rs, Bg), compressibility, wax, hydrate or asphaltene
  behaviour.

## 3. Topology and boundary conditions

* A single **series** flow path from a reservoir node to a downstream boundary node,
  defined entirely in the scenario configuration. Branches (annulus, crossover, swab
  cavity, manifolds) are rejected by topology validation in Release 1.
* Boundary conditions:
  * Reservoir: static pressure `P_res` at the reservoir datum and temperature `T_res`.
  * Downstream: fixed absolute pressure `P_down` at the boundary node (e.g. manifold or
    riser base) and the fluid temperature that would enter if flow reversed.
* Reservoir pressure is **not** the pressure in the tree; it drives inflow through
  the IPR.

## 4. Hydraulic equations

Each element contributes a signed pressure drop `ΔP_i(Q)` in the production direction.

| Element | Relation |
|---|---|
| Inflow (linear IPR) | `ΔP = Q / J` (drawdown `P_res − P_wf`) |
| Pipe | `ΔP = ρ g Δz + f (L/D) ρ v|v| / 2` |
| Valve / choke | `ΔP = ρ Q|Q| / (2 C²)`,  `C = C_d A_eff` |

* Δz is the elevation difference between the pipe's end nodes (straight-line TVD).
  Measured length may exceed it.
* Darcy friction factor: Churchill (1977), continuous across laminar, transitional
  and turbulent flow. The transition range 2000 < Re < 4000 is flagged as uncertain.
* Isolation valves: `C_open = A_bore / √K_open`; during stroking `C = C_open · f(x)`
  with a generic linear area characteristic.
* Choke: `C_max` from `Cv_max` via `Kv = 0.865 Cv` and
  `C = Kv/3600 · √(1000 / 2·10⁵)`; `C(x) = C_max · f(x)` with generic linear,
  quick-opening (`√x`) or modified equal-percentage (`(R^x − 1)/(R − 1)`)
  characteristics. **These are textbook idealisations, not manufacturer data.**
* The restriction relation assumes turbulent, non-cavitating, non-flashing
  incompressible flow with pressure recovery folded into C. **Critical (choked) flow,
  cavitation and flashing are not modelled.**

### Operating point

The steady flow `Q` satisfies

```
F(Q) = P_res − P_down − Σ ΔP_i(Q) = 0
```

`F` is strictly decreasing, so the root is unique. With the net static drive
`F0 = F(0) = P_res − P_down − ρ g Σ Δz`, the root is bracketed exactly by `[0, J·F0]`
(or `[J·F0, 0]` if `F0 < 0`) and found with SciPy's Brent method (relative tolerance
4ε). Residuals above `max(1 Pa, 10⁻⁸ · pressure scale)` are reported as a failure —
no value is substituted.

### Closed paths

* Any element with `C = 0` (fully closed valve or choke) gives `Q = 0` exactly.
* Nodes connected to the reservoir take static pressure from `P_res` (no drawdown);
  nodes connected to the boundary take static pressure from `P_down`.
* Nodes isolated between two closed elements are **trapped**: incompressible steady
  state cannot determine their pressure, so they keep the value at the moment of
  isolation (rigid volume, no leakage, isothermal assumed). With no history the
  value is reported as **undetermined** and transmitters show no value.
* Pressures change only because the boundary conditions and the model require it;
  nothing is changed merely because a valve icon changes state.

### Reverse flow

If `F0 < 0` the solver returns negative `Q` (downstream fluid entering the well) and
raises a `REVERSE_FLOW` warning. The same fluid and injectivity equal to productivity
are assumed — a simplification, not a representation of real cross-flow.

### Invalid operating points

If any node pressure is ≤ 0 Pa absolute (e.g. a static liquid column that cannot
reach the tree), the diagnostics raise `NEGATIVE_ABSOLUTE_PRESSURE` (error) and **every
transmitter reading is set to BAD with no value**.

## 5. Thermal model

* Pipes are divided into N well-mixed cells; per cell
  `M c_p dT/dt = ṁ c_p (T_up − T) − U π D ΔL (T − T_amb)`, integrated with
  backward Euler (unconditionally stable).
* `M` includes the fluid only — pipe-wall, insulation and tree-body heat capacity are
  neglected, so cool-down is **faster than reality**.
* `U` is an overall coefficient referred to the inner surface; ambient temperature
  varies linearly between the configured pipe-end values (geothermal profile in the
  tubing; seabed temperature for the flowline).
* Inflow enters at reservoir temperature (no reservoir Joule–Thomson effect).
* Restrictions apply isenthalpic throttling of the liquid:
  `ΔT = (1 − βT) ΔP / (ρ c_p)` — a small **temperature rise** (≈ 3 K for 70 bar with
  the base-case data). This is a property of the liquid model, not a gas JT cooling.
* Frictional heating and potential-energy change in pipes are neglected.
* Zero-volume tree nodes take the temperature of the fluid leaving the upstream
  element; at zero flow they follow the adjacent upstream pipe cell.
* Initial condition: thermal steady state of the initial configuration.

## 6. Time model

| Behaviour | Treatment |
|---|---|
| Pressure / flow | **Quasi-steady** — recomputed instantly for current positions and boundaries. No pressure waves, line-pack, water hammer. |
| Valve / choke travel | Time-dependent, constant stroke rate (`100 % / full_stroke_time`). |
| Temperature | Time-dependent (Section 5). |

Simulation time advances only while RUNNING, in sub-steps ≤ 5 s, driven by the
backend loop (`elapsed wall time × speed`). Results depend on simulation time, not on
browser rendering rate (tested).

## 7. Instruments

Ideal transmitters within their calibrated range. Outside the range the reading
saturates at the limit (`OUT_OF_RANGE_HIGH/LOW`). Undetermined or failed values give no
number. The model process value (PV) is kept separate from the displayed
measurement so faults can be added later.

## 8. Training rules

`max_opening_differential_bar` (scenario-configurable) produces a **warning event**
when an isolation valve is opened against a differential above the limit. It is a
training rule, not an interlock and not an operating procedure. It does not block the
command.

## 9. Known limitations (Release 1)

No multiphase flow, gas, compressibility, PVT, hydrates, wax, scale, slugging,
erosion, cavitation/critical choke flow, pressure transients, reservoir depletion,
branched networks, instrument faults, or manufacturer-specific valve/choke data.
