import { ArrowRight, Droplets, Layers, Workflow } from "lucide-react";

import { useWorkstation } from "@/app/context";
import { PageBody } from "@/app/PageBody";
import { Badge, Button, Panel } from "@/components/ui/primitives";
import { valveVisual, VALVE_LABEL } from "@/lib/stateColors";
import { fmt, formatDuration, paToBarDelta } from "@/lib/units";
import { cn } from "@/lib/utils";
import type { RestrictionSnapshot } from "@/types/simulation";

const VIS_TONE = { open: "ok", closed: "bad", partial: "warn", moving: "warn", fault: "fault" } as const;

const GROUP_OF: Record<string, "production" | "annulus" | "chemical"> = {
  scssv: "production",
  master: "production",
  wing: "production",
  isolation: "production",
  choke: "production",
  annulus_master: "annulus",
  annulus_wing: "annulus",
  crossover: "annulus",
  injection_isolation: "chemical",
  metering: "chemical",
};

function ValveCard({ v }: { v: RestrictionSnapshot }) {
  const { actions, selectTag, selection } = useWorkstation();
  const vis = valveVisual(v);
  const selected = selection?.type === "element" && selection.id === v.id;
  return (
    <article
      className={cn(
        "flex flex-col rounded-xl border bg-panel p-4 shadow-[var(--shadow-card)] transition-colors",
        selected ? "border-accent/50 ring-2 ring-accent/15" : "border-line",
      )}
      data-testid={`valve-card-${v.tag}`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="num text-[15px] font-semibold">{v.tag}</div>
          <div className="truncate text-[12.5px] text-dim">{v.name}</div>
        </div>
        <Badge tone={VIS_TONE[vis]}>{VALVE_LABEL[vis].toLowerCase()}</Badge>
      </div>

      <div className="mt-3">
        <div className="relative h-2 overflow-hidden rounded-full bg-panel-3" aria-hidden>
          <div className="absolute inset-y-0 left-0 rounded-full bg-flow transition-[width] duration-500 ease-[var(--ease-out)]" style={{ width: `${v.position_pct}%` }} />
          <div className="absolute -inset-y-0.5 w-0.5 rounded bg-navy" style={{ left: `calc(${v.commanded_pct}% - 1px)` }} title="commanded" />
        </div>
        <div className="num mt-1.5 flex justify-between text-[12px] text-muted">
          <span>
            actual <span className="font-semibold text-fg">{fmt(v.position_pct, 1)}%</span>
          </span>
          <span>
            command <span className="font-semibold text-fg">{fmt(v.commanded_pct, 0)}%</span>
          </span>
        </div>
      </div>

      <dl className="num mt-3 grid grid-cols-2 gap-x-3 gap-y-1 text-[12px]">
        <dt className="text-dim">ΔP across</dt>
        <dd className="text-right">{v.dp_pa === null ? "—" : `${fmt(paToBarDelta(v.dp_pa), 2)} bar`}</dd>
        <dt className="text-dim">Stroke</dt>
        <dd className="text-right">
          {fmt(v.full_stroke_time_s, 0)} s{v.actuation_delay_s ? ` + ${fmt(v.actuation_delay_s, 0)} s delay` : ""}
        </dd>
        <dt className="text-dim">Status</dt>
        <dd className="truncate text-right">
          {v.moving ? (v.phase === "delay" ? "signal dead time" : `travelling ${formatDuration(v.time_to_target_s)}`) : v.leaking ? <span className="text-fault">seat leak</span> : "idle"}
        </dd>
      </dl>

      <div className="mt-auto flex items-center gap-2 pt-4">
        <Button size="sm" variant="ok" className="flex-1" disabled={!v.supported_commands.includes("open")} onClick={() => actions.valve(v.tag, "open")} aria-label={`${v.tag} open`}>
          Open
        </Button>
        <Button size="sm" variant="bad" className="flex-1" disabled={!v.supported_commands.includes("close")} onClick={() => actions.valve(v.tag, "close")} aria-label={`${v.tag} close`}>
          Close
        </Button>
        <Button size="icon" variant="ghost" onClick={() => selectTag(v.tag)} aria-label={`${v.tag} details`} title="Details & set position">
          <ArrowRight size={16} />
        </Button>
      </div>
    </article>
  );
}

export function ValvesPage() {
  const { state } = useWorkstation();
  const valves = state.elements.filter((e): e is RestrictionSnapshot => e.kind === "valve" || e.kind === "choke");
  const groups: { id: "production" | "annulus" | "chemical"; title: string; sub: string; icon: React.ReactNode }[] = [
    { id: "production", title: "Production tree & well", sub: "SCSSV, master, wing and production choke", icon: <Workflow size={16} /> },
    { id: "annulus", title: "Annulus", sub: "Annulus master, wing and crossover valves", icon: <Layers size={16} /> },
    { id: "chemical", title: "Chemical injection", sub: "Isolation and metering valves of each circuit", icon: <Droplets size={16} /> },
  ];
  return (
    <PageBody intro="Operate every valve from one place. The bar shows the actual position; the dark marker is the commanded position — valves take time to travel, and the process keeps responding after they stop.">
      <div className="space-y-6">
        {groups.map((g) => {
          const list = valves.filter((v) => (GROUP_OF[v.subtype] ?? "production") === g.id);
          if (!list.length) return null;
          return (
            <section key={g.id}>
              <div className="mb-2.5 flex items-center gap-2">
                <span className="text-dim">{g.icon}</span>
                <h2 className="t-heading">{g.title}</h2>
                <span className="text-[12.5px] text-dim">· {g.sub}</span>
              </div>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
                {list.map((v) => (
                  <ValveCard key={v.tag} v={v} />
                ))}
              </div>
            </section>
          );
        })}
        {state.mode !== "dynamic" && valves.some((v) => v.branch) && (
          <Panel title="Note">
            <p className="p-4 text-[13px] text-muted">The steady model does not represent annulus or injection branches: their valves move but have no process response.</p>
          </Panel>
        )}
      </div>
    </PageBody>
  );
}
