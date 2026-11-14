# Architecture

```
Browser (React + TypeScript)                       Server (Python, FastAPI)
┌─────────────────────────────────┐   REST /api    ┌───────────────────────────────┐
│ Dashboard                       │ ─────────────▶ │ api/routes.py  (validation)   │
│  ├ TopBar (lifecycle, speed)    │                │        │                      │
│  ├ TreeSchematic (SVG, config-  │   WS /ws/...   │ sessions.py  SessionManager   │
│  │  driven)                     │ ◀───────────── │  ├ one SimulationEngine per   │
│  ├ Component / Conditions /     │  init + deltas │  │  browser session          │
│  │  Training panels             │                │  ├ asyncio loop (0.25 s tick) │
│  ├ Trends (Recharts)            │                │  └ TrainingSession            │
│  └ Instruments / Valves /       │                │ simulation/  (engine, physics)│
│    Events / Diagnostics         │                │ scenarios/   (JSON configs)   │
└─────────────────────────────────┘                │ training/    (exercises)      │
                                                   └───────────────────────────────┘
```

## Principles

* **The backend is authoritative.** The browser displays only values received from the
  engine and computes nothing physical. Unit conversion for display is its only
  arithmetic.
* **The engine is independent of the API.** `app/simulation` has no FastAPI imports and
  is fully testable on its own. The API layer validates input (Pydantic) and delegates.
* **Configuration-driven.** Topology, components, instruments and schematic layout
  come from scenario JSON. The schematic draws whatever the topology contains.
* **Simulation time is separate from rendering.** One asyncio task advances every
  RUNNING session by `elapsed wall time × speed`. The engine integrates in fixed
  sub-steps, and the browser only renders pushed state.
* **Per-session isolation.** Each browser keeps a session id in `localStorage`. On an
  internal server several interns never share a simulation. Idle sessions expire
  (default 4 h) and the session count is capped (default 50).

## Backend layout

| Path | Responsibility |
|---|---|
| `app/main.py` | FastAPI app, lifespan (starts the sim loop), CORS, serves the built frontend in production |
| `app/api/` | Request schemas (`schemas.py`), REST + WebSocket routes (`routes.py`) |
| `app/core/` | Unit conversions (`units.py`), application settings (`config.py`, env `SUBSEASIM_*`) |
| `app/models/scenario.py` | Pydantic schema of scenario files |
| `app/scenarios/` | Loader (inheritance via `extends`, `element_overrides`) and JSON data |
| `app/simulation/` | Engineering engine (see SIMULATION_MODEL.md) |
| `app/training/` | Exercise framework, exercise definitions, registry |
| `app/sessions.py` | Session manager, simulation loop, WebSocket broadcast |

### API summary

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Liveness |
| GET | `/api/scenarios`, `/api/scenarios/{id}` | Scenario catalogue |
| GET | `/api/training/exercises` | Exercise catalogue |
| POST | `/api/sessions` | Create session `{scenario_id}` |
| GET | `/api/sessions/{sid}` (`/history`, `/events`) | Snapshot, trend history, events |
| POST | `/api/sessions/{sid}/lifecycle` | `{action: start\|pause\|resume\|reset}` |
| POST | `/api/sessions/{sid}/speed` | `{time_scale: 1\|10\|60\|300}` |
| POST | `/api/sessions/{sid}/scenario` | Load scenario |
| POST | `/api/sessions/{sid}/valves/{tag}` | `{command: open\|close\|set_position, position_pct?}` |
| PUT | `/api/sessions/{sid}/boundary` | SI boundary conditions |
| PUT | `/api/sessions/{sid}/fluid` | SI fluid properties |
| POST | `/api/sessions/{sid}/training/start\|answer\|advance\|stop` | Training |
| WS | `/ws/sessions/{sid}` | `init` (full state, history, events), then `update` deltas |

Errors: 404 unknown session/scenario/valve/exercise, 409 rejected command or invalid
lifecycle transition, 422 validation failure, 503 session limit.

## Frontend layout (`frontend/src`)

| Folder | Content |
|---|---|
| `types/` | TypeScript interfaces mirroring the API |
| `services/api.ts` | REST client |
| `hooks/useSimulation.ts` | Session bootstrap, WebSocket with reconnect, state store |
| `schematic/` | Config-driven SVG tree (`TreeSchematic.tsx`) |
| `controls/` | Component control panel, conditions panel |
| `instrumentation/` | Instrument and valve tables, key-measurement strip |
| `charts/` | Trend charts |
| `training/` | Training panel |
| `dashboard/` | Layout, top bar, event log, diagnostics |
| `components/ui/` | shadcn/ui-style primitives (Radix Tabs/Slider, CVA) |
| `lib/` | Units, state colours, utils |

## Dependencies (and why)

Backend: FastAPI, Uvicorn, Pydantic, NumPy, SciPy (Brent root finder). Dev: pytest, httpx.
Frontend: React 18, Vite, TypeScript, Tailwind 4, Recharts, Radix Tabs/Slider +
class-variance-authority + clsx + tailwind-merge (the shadcn/ui component pattern),
lucide-react (icons). Dev: Vitest, Testing Library, jsdom, Playwright.
Not used yet: Three.js (Release 3), SQLite/SQLAlchemy (no persistence needed in
Release 1, because scenarios are versioned JSON files), CoolProp (see SIMULATION_MODEL.md).

## Safety isolation

The code base contains no industrial protocol client (OPC UA, Modbus, DNP3, vendor
SDKs) and no outbound network calls. The only network endpoints are the HTTP and
WebSocket API it serves itself.
