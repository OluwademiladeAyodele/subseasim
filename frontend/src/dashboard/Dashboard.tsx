import { useEffect, useState } from "react";

import { Panel, Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/primitives";
import { TrendsView } from "@/charts/TrendsView";
import { ComponentPanel } from "@/controls/ComponentPanel";
import { ConditionsPanel } from "@/controls/ConditionsPanel";
import type { Simulation } from "@/hooks/useSimulation";
import { InstrumentTable, ValveTable } from "@/instrumentation/InstrumentTable";
import { KeyMeasurements } from "@/instrumentation/KeyMeasurements";
import type { DisplayPrefs } from "@/lib/units";
import { TreeSchematic, type Selection } from "@/schematic/TreeSchematic";
import { api } from "@/services/api";
import { TrainingPanel } from "@/training/TrainingPanel";
import type { ExerciseSummary, ScenarioInfo } from "@/types/simulation";

import { DiagnosticsPanel } from "./DiagnosticsPanel";
import { EventLog } from "./EventLog";
import { TopBar } from "./TopBar";

const PREFS_KEY = "subseasim.prefs";

function loadPrefs(): DisplayPrefs {
  try {
    const p = JSON.parse(localStorage.getItem(PREFS_KEY) ?? "null");
    if (p && (p.pressureRef === "bara" || p.pressureRef === "barg")) return p;
  } catch {
    /* ignore */
  }
  return { pressureRef: "bara", flowUnit: "m3/d" };
}

export function Dashboard({ sim }: { sim: Simulation }) {
  const { state, layout, training, samples, events, connection, error, run } = sim;
  const [prefs, setPrefsState] = useState<DisplayPrefs>(loadPrefs);
  const [selection, setSelection] = useState<Selection>(null);
  const [rightTab, setRightTab] = useState("component");
  const [scenarios, setScenarios] = useState<ScenarioInfo[]>([]);
  const [exercises, setExercises] = useState<ExerciseSummary[]>([]);

  useEffect(() => {
    api.scenarios().then(setScenarios).catch(() => undefined);
    api.exercises().then(setExercises).catch(() => undefined);
  }, []);

  const setPrefs = (p: DisplayPrefs) => {
    setPrefsState(p);
    try {
      localStorage.setItem(PREFS_KEY, JSON.stringify(p));
    } catch {
      /* ignore */
    }
  };

  const select = (s: Selection) => {
    setSelection(s);
    if (s) setRightTab("component");
  };

  if (!state || !layout) {
    return (
      <div className="flex h-full items-center justify-center text-muted">
        {error ? <span className="text-bad">{error}</span> : "Connecting to the SubseaSim engine…"}
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <TopBar
        state={state}
        scenarios={scenarios}
        connection={connection}
        prefs={prefs}
        setPrefs={setPrefs}
        trainingActive={!!training}
        onLifecycle={(a) => run((sid) => api.lifecycle(sid, a))}
        onSpeed={(s) => run((sid) => api.speed(sid, s))}
        onScenario={(id) => {
          setSelection(null);
          run((sid) => api.loadScenario(sid, id));
        }}
      />
      {error && (
        <div role="alert" className="flex items-center justify-between border-b border-bad/50 bg-bad/10 px-3 py-1 text-bad" data-testid="error-banner">
          <span>{error}</span>
          <button type="button" className="text-[11px] uppercase text-muted hover:text-fg" onClick={sim.clearError}>
            dismiss
          </button>
        </div>
      )}

      <main className="grid min-h-0 flex-1 grid-cols-1 gap-1.5 overflow-auto p-1.5 lg:grid-cols-[minmax(0,1fr)_380px] lg:grid-rows-[minmax(0,1.55fr)_minmax(0,1fr)] lg:overflow-hidden">
        <Panel
          title={
            <>
              Production system schematic · <span className="normal-case tracking-normal text-fg">{state.scenario.name}</span>
            </>
          }
          right={<span className="text-[10px] text-warn">{state.scenario.data_classification}</span>}
          className="min-h-[520px] lg:min-h-0"
          bodyClassName="flex flex-col"
        >
          <KeyMeasurements state={state} prefs={prefs} />
          <div className="min-h-0 flex-1 p-1">
            <TreeSchematic state={state} layout={layout} selection={selection} onSelect={select} prefs={prefs} />
          </div>
        </Panel>

        <Panel className="min-h-[560px] lg:row-span-2 lg:min-h-0" bodyClassName="flex flex-col">
          <Tabs value={rightTab} onValueChange={setRightTab} className="flex min-h-0 flex-1 flex-col">
            <TabsList>
              <TabsTrigger value="component">Component</TabsTrigger>
              <TabsTrigger value="conditions">Conditions</TabsTrigger>
              <TabsTrigger value="training">
                Training{training ? <span className="ml-1 text-fault">●</span> : null}
              </TabsTrigger>
            </TabsList>
            <TabsContent value="component">
              {training && (
                <button
                  type="button"
                  onClick={() => setRightTab("training")}
                  className="block w-full border-b border-fault/40 bg-fault/5 px-3 py-1.5 text-left hover:bg-fault/10"
                  data-testid="training-banner"
                >
                  <span className="text-[10px] font-bold uppercase tracking-[0.12em] text-fault">Training step {training.index + 1}/{training.steps.length}</span>
                  <span className="block text-fg">{training.current.title}</span>
                  {training.current.kind === "task" && (
                    <span className={training.current.complete ? "block text-ok" : "block text-warn"}>
                      {training.current.complete ? "Task complete — open Training to continue" : training.current.hint}
                    </span>
                  )}
                </button>
              )}
              <ComponentPanel state={state} selection={selection} prefs={prefs} onCommand={(tag, c, p) => run((sid) => api.valve(sid, tag, c, p))} />
            </TabsContent>
            <TabsContent value="conditions">
              <ConditionsPanel
                state={state}
                prefs={prefs}
                onBoundary={(b) => run((sid) => api.boundary(sid, b))}
                onFluid={(f) => run((sid) => api.fluid(sid, f))}
              />
            </TabsContent>
            <TabsContent value="training" className="flex flex-col">
              <TrainingPanel
                training={training}
                exercises={exercises}
                onStart={(id) => {
                  setSelection(null);
                  run((sid) => api.trainingStart(sid, id));
                }}
                onAnswer={(step, choice) => run((sid) => api.trainingAnswer(sid, step, choice))}
                onAdvance={() => run((sid) => api.trainingAdvance(sid))}
                onStop={() => run((sid) => api.trainingStop(sid))}
              />
            </TabsContent>
          </Tabs>
          <div className="h-[34%] min-h-[150px] shrink-0 border-t border-line">
            <div className="flex h-6 items-center border-b border-line bg-panel-2 px-2.5 text-[11px] font-bold uppercase tracking-[0.12em] text-muted">Recent events</div>
            <div className="h-[calc(100%-1.5rem)] overflow-auto">
              <EventLog events={events} compact limit={30} />
            </div>
          </div>
        </Panel>

        <Panel className="min-h-[420px] lg:min-h-0" bodyClassName="flex flex-col">
          <Tabs defaultValue="trends" className="flex min-h-0 flex-1 flex-col">
            <TabsList>
              <TabsTrigger value="trends">Trends</TabsTrigger>
              <TabsTrigger value="instruments">Instruments</TabsTrigger>
              <TabsTrigger value="valves">Valves</TabsTrigger>
              <TabsTrigger value="events">Event history</TabsTrigger>
              <TabsTrigger value="diagnostics">
                Diagnostics
                {state.diagnostics.some((d) => d.severity !== "info") ? <span className="ml-1 text-warn">●</span> : null}
              </TabsTrigger>
            </TabsList>
            <TabsContent value="trends">
              <TrendsView state={state} samples={samples} prefs={prefs} />
            </TabsContent>
            <TabsContent value="instruments">
              <InstrumentTable state={state} prefs={prefs} onSelect={(tag) => select({ type: "instrument", tag })} />
            </TabsContent>
            <TabsContent value="valves">
              <ValveTable state={state} onSelect={(id) => select({ type: "element", id })} />
            </TabsContent>
            <TabsContent value="events">
              <EventLog events={events} />
            </TabsContent>
            <TabsContent value="diagnostics">
              <DiagnosticsPanel state={state} />
            </TabsContent>
          </Tabs>
        </Panel>
      </main>
      <footer className="border-t border-line bg-panel px-3 py-0.5 text-[10px] text-dim">
        SubseaSim is an educational simulator using illustrative data and simplified models. It is not safety-certified, must not be used for operational
        decisions, and has no interface to real subsea, SCADA or control systems.
      </footer>
    </div>
  );
}
