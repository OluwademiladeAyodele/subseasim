/**
 * Workstation context: one place for the live simulation, display
 * preferences, the current selection (inspector) and every backend action,
 * so pages stay small and never drill props.
 */
import { createContext, useContext, useEffect, useMemo, useRef, useState } from "react";

import type { Simulation } from "@/hooks/useSimulation";
import type { DisplayPrefs } from "@/lib/units";
import type { Selection } from "@/schematic/TreeSchematic";
import { api, type IntegrityTestRequest } from "@/services/api";
import type { ExerciseSummary, Layout, SandChokeInputs, ScenarioInfo, SimMode, SimulationState, ValveCommand } from "@/types/simulation";

import type { RouteId } from "./routes";

const PREFS_KEY = "subseasim.prefs";

function loadPrefs(): DisplayPrefs {
  try {
    const p = JSON.parse(localStorage.getItem(PREFS_KEY) ?? "null");
    if (p && (p.pressureRef === "bara" || p.pressureRef === "barg")) return p;
  } catch {
    /* storage unavailable */
  }
  return { pressureRef: "bara", flowUnit: "m3/d" };
}

export interface Actions {
  lifecycle: (a: "start" | "pause" | "resume" | "reset") => Promise<boolean>;
  speed: (s: number) => Promise<boolean>;
  mode: (m: SimMode) => Promise<boolean>;
  scenario: (id: string) => Promise<boolean>;
  valve: (tag: string, c: ValveCommand, pos?: number) => Promise<boolean>;
  pump: (chem: string, body: { running?: boolean; discharge_pressure_pa?: number }) => Promise<boolean>;
  selector: (tag: string, command: "open" | "close") => Promise<boolean>;
  blackOil: (body: Record<string, number | string>) => Promise<boolean>;
  fluidModel: (model: "single_phase" | "black_oil") => Promise<boolean>;
  mpfmFaults: (body: Record<string, number | boolean>) => Promise<boolean>;
  mpfmCalibrate: () => Promise<boolean>;
  sandInputs: (body: SandChokeInputs) => Promise<boolean>;
  sandExample: () => Promise<boolean>;
  sandFastForward: (days: number) => Promise<boolean>;
  supply: (id: string, available: boolean) => Promise<boolean>;
  integrityStart: (req: IntegrityTestRequest) => Promise<boolean>;
  integrityAbort: (id: number) => Promise<boolean>;
  boundary: (b: Record<string, number>) => Promise<boolean>;
  fluid: (f: Record<string, number>) => Promise<boolean>;
  trainingStart: (id: string) => Promise<boolean>;
  trainingAnswer: (step: string, choice: string) => Promise<boolean>;
  trainingAdvance: () => Promise<boolean>;
  trainingStop: () => Promise<boolean>;
}

export interface Workstation {
  sim: Simulation;
  state: SimulationState;
  layout: Layout;
  prefs: DisplayPrefs;
  setPrefs: (p: DisplayPrefs) => void;
  selection: Selection;
  select: (s: Selection) => void;
  /** Select a component by tag (valve, choke, check valve or instrument). */
  selectTag: (tag: string) => void;
  route: RouteId;
  go: (r: RouteId) => void;
  actions: Actions;
  scenarios: ScenarioInfo[];
  exercises: ExerciseSummary[];
}

const Ctx = createContext<Workstation | null>(null);

export function useWorkstation(): Workstation {
  const w = useContext(Ctx);
  if (!w) throw new Error("useWorkstation outside provider");
  return w;
}

export function WorkstationProvider({
  sim,
  route,
  go,
  children,
}: {
  sim: Simulation;
  route: RouteId;
  go: (r: RouteId) => void;
  children: React.ReactNode;
}) {
  const [prefs, setPrefsState] = useState<DisplayPrefs>(loadPrefs);
  const [selection, setSelection] = useState<Selection>(null);
  const [scenarios, setScenarios] = useState<ScenarioInfo[]>([]);
  const [exercises, setExercises] = useState<ExerciseSummary[]>([]);
  const { run, state, layout } = sim;
  const statusRef = useRef(state?.status);
  statusRef.current = state?.status;

  useEffect(() => {
    api.scenarios().then(setScenarios).catch(() => undefined);
    api.exercises().then(setExercises).catch(() => undefined);
  }, []);

  // a different scenario invalidates the selection
  useEffect(() => setSelection(null), [state?.scenario.id]);

  const actions: Actions = useMemo(
    () => ({
      lifecycle: (a) => run((sid) => api.lifecycle(sid, a)),
      speed: (s) => run((sid) => api.speed(sid, s)),
      mode: (m) => run((sid) => api.mode(sid, m)),
      scenario: (id) => run((sid) => api.loadScenario(sid, id)),
      valve: async (tag, c, p) => {
        const ok = await run((sid) => api.valve(sid, tag, c, p));
        const st = statusRef.current;
        if (ok && st !== "running") {
          sim.notify(
            `${tag} command accepted. The simulation is ${st === "ready" ? "not started" : "paused"}, so the valve will move when you ${
              st === "ready" ? "press Start" : "press Resume"
            } (valves travel in simulated time).`,
          );
        }
        return ok;
      },
      pump: (chem, body) => run((sid) => api.pump(sid, chem, body)),
      selector: (tag, c) => run((sid) => api.selector(sid, tag, c)),
      blackOil: (body) => run((sid) => api.blackOil(sid, body)),
      fluidModel: (m) => run((sid) => api.fluidModel(sid, m)),
      mpfmFaults: (b) => run((sid) => api.mpfmFaults(sid, b)),
      mpfmCalibrate: () => run((sid) => api.mpfmCalibrate(sid)),
      sandInputs: (b) => run((sid) => api.sandInputs(sid, b)),
      sandExample: () => run((sid) => api.sandExample(sid)),
      sandFastForward: (d) => run((sid) => api.sandFastForward(sid, d)),
      supply: (id, a) => run((sid) => api.supply(sid, id, a)),
      integrityStart: (req) => run((sid) => api.integrityStart(sid, req)),
      integrityAbort: (id) => run((sid) => api.integrityAbort(sid, id)),
      boundary: (b) => run((sid) => api.boundary(sid, b)),
      fluid: (f) => run((sid) => api.fluid(sid, f)),
      trainingStart: (id) => run((sid) => api.trainingStart(sid, id)),
      trainingAnswer: (step, choice) => run((sid) => api.trainingAnswer(sid, step, choice)),
      trainingAdvance: () => run((sid) => api.trainingAdvance(sid)),
      trainingStop: () => run((sid) => api.trainingStop(sid)),
    }),
    [run, sim],
  );

  if (!state || !layout) return null;

  const setPrefs = (p: DisplayPrefs) => {
    setPrefsState(p);
    try {
      localStorage.setItem(PREFS_KEY, JSON.stringify(p));
    } catch {
      /* ignore */
    }
  };
  const selectTag = (shown: string) => {
    // accept the engineering tag or its display alias
    const tag = Object.entries(state.tag_aliases ?? {}).find(([, a]) => a.tag === shown)?.[0] ?? shown;
    if (state.control_hydraulics?.selector_valves.some((s) => s.tag === tag)) return setSelection({ type: "selector", tag });
    const el = state.elements.find((e) => (e as { tag?: string }).tag === tag);
    setSelection(el ? { type: "element", id: el.id } : state.instruments.some((i) => i.tag === tag) ? { type: "instrument", tag } : null);
  };

  const value: Workstation = {
    sim,
    state,
    layout,
    prefs,
    setPrefs,
    selection,
    select: setSelection,
    selectTag,
    route,
    go,
    actions,
    scenarios,
    exercises,
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
