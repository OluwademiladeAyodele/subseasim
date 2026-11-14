# Simulation model

How the Release 1 engine is organised and computes a state. Equations and
assumptions are in [ENGINEERING_ASSUMPTIONS.md](ENGINEERING_ASSUMPTIONS.md).

## Module map (`backend/app/simulation/`)

| Concern | Module |
|---|---|
| System topology | `topology/topology.py` — node/element chain built from config, validated |
| Component definitions | `components/elements.py` — inflow, pipe, valve, choke elements |
| Valve characteristics | `valves/characteristics.py`; actuator travel `valves/actuator.py` |
| Choke characteristics | `choke/choke.py` |
| Fluid properties | `fluid_properties/base.py` (protocol), `constant_liquid.py` |
| Reservoir inflow | `inflow/ipr.py` (linear IPR) |
| Hydraulics | `hydraulics/friction.py`, `restriction.py`, `properties.py`, `network.py` (operating point) |
| Flowline / pipe | `flowline/pipe.py` |
| Thermal | `thermodynamics/thermal.py` |
| Instruments | `instruments/instruments.py` |
| Simulation state | `state.py` (event log, history), `engine.py` |
| Numerical methods | `solver/root_finding.py` (Brent), `solver/integration.py` (sub-steps, implicit Euler) |
| Validation & diagnostics | `diagnostics/checks.py` |
| Config → runtime | `build.py` (engineering units → SI) |

## One engine step

`SimulationEngine.advance(dt)` (only while RUNNING), for each sub-step ≤ 5 s:

1. Move every actuator toward its commanded position.
2. If any position changed, re-solve the hydraulic operating point
   (`solve_hydraulics`): open path → Brent root of `F(Q)`; closed path → static /
   trapped pressures.
3. Advance the thermal cells by `dt` using the current flow and element ΔPs.

Then: compute instrument readings and diagnostics, emit outcome events for completed
operations, and store a trend sample (≥ 1 s simulation time apart).

Boundary-condition and fluid changes call `recompute()`, which re-solves hydraulics
immediately (algebraic, no time passes) and refreshes zero-volume temperatures; pipe
temperatures then evolve with time.

## Fluid-property subsystem and CoolProp evaluation

The `FluidModel` protocol (density, viscosity, cp, β, bubble point as functions of P,
T) is the extension point. The Release 1 series solver requires
`is_constant_property = True`; `FlowProperties.from_fluid` refuses other models
rather than evaluating them at an arbitrary point.

**CoolProp evaluation** (not installed in Release 1):

| Criterion | Finding |
|---|---|
| Fluid support | High-accuracy Helmholtz-energy EOS for ~120 pure and pseudo-pure fluids, including water, methane, ethane, propane, n-alkanes, CO₂, N₂, H₂S. |
| Mixtures | Supported with binary interaction parameters for a subset of pairs; accuracy and robustness reduced, especially near phase boundaries. |
| Petroleum fluids | **No** crude-oil or petroleum pseudo-component characterisation, no black-oil properties (Bo, Rs), no plus-fraction handling. It is not a petroleum PVT simulator. |
| Ranges | Each EOS has stated validity limits in T and P, generally wide for the pure fluids above. |
| Licence | MIT (permissive). |
| Integration | `pip install CoolProp` (compiled wheels); check wheel availability for the deployed Python version at integration time. |

**Conclusion:** CoolProp is suitable in later releases for water and brine-free water
properties, and for gas-phase light hydrocarbons (methane-rich gas density, viscosity,
Z-factor). It is unsuitable as the crude-oil model. Petroleum fluids need documented
black-oil correlations (for example Standing, Vasquez–Beggs, Beggs–Robinson, with
cited validity ranges) or an evaluated open-source PVT package, implemented behind
`FluidModel` together with a marching solver.

## Data provenance

All scenario data are **illustrative** (`data_classification` field, shown in the
UI). No field, vendor or company data is used.
