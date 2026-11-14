# Roadmap

## Release 1 — Interactive subsea tree simulator (implemented)

- [x] React + TypeScript + Vite dashboard, dark industrial theme, responsive layout
- [x] Python FastAPI backend; engine independent of API
- [x] Configuration-driven series topology and SVG schematic (SCSSV, PMV, PWV, choke, tubing, flowline, transmitters)
- [x] Valve open/close with rate-limited travel; commanded vs actual position; unavailable state
- [x] Choke position control with generic nonlinear characteristic
- [x] Reservoir pressure, PI, temperature, downstream pressure, and fluid property configuration
- [x] Single-phase quasi-steady hydraulic model (linear IPR, Churchill friction, hydrostatics, restrictions)
- [x] Closed-in, trapped-section and reverse-flow handling; explicit failure/invalid reporting
- [x] Transient lumped thermal model with throttling heating
- [x] Ideal instruments with range clamping and quality status
- [x] Backend-controlled lifecycle (start/pause/resume/reset), speed 1–300×, WebSocket streaming
- [x] Selectable trend charts of engine samples; event log with engineering consequences
- [x] Training framework + Exercise 3 (choke operation) with predictions, data-driven explanations and scoring
- [x] Training rule: warning when opening against a differential
- [x] Per-user sessions for internal-server deployment
- [x] Automated tests (pytest, Vitest, Playwright); Docker single-container build

## Release 2 — Advanced engineering simulator (planned)

- Fluid: black-oil correlations behind `FluidModel` (cited sources and validity ranges); CoolProp for water/gas; marching solver for P/T-dependent properties
- Choke: manufacturer-style Cv tables, cavitation/critical-flow checks for liquids
- Configurable flowline geometry (multiple segments, profiles), insulation thermal mass
- Instrument faults: bias, drift, frozen output, noise, comms loss (PV vs measurement already separated)
- Exercises 1, 2, 4–9 (tree identification, valve operations, pressure monitoring, reservoir/downstream changes, isolation, instrumentation interpretation, fault identification)
- Improved diagnostics; optional SQLite persistence of training results

## Release 3 — Advanced training platform (planned)

- Branched network solver (annulus, crossover, swab, manifolds); configurable tree architectures
- Multiphase flow, where validated models are available; multiphase choke correlations
- Flow assurance models (hydrate curve and subcooling, wax appearance, slugging indicators) as separate documented models
- Dynamic hydraulics (compressibility, line-pack, shutdown/restart; water hammer only with the physics implemented)
- Optional Three.js 3D equipment view, complementing the schematic
- Multi-user accounts, instructor dashboard, scenario authoring, assessment history (PostgreSQL + SQLAlchemy)
- Exercise 10 (integrated production scenario)
