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

## Dynamic subsystem (Release 2)

`app/simulation/dynamic/` adds a time-dependent model next to the unchanged steady-state
solver. It covers the network builder, the implicit hydraulic solver, transport and thermal,
the coupling model and integrity tests. The engine selects the model per session
(`mode`). In dynamic mode the series solver still runs as the steady-state reference.
New endpoints: `POST /api/sessions/{id}/mode`, `POST /api/sessions/{id}/chemicals/{chem}`,
`POST /api/sessions/{id}/integrity/tests`, `POST /api/sessions/{id}/integrity/tests/{n}/abort`.
New frontend panels: `controls/ChemicalsPanel.tsx`, `controls/IntegrityPanel.tsx`. The schematic
supports branches, check valves, chemical bands, zoom and pan. See
[DYNAMIC_SIMULATION_MODEL.md](DYNAMIC_SIMULATION_MODEL.md).

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
| `app/storage/` | Simulation records: SQLite store and record builder (see SIMULATION_RECORDS.md) |
| `app/core/model_registry.py` | Method, version, model status and validation of every calculation module |
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
| POST | `/api/sessions/{sid}/records` | Save the current assessment as a record |
| GET / DELETE | `/api/records`, `/api/records/{id}` (`/export`) | List, read, export, delete records |
| WS | `/ws/sessions/{sid}` | `init` (full state, history, events), then `update` deltas |

Errors: 404 unknown session/scenario/valve/exercise, 409 rejected command or invalid
lifecycle transition, 422 validation failure, 503 session limit.

## Frontend layout (`frontend/src`)

The UI is a **workstation** with separate workspaces rather than one crowded dashboard:
a deep-navy sidebar (Operate · Monitor · Configure · Learn), a translucent top bar with the
simulation controls, hash-routed pages (`#/overview`, `#/valves`, … deep-linkable, with
back/forward), a non-modal **inspector** sheet that opens from the right for whatever
component is selected, and a **command palette** (Ctrl/Cmd + K) for every workspace,
valve operation, transmitter, simulation control and scenario. `Alt + 1–9` jumps between
workspaces; `Esc` closes the inspector or palette.

| Folder | Content |
|---|---|
| `app/` | Shell (layout, shortcuts), `Sidebar`, `TopBar`, `Inspector`, `CommandPalette`, `routes.ts`, `useRoute` (hash routing), `context.tsx` (live state, prefs, selection, actions) |
| `pages/` | One file per workspace: Overview, Valves, Chemicals, Integrity, Trends (lazy-loaded), Instruments, Events, Diagnostics, Conditions, Scenario & model, Training |
| `types/` | TypeScript interfaces mirroring the API |
| `services/api.ts` | REST client |
| `hooks/useSimulation.ts` | Session bootstrap, WebSocket with reconnect, state store |
| `schematic/` | Config-driven SVG schematic (zoom/pan, chemical bands, live indicators) |
| `controls/` | Component inspector content, chemicals, integrity and conditions panels |
| `instrumentation/` | Instrument and valve tables, hero metrics |
| `charts/` | Trend charts with event markers and steady-state reference |
| `training/` | Training panel |
| `dashboard/` | Event log, diagnostics panel |
| `components/ui/` | Primitives: Button, Badge, Panel, Segmented, Stat, Tabs, Slider, Input, Kbd |
| `lib/` | Units, state colours (status + schematic palette), utils |

Design system (`index.css`): light surfaces (`#f4f6f9` canvas, white cards), slate text,
deep navy structure with an electric-cyan highlight, status colours with text labels (never
colour alone), Inter for text and JetBrains Mono (tabular) for every live number, a
size-specific type scale (`t-display`, `t-title`, `t-heading`, `t-eyebrow`), press feedback on
pointer-down, and short anchored transitions (page rise, inspector slide in and out along the same
path, palette materialise). Everything respects `prefers-reduced-motion` and
`prefers-reduced-transparency`. Fonts are self-hosted (`@fontsource-variable`), with no network
font requests.

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
