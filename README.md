# SubseaSim

A browser-based **training simulator** for subsea production operations. Interns can
operate a virtual subsea Christmas tree (SCSSV, PMV, PWV, production choke), change
reservoir and downstream conditions, and watch pressure, temperature and flow respond.
All values come from a documented engineering model.

> **Educational use only.** Every value is simulated from illustrative data with
> simplified models. SubseaSim is not safety-certified, must not be used for
> operational decisions, and has no interface to real subsea, SCADA, DCS or control
> systems.

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

* [Architecture](docs/ARCHITECTURE.md)
* [Engineering assumptions](docs/ENGINEERING_ASSUMPTIONS.md): units, equations, limitations
* [Simulation model](docs/SIMULATION_MODEL.md): modules, step sequence, CoolProp evaluation
* [Validation](docs/VALIDATION.md): test methodology and results
* [Scenarios](docs/SCENARIOS.md): data and file format
* [Roadmap](docs/ROADMAP.md)
