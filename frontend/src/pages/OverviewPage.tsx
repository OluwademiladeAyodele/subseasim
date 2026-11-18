import { BookOpen, ChevronRight, Lightbulb, Radio, Workflow } from "lucide-react";
import { useState } from "react";

import { useWorkstation } from "@/app/context";
import { PageBody } from "@/app/PageBody";
import { Badge, Panel } from "@/components/ui/primitives";
import { EventLog } from "@/dashboard/EventLog";
import { KeyMeasurements } from "@/instrumentation/KeyMeasurements";
import { valveVisual, VALVE_LABEL } from "@/lib/stateColors";
import { fmt } from "@/lib/units";
import { cn } from "@/lib/utils";
import { displayTag } from "@/lib/tags";
import { TreeSchematic } from "@/schematic/TreeSchematic";
import { XtSchematic } from "@/schematic/XtSchematic";
import type { RouteId } from "@/app/routes";
import type { RestrictionSnapshot } from "@/types/simulation";

const VIS_TONE = { open: "ok", closed: "bad", partial: "warn", moving: "warn", fault: "fault" } as const;

function Briefing({ lines }: { lines: string[] }) {
  const [open, setOpen] = useState(true);
  return (
    <section className="relative overflow-hidden rounded-xl border border-cyan/40 bg-gradient-to-br from-[#ecfeff] to-white p-4" data-testid="briefing">
      <div aria-hidden className="blob absolute -right-8 -top-10 h-28 w-28 bg-cyan/20" />
      <button type="button" onClick={() => setOpen(!open)} className="relative flex w-full items-center gap-2 text-left" aria-expanded={open}>
        <Lightbulb size={16} className="text-[#0e7490]" />
        <span className="t-heading flex-1 text-[#164e63]">Scenario briefing</span>
        <ChevronRight size={16} className={cn("text-[#0e7490] transition-transform", open && "rotate-90")} />
      </button>
      {open && (
        <ul className="relative mt-2 space-y-1.5 text-[13px] leading-snug text-[#155e75]">
          {lines.map((l) => (
            <li key={l} className="flex gap-2">
              <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-[#0e7490]" />
              {l}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function TrainingCard() {
  const { sim, go } = useWorkstation();
  const t = sim.training;
  if (!t) return null;
  return (
    <button
      type="button"
      onClick={() => go("training")}
      className="pressable block w-full rounded-xl border border-[#c4b5fd] bg-[#f5f3ff] p-4 text-left hover:border-[#a78bfa]"
      data-testid="training-banner"
    >
      <div className="flex items-center gap-2 text-xs font-semibold text-[#6d28d9]">
        <BookOpen size={14} /> Training · step {t.index + 1} of {t.steps.length}
      </div>
      <div className="t-heading mt-1 text-fg">{t.current.title}</div>
      {t.current.kind === "task" && (
        <div className={cn("mt-1 text-[13px]", t.current.complete ? "text-ok" : "text-warn")}>
          {t.current.complete ? "Task complete — open Training to continue" : t.current.hint}
        </div>
      )}
    </button>
  );
}

function ValveStatus() {
  const { state, selectTag } = useWorkstation();
  const valves = state.elements.filter((e): e is RestrictionSnapshot => (e.kind === "valve" || e.kind === "choke") && !e.branch);
  return (
    <Panel title="Production valves" icon={<Workflow size={16} />} bodyClassName="py-1">
      <ul>
        {valves.map((v) => {
          const vis = valveVisual(v);
          return (
            <li key={v.tag}>
              <button type="button" onClick={() => selectTag(v.tag)} className="flex w-full items-center gap-3 px-4 py-2 text-left hover:bg-panel-2">
                <span className="num w-[86px] text-[13px] font-semibold" title={v.tag}>{displayTag(state, v.tag)}</span>
                <span className="relative h-1.5 flex-1 overflow-hidden rounded-full bg-panel-3">
                  <span className="absolute inset-y-0 left-0 rounded-full bg-flow transition-[width] duration-500" style={{ width: `${v.position_pct}%` }} />
                </span>
                <span className="num w-11 text-right text-[12px] text-muted">{fmt(v.position_pct, 0)}%</span>
                <Badge tone={VIS_TONE[vis]} className="w-[86px] justify-center">
                  {VALVE_LABEL[vis].toLowerCase()}
                </Badge>
              </button>
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}

export function OverviewPage() {
  const { state, layout, selection, select, prefs, sim, selectTag, go } = useWorkstation();
  const dynamic = state.mode === "dynamic";
  // the tree workstation is the main view; scenarios without one fall back to the generic tree
  const xt = !!state.schematic;
  return (
    <PageBody>
      <KeyMeasurements state={state} prefs={prefs} onSelect={selectTag} />
      <Panel
        title={xt ? `Christmas tree workstation — ${state.schematic!.title}` : "Production system"}
        subtitle={
          dynamic
            ? "Click any component to inspect and operate it · scroll to zoom, drag to pan · ▲▼ rate of change · → ss = steady-state value a pressure is relaxing toward"
            : "Click any component to inspect and operate it · scroll to zoom, drag to pan"
        }
        right={
          <div className="flex items-center gap-2">
            <Badge tone={dynamic ? "accent" : "neutral"}>{dynamic ? "Dynamic model" : "Steady model"}</Badge>
            <Badge tone="warn">{state.scenario.data_classification}</Badge>
          </div>
        }
        className="mt-4"
        bodyClassName="flex"
      >
        {xt ? (
          <div className="mx-auto w-full max-w-[1600px]" style={{ aspectRatio: `${state.schematic!.width} / ${state.schematic!.height}` }}>
            <XtSchematic state={state} schematic={state.schematic!} selection={selection} onSelect={select} prefs={prefs} onNavigate={(p) => go(p as RouteId)} />
          </div>
        ) : (
          <div className="mx-auto w-full max-w-[1500px]" style={{ aspectRatio: `${layout.width} / ${layout.height}` }}>
            <TreeSchematic state={state} layout={layout} selection={selection} onSelect={select} prefs={prefs} />
          </div>
        )}
      </Panel>
      <div className="mt-4 grid items-start gap-4 lg:grid-cols-2 2xl:grid-cols-3">
        {(sim.training || !!state.briefing?.length) && (
          <div className="flex min-w-0 flex-col gap-4">
            <TrainingCard />
            {!!state.briefing?.length && <Briefing key={state.scenario.id} lines={state.briefing} />}
          </div>
        )}
        <Panel
          title="Live activity"
          icon={<Radio size={16} />}
          right={
            <button type="button" onClick={() => go("events")} className="text-xs font-medium text-accent hover:underline">
              All events
            </button>
          }
          className="max-h-[420px]"
          bodyClassName="overflow-y-auto"
        >
          <EventLog events={sim.events} compact limit={30} onTag={selectTag} aliases={state.tag_aliases} />
        </Panel>
        <ValveStatus />
      </div>
    </PageBody>
  );
}
