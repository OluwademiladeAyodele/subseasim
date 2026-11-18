# SubseaSim

A browser-based **training simulator** for subsea production operations. Interns can
operate a virtual subsea Christmas tree (SCSSV, PMV, PWV, production choke), change
reservoir and downstream conditions, and watch pressure, temperature and flow respond.
All values come from a documented engineering model.

> **Educational use only.** Every value is simulated from illustrative data with
> simplified models. SubseaSim is not safety-certified, must not be used for
> operational decisions, and has no interface to real subsea, SCADA, DCS or control
> systems.

## Features (Release 2: dynamic simulation)

* **Dynamic model** (default for new sessions, scenario `subsea_dynamic_base`). Pressure,
  temperature, flow and chemical concentration evolve over simulated time from mass,
  momentum and energy balances: line-pack, wellbore storage, radial reservoir transient,
  thermal expansion of trapped fluid. The quasi-steady Release 1 model remains selectable
  (Dynamic / Steady switch).
* A-annulus with AMV, AWV, crossover and service line. Four chemical-injection circuits
  (methanol, corrosion inhibitor, biocide, wax inhibitor) injecting into the production
  path, with transport, mixing and mass balance.
* Valve dead time, separate open/close stroke times, seat leakage. Valve end of travel and
  process settling are reported separately.
* Integrity testing: stroke, pressure-hold and inflow tests with isolation verification.
* Fixed-step, deterministic clock (1×–600×). Trends against simulated time with event
  markers and steady-state reference lines. Schematic zoom and pan with chemical-front bands.
* Training scenarios A–F (`dyn_*`). See [docs/DYNAMIC_SIMULATION_MODEL.md](docs/DYNAMIC_SIMULATION_MODEL.md).

## Features (Release 1)

* Interactive SVG tree schematic generated from scenario configuration, with
  open/closed/throttling/moving/unavailable valves and flowing/static/trapped flow paths
* Valve open/close with actuator travel; choke position control (nonlinear characteristic)
* Reservoir pressure, productivity index, temperature, downstream pressure and fluid
  properties are all configurable
* Quasi-steady single-phase hydraulic solver with linear IPR, friction, hydrostatics and
  restrictions; closed-in, trapped and reverse-flow handling; failures are reported,
  never masked
* Transient thermal model
* Instrument table (PT/TT/FT/PDT) with quality status; bara/barg and m³/d / m³/h / bbl/d display
* Start / pause / resume / reset, 1–300× speed, live WebSocket updates
* Trend charts of engine samples, event history with engineering consequences, diagnostics
* Guided **Exercise 3 — Choke operation**, with predictions, explanations generated
  from the simulation data, assessment questions and a performance summary
* One simulation per browser session, so many interns can share one internal server

## Quick start: Docker (internal server)

```bash
docker compose up --build
# open http://<server>:8000
```

One container serves the API, the WebSocket and the built frontend on port 8000.

## Hosting on Railway

The repository deploys to [Railway](https://railway.com) as-is. `railway.json` selects the
Dockerfile build, sets the health check (`/api/health`) and pins **one replica**.

1. Railway dashboard → **New Project** → **Deploy from GitHub repo** → choose this repository
   (branch `main`). Railway detects `railway.json` and builds the Dockerfile.
2. When the first deploy is healthy: service → **Settings** → **Networking** →
   **Generate Domain**. Open the `https://….up.railway.app` URL.
3. Optional variables (service → **Variables**): `SUBSEASIM_MAX_SESSIONS` (default 50),
   `SUBSEASIM_ORPHAN_PAUSE_S` (default 30), `SUBSEASIM_DYNAMIC_STEP_S` (default 1.0).
   `PORT` is set by Railway automatically. Do not set `SUBSEASIM_FRONTEND_DIST`.

Every push to `main` redeploys. Things to know:

* **Keep one replica.** Simulation sessions live in the server's memory, so a second
  replica would split users between two servers.
* **Redeploys reset running simulations.** Open browsers recover automatically and start a
  fresh session, with a notice.
* **Simulation records** are stored in SQLite at `/app/data/records.sqlite`. Add a Railway
  **volume mounted at `/app/data`** to keep them across redeploys; without it they are lost.
  See [docs/SIMULATION_RECORDS.md](docs/SIMULATION_RECORDS.md).
* **CPU:** one session at 600× uses about half a CPU core. Size the plan for the number of
  trainees who run at high speed at the same time.

## Local development

Prerequisites: Python 3.11–3.13, Node 20.19+ / 22.12+.

```bash
# backend
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt      # Linux/macOS: .venv/bin/python
.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000

# frontend (second terminal)
cd frontend
npm install
npm run dev            # http://localhost:5173 (proxies /api and /ws to :8000)
```

On Windows, if the default `python` is newer than 3.13, create the virtual environment
with `py -3.13 -m venv .venv` (NumPy/SciPy wheels may not yet exist for brand-new
Python versions).

## Tests

```bash
cd backend && .venv/Scripts/python -m pytest       # 99 tests: engineering, numerics, API, training
cd frontend && npm test                             # 21 component/unit tests
cd frontend && npx playwright install chromium && npm run e2e   # 6 end-to-end workflows
```

## Using the simulator

1. Press **Start**. Simulation time runs. Choose a speed (thermal effects take hours, so try 60×).
2. Click a valve or the choke on the schematic. The **Component** panel shows its
   position, its commanded position and the operations it supports.
3. Use **Conditions** to change reservoir or downstream pressure or fluid properties. The
   operating point is recalculated immediately.
4. Watch **Trends**, **Instruments**, **Event history** and **Diagnostics**.
5. **Training → Start exercise** runs Exercise 3.

## Configuration

Environment variables (all optional): `SUBSEASIM_TICK_PERIOD_S`, `SUBSEASIM_MAX_SUBSTEP_S`,
`SUBSEASIM_SAMPLE_INTERVAL_S`, `SUBSEASIM_HISTORY_LENGTH`, `SUBSEASIM_MAX_SESSIONS`,
`SUBSEASIM_SESSION_IDLE_TIMEOUT_S`, `SUBSEASIM_CORS_ORIGINS`, `SUBSEASIM_FRONTEND_DIST`.
Engineering parameters live only in scenario files.

## Documentation

* [Dynamic simulation model](docs/DYNAMIC_SIMULATION_MODEL.md): Release 2 overview, audit, verification
* [Pipeline transient model](docs/PIPELINE_TRANSIENT_MODEL.md) · [Chemical transport](docs/CHEMICAL_TRANSPORT_MODEL.md) · [Instrument response](docs/INSTRUMENT_RESPONSE_MODEL.md) · [Simulation time](docs/SIMULATION_TIME_MANAGEMENT.md)
* [Engineering validation](docs/ENGINEERING_VALIDATION.md) · [Choke erosion](docs/CHOKE_EROSION_MODEL.md) · [Choke maintenance](docs/CHOKE_MAINTENANCE_MODEL.md) · [Choke cavitation](docs/CHOKE_CAVITATION_MODEL.md)
* [Simulation records](docs/SIMULATION_RECORDS.md): saved assessments, provenance, model versions
* [Background jobs](docs/BACKGROUND_JOBS.md): long calculations without freezing the server
* [Scenario comparison and reports](docs/SCENARIO_COMPARISON_AND_REPORTS.md): compare operating options, printable engineering reports
* [Architecture](docs/ARCHITECTURE.md)
* [Engineering assumptions](docs/ENGINEERING_ASSUMPTIONS.md): units, equations, limitations
* [Simulation model](docs/SIMULATION_MODEL.md): modules, step sequence, CoolProp evaluation
* [Validation](docs/VALIDATION.md): test methodology and results
* [Scenarios](docs/SCENARIOS.md): data and file format
* [Roadmap](docs/ROADMAP.md)
