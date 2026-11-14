import { Pause, Play, RotateCcw, StepForward } from "lucide-react";

import { Badge, Button, Select } from "@/components/ui/primitives";
import type { Connection } from "@/hooks/useSimulation";
import { type DisplayPrefs, type FlowUnit, formatSimTime, type PressureRef } from "@/lib/units";
import type { ScenarioInfo, SimulationState } from "@/types/simulation";

interface Props {
  state: SimulationState | null;
  scenarios: ScenarioInfo[];
  connection: Connection;
  prefs: DisplayPrefs;
  setPrefs: (p: DisplayPrefs) => void;
  onLifecycle: (a: "start" | "pause" | "resume" | "reset") => void;
  onSpeed: (s: number) => void;
  onScenario: (id: string) => void;
  trainingActive: boolean;
}

const SPEEDS = [1, 10, 60, 300];

export function TopBar({ state, scenarios, connection, prefs, setPrefs, onLifecycle, onSpeed, onScenario, trainingActive }: Props) {
  const status = state?.status ?? "ready";
  const statusTone = status === "running" ? "ok" : status === "paused" ? "warn" : "info";
  const conTone = connection === "live" ? "ok" : connection === "offline" ? "bad" : "warn";
  return (
    <header className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-line bg-panel px-3 py-1.5">
      <div className="flex items-center gap-2">
        <svg viewBox="0 0 32 32" className="h-6 w-6" aria-hidden>
          <rect width="32" height="32" rx="5" fill="#0b1520" stroke="#223142" />
          <path d="M16 5v22M9 11h14M11 17h10" stroke="#38bdf8" strokeWidth="2.5" strokeLinecap="round" />
        </svg>
        <div className="leading-none">
          <div className="text-[15px] font-bold tracking-wide">
            Subsea<span className="text-accent">Sim</span>
          </div>
          <div className="text-[9px] uppercase tracking-[0.18em] text-dim">Production training simulator</div>
        </div>
      </div>

      <Badge tone="warn" title="All values are produced by a simplified engineering model. Not connected to any real equipment." data-testid="simulated-badge">
        Simulated · Training only
      </Badge>

      <label className="flex items-center gap-1.5">
        <span className="text-[10px] font-bold uppercase tracking-[0.1em] text-dim">Scenario</span>
        <Select
          aria-label="Scenario"
          value={state?.scenario.id ?? ""}
          disabled={trainingActive}
          onChange={(e) => onScenario(e.target.value)}
          className="max-w-[300px]"
          title={trainingActive ? "Close the training exercise to change scenario" : state?.scenario.description}
        >
          {scenarios.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </Select>
      </label>

      <div className="flex items-center gap-2">
        <Badge tone={statusTone} data-testid="sim-status">{status}</Badge>
        <div className="num text-[17px] text-fg" data-testid="sim-clock" title="Simulation time (independent of wall-clock rendering)">
          T+{formatSimTime(state?.time_s ?? 0)}
        </div>
      </div>

      <div className="flex items-center gap-1">
        {status === "ready" && (
          <Button variant="ok" size="sm" onClick={() => onLifecycle("start")} aria-label="Start">
            <Play size={13} /> Start
          </Button>
        )}
        {status === "running" && (
          <Button size="sm" onClick={() => onLifecycle("pause")} aria-label="Pause">
            <Pause size={13} /> Pause
          </Button>
        )}
        {status === "paused" && (
          <Button variant="ok" size="sm" onClick={() => onLifecycle("resume")} aria-label="Resume">
            <StepForward size={13} /> Resume
          </Button>
        )}
        <Button variant="ghost" size="sm" onClick={() => onLifecycle("reset")} aria-label="Reset">
          <RotateCcw size={13} /> Reset
        </Button>
      </div>

      <label className="flex items-center gap-1.5">
        <span className="text-[10px] font-bold uppercase tracking-[0.1em] text-dim">Speed</span>
        <Select aria-label="Simulation speed" value={state?.time_scale ?? 1} onChange={(e) => onSpeed(Number(e.target.value))}>
          {SPEEDS.map((s) => (
            <option key={s} value={s}>
              {s}×
            </option>
          ))}
        </Select>
      </label>

      <div className="ml-auto flex items-center gap-3">
        <label className="flex items-center gap-1.5">
          <span className="text-[10px] font-bold uppercase tracking-[0.1em] text-dim">Pressure</span>
          <Select aria-label="Pressure reference" value={prefs.pressureRef} onChange={(e) => setPrefs({ ...prefs, pressureRef: e.target.value as PressureRef })}>
            <option value="bara">bara (absolute)</option>
            <option value="barg">barg (gauge)</option>
          </Select>
        </label>
        <label className="flex items-center gap-1.5">
          <span className="text-[10px] font-bold uppercase tracking-[0.1em] text-dim">Flow</span>
          <Select aria-label="Flow unit" value={prefs.flowUnit} onChange={(e) => setPrefs({ ...prefs, flowUnit: e.target.value as FlowUnit })}>
            <option value="m3/d">m³/d</option>
            <option value="m3/h">m³/h</option>
            <option value="bbl/d">bbl/d</option>
          </Select>
        </label>
        <Badge tone={conTone} data-testid="connection">{connection}</Badge>
      </div>
    </header>
  );
}
