# Validation

Three things are distinguished:

1. **Software correctness**: the code does what it is specified to do (API, lifecycle,
   input validation, UI behaviour).
2. **Numerical verification**: the equations are solved correctly (comparison with
   closed-form solutions, convergence, stability).
3. **Engineering-model validation**: the model represents a real system. **Release 1 has
   none.** Passing tests does not show that SubseaSim reproduces any real subsea
   installation. The base-case numbers were only sanity-checked by hand calculation
   for plausibility.

## How to run

```bash
cd backend && .venv/Scripts/python -m pytest      # (Linux/macOS: .venv/bin/python)
cd frontend && npm test                           # Vitest + Testing Library
cd frontend && npm run e2e                        # Playwright (starts servers if needed)
```

## Results (Release 1, 2026-11-07)

| Suite | Tests | Result |
|---|---|---|
| Backend (pytest) | 99 | all passed |
| Frontend unit/component (Vitest) | 21 | all passed |
| End-to-end (Playwright, Chromium) | 6 | all passed |

## Numerical verification (backend `tests/test_hydraulics_reference.py`, `test_thermal.py`, `test_friction_and_restrictions.py`)

| Reference | Check |
|---|---|
| IPR + single restriction | Solver Q equals the closed-form quadratic root (rel. 1e-10) |
| IPR + laminar pipe | Equals the linear Hagen–Poiseuille solution (rel. 2e-3, Re < 1000 asserted) |
| Hagen–Poiseuille | Laminar Darcy–Weisbach = `128 μ L Q / (π D⁴)` |
| Churchill friction factor | = 64/Re in the laminar limit; within 3 % of the Colebrook–White iteration for Re 1e4–1e6, ε/D 0–1e-3; continuous through transition |
| Static liquid column | Closed outlet gives `P_res − ρ g H` |
| Pressure budget | Σ element ΔP = P_res − P_down (±1 Pa); node pressures consistent with element ΔPs at the same Q |
| Convergence sweep | 300 randomised cases (P, J, geometry, fluid, choke): all converge with residual ≤ tolerance and correct flow direction |
| Nearly closed restriction | Positions 1e-12 … 0.01 % converge to the restriction-only limit (regression for a defect found during development) |
| Kv/Cv/K definitions | Reproduce their defining equations |
| Tanks-in-series thermal | Exact discrete solution `(adv/(adv+loss))^N`; converges to the plug-flow exponential (N = 400, ±0.05 K) |
| Lumped cool-down | Decays with τ = ρ c_p D / (4U) (±0.2 %) |
| Implicit Euler | Stable for dt = 1e12 s; dt = 0 leaves state unchanged |
| Time partitioning | 1 × 600 s vs 600 × 1 s give identical hydraulics and temperatures within 0.05 K |

## Engineering-behaviour tests (`test_engineering_behaviour.py`)

| # | Requirement | Test |
|---|---|---|
| 1 | Zero flow | Closing any of SCSSV, PMV, PWV, choke gives Q = 0 and FT reads 0 |
| 2 | Closed-valve behaviour | Reservoir side = static from P_res, boundary side = static from P_down; ΔP across closed valve = net static drive |
| 3 | No fabricated pressure change | Closing a valve downstream of an already-closed valve changes no pressure |
| 4 | Trapped volume | Pressure retained; undetermined without history |
| 5 | Choke response | Flow strictly increases with opening; non-proportional; choke ΔP falls as it opens |
| 6 | Boundary response | Flow rises with P_res and J, falls with P_down; reversible |
| 7 | Fluid response | Higher viscosity or density lowers flow |
| 8 | Invalid points | Reverse flow warned; below bubble point warned; negative absolute pressure makes readings BAD |
| 9 | Instrument consistency | PT = node pressure, PDT = PT-102 − PT-103 = choke ΔP, FT = Q, TT-001 = T_res |
| 10 | Throttling heating | TT-103 − TT-102 equals `(1 − βT) ΔP / (ρ c_p)` |
| 11 | No temperature step on valve closure | Temperature unchanged at the instant of closure |

## Software correctness

* API: session creation and isolation, commands, 404/409/422 handling, WebSocket
  init/update, training endpoints (`test_api_and_training.py`).
* Engine: lifecycle transitions, paused time freeze, outcome events, training-rule
  warning, history samples equal engine readings (`test_engine_lifecycle.py`).
* Topology/scenario validation, actuator travel, command rejection, range clamping
  (`test_valves_instruments_topology.py`).
* Training: complete Exercise 3 run; correct answers resolved from simulation data
  (`test_api_and_training.py`).
* Frontend: unit conversions, schematic rendering/selection, valve-specific controls,
  input validation, BAD-value display, prediction workflow (`src/**/*.test.ts(x)`, run
  against real engine snapshots exported as fixtures).
* E2E: simulated marking, choke changes flow, PWV closure stops flow, invalid input
  error, reservoir change, training start (`frontend/e2e`).

## Not verified

* Docker image build: Docker Desktop was not running in the development environment.
  The production serving path (FastAPI serving the built frontend and the WebSocket
  on one port) was verified without Docker. Run `docker compose up --build` to confirm.
* Any comparison with field or vendor data (engineering-model validation).
