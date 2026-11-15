# Simulation time management

Implementation: `backend/app/sessions.py` (wall-clock loop), `backend/app/simulation/engine.py` (`advance`, `_advance_dynamic`), `backend/app/core/config.py`.

## 1. Principles

* **The backend is authoritative.** Simulation time advances only in the backend. The browser renders what the backend sends and never interpolates or extrapolates process values.
* **The solver step is fixed and independent of speed.** Speeding up runs more steps per wall-clock tick, never larger steps, so numerical accuracy and stability do not depend on the selected speed.
* **Rendering is independent of solving.** The solver runs at 1 step per simulated second (default). The backend broadcasts at most once per wall-clock tick (0.25 s). The browser renders at its own frame rate. Flow-dash animations on the schematic are cosmetic, and their speed is derived from the backend velocity.

## 2. The loop

```
every tick_period_s (0.25 s wall clock):
    elapsed = min(wall time since last tick, 4 x tick)        # stall protection
    for each RUNNING session:
        engine.advance(elapsed x time_scale)                   # simulated seconds requested
        achieved_speed = smoothed(simulated advance / elapsed)
        broadcast state delta, new events, new trend samples
```

`engine.advance(dt_total)` (dynamic mode) adds `dt_total` to a time debt and executes `floor(debt / Δt)` fixed steps. Simulated time is `n_steps × Δt` exactly. Results are therefore **bit-identical** for any partitioning of the requested time and for any speed (automated tests compare 1 × 600 s with 2400 × 0.25 s, and 1× with 600×).

In steady mode the Release 1 behaviour is unchanged (equal sub-steps of at most 5 s per call).

## 3. Controls

| Control | Behaviour |
|---|---|
| Start | `ready → running` |
| Pause | `running → paused`; simulated time and every state are frozen (commands are still accepted and act when time runs) |
| Resume | `paused → running`, continuing from the exact state |
| Reset | rebuilds the model from the scenario initial conditions, `time = 0`, clears trends |
| Speed | 1×, 10×, 60× (1 min/s), 300×, 600× (10 min/s); configurable in `Settings.allowed_time_scales` |
| Model | Dynamic / Steady switch: rebuilds the model and restarts from initial conditions |

The top bar shows elapsed simulated time `T+hh:mm:ss`, the simulated time of day (`dynamics.clock_start_s` + elapsed), the solver step, and the **achieved speed**. If the CPU cannot keep up with the requested speed, the simulation runs slower than requested (achieved speed shown in amber). It is never made coarser.

A dynamic solver failure (non-finite or singular state) pauses the session, keeps the last valid state and logs an error event.

## 4. Trend storage

Samples are recorded against **simulated time**: every `max(sample_interval_s, time_scale × tick_period_s)` simulated seconds, i.e. 1 s at 1× and 150 s at 600×. They are kept in a 7200-sample ring buffer per session. Events carry `sim_time_s` (and wall time for audit) and are drawn as markers on the trend charts.

## 5. Settings

| Setting (env `SUBSEASIM_…`) | Default | Meaning |
|---|---|---|
| `DYNAMIC_STEP_S` | 1.0 | fixed dynamic solver step [s] |
| `TICK_PERIOD_S` | 0.25 | wall-clock loop period [s] |
| `MAX_SUBSTEP_S` | 5.0 | steady-mode maximum sub-step [s] |
| `SAMPLE_INTERVAL_S` | 1.0 | minimum trend sample spacing [s sim] |
| `HISTORY_LENGTH` | 7200 | trend samples kept |

Cost: about 0.8 ms of CPU per dynamic step for the base system, so 600× uses roughly half of one core per running session.
