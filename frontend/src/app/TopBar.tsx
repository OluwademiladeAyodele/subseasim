import { Gauge, Pause, Play, RotateCcw, SlidersHorizontal, StepForward } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Button, Segmented, Select } from "@/components/ui/primitives";
import { type FlowUnit, formatSimTime, formatTimeOfDay, type PressureRef } from "@/lib/units";
import { cn } from "@/lib/utils";
import type { SimMode } from "@/types/simulation";

import { useWorkstation } from "./context";
import { ROUTE_BY_ID } from "./routes";

const DEFAULT_SPEEDS = [1, 10, 60, 300];

function StatusPill({ status }: { status: string }) {
  const s = {
    running: { c: "bg-ok/10 text-ok", dot: "bg-ok live-dot", t: "Running" },
    paused: { c: "bg-warn/12 text-warn", dot: "bg-warn", t: "Paused" },
    ready: { c: "bg-info/10 text-info", dot: "bg-info", t: "Ready" },
  }[status] ?? { c: "bg-panel-3 text-muted", dot: "bg-static", t: status };
  return (
    <span className={cn("inline-flex h-7 items-center gap-1.5 rounded-full px-2.5 text-xs font-semibold", s.c)} data-testid="sim-status">
      <span className={cn("h-1.5 w-1.5 rounded-full", s.dot)} />
      {s.t.toLowerCase()}
    </span>
  );
}

function UnitsMenu() {
  const { prefs, setPrefs } = useWorkstation();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const on = (e: PointerEvent) => !ref.current?.contains(e.target as Node) && setOpen(false);
    const key = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("pointerdown", on);
    window.addEventListener("keydown", key);
    return () => {
      window.removeEventListener("pointerdown", on);
      window.removeEventListener("keydown", key);
    };
  }, [open]);
  return (
    <div className="relative" ref={ref}>
      <Button variant="ghost" size="icon" aria-label="Display units" aria-expanded={open} title="Display units" onClick={() => setOpen(!open)}>
        <SlidersHorizontal size={16} />
      </Button>
      {open && (
        <div className="palette-in absolute right-0 top-10 z-40 w-64 rounded-xl border border-line bg-panel p-3 shadow-[var(--shadow-float)]" role="dialog" aria-label="Display units">
          <div className="t-eyebrow mb-2">Display units</div>
          <label className="mb-2 flex items-center justify-between gap-2 text-[13px]">
            <span className="text-muted">Pressure</span>
            <Select aria-label="Pressure reference" value={prefs.pressureRef} onChange={(e) => setPrefs({ ...prefs, pressureRef: e.target.value as PressureRef })}>
              <option value="bara">bara (absolute)</option>
              <option value="barg">barg (gauge)</option>
            </Select>
          </label>
          <label className="flex items-center justify-between gap-2 text-[13px]">
            <span className="text-muted">Flow rate</span>
            <Select aria-label="Flow unit" value={prefs.flowUnit} onChange={(e) => setPrefs({ ...prefs, flowUnit: e.target.value as FlowUnit })}>
              <option value="m3/d">m³/d</option>
              <option value="m3/h">m³/h</option>
              <option value="bbl/d">bbl/d</option>
            </Select>
          </label>
          <p className="mt-2 text-[11.5px] leading-snug text-dim">Display only — the engine always works in SI units.</p>
        </div>
      )}
    </div>
  );
}

export function TopBar() {
  const { state, route, actions, sim, go } = useWorkstation();
  const r = ROUTE_BY_ID[route];
  const status = state.status;
  const clock = state.clock;
  const speeds = clock?.allowed_speeds ?? DEFAULT_SPEEDS;
  const mode = state.mode ?? "steady";
  const achieved = clock?.achieved_speed;
  const lagging = status === "running" && achieved != null && achieved < 0.85 * state.time_scale;
  const trainingActive = !!sim.training;

  return (
    <header className="glass sticky top-0 z-20 flex min-h-14 flex-wrap items-center gap-x-5 gap-y-2 border-b border-line/80 px-5 py-2">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5 text-xs text-dim">
          <span>{r.group}</span>
          <span aria-hidden>/</span>
          <button type="button" onClick={() => go("scenario")} className="truncate hover:text-accent" title="Scenario & model">
            {state.scenario.name}
          </button>
        </div>
        <h1 className="t-title truncate text-fg">{r.label}</h1>
      </div>

      {/* simulation control cluster */}
      <div className="flex flex-wrap items-center gap-3">
        <StatusPill status={status} />
        <div className="leading-none" title="Elapsed simulation time — independent of wall-clock rendering">
          <div className="num text-[22px] font-semibold tracking-[-0.02em] text-fg" data-testid="sim-clock">
            T+{formatSimTime(state.time_s)}
          </div>
          {clock && (
            <div className="num mt-0.5 text-[11px] text-dim">
              {formatTimeOfDay(clock.time_of_day_s)} sim · {clock.solver_step_s}s {clock.fixed_step ? "fixed step" : "step"}
            </div>
          )}
        </div>
        <div className="flex items-center gap-1">
          {status === "ready" && (
            <Button variant="primary" size="sm" onClick={() => actions.lifecycle("start")} aria-label="Start">
              <Play size={14} fill="currentColor" /> Start
            </Button>
          )}
          {status === "running" && (
            <Button size="sm" onClick={() => actions.lifecycle("pause")} aria-label="Pause">
              <Pause size={14} fill="currentColor" /> Pause
            </Button>
          )}
          {status === "paused" && (
            <Button variant="primary" size="sm" onClick={() => actions.lifecycle("resume")} aria-label="Resume">
              <StepForward size={14} /> Resume
            </Button>
          )}
          <Button variant="ghost" size="sm" onClick={() => actions.lifecycle("reset")} aria-label="Reset" title="Reset to the scenario's initial conditions">
            <RotateCcw size={14} /> Reset
          </Button>
        </div>
        <div className="flex items-center gap-2">
          <Segmented
            label="Simulation speed"
            size="sm"
            value={state.time_scale}
            onChange={(s) => actions.speed(s)}
            options={speeds.map((s) => ({ value: s, label: `${s}×`, title: s === 1 ? "Real time" : `${s} simulated seconds per second` }))}
          />
          {status === "running" && achieved != null && (
            <span
              className={cn("num flex items-center gap-1 text-[11.5px]", lagging ? "text-warn" : "text-dim")}
              title="Speed actually achieved (simulated s per wall s). The solver step never changes with speed."
              data-testid="achieved-speed"
            >
              <Gauge size={12} /> {achieved.toFixed(achieved < 10 ? 1 : 0)}×
            </span>
          )}
        </div>
        <Segmented<SimMode>
          label="Simulation model"
          size="sm"
          value={mode}
          disabled={trainingActive}
          onChange={(m) => actions.mode(m)}
          testIdPrefix="mode"
          options={[
            { value: "dynamic", label: "Dynamic", title: "Time-dependent model: line-pack, reservoir transient, chemical transport, annulus, integrity tests" },
            { value: "steady", label: "Steady", title: "Quasi-steady model (Release 1): instant operating point, production path only" },
          ]}
        />
        <UnitsMenu />
      </div>
    </header>
  );
}
