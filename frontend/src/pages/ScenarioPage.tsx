import { Check, Cpu, Layers, Waves } from "lucide-react";

import { useWorkstation } from "@/app/context";
import { PageBody } from "@/app/PageBody";
import { Badge, Button, Panel } from "@/components/ui/primitives";
import { fmt } from "@/lib/units";
import { cn } from "@/lib/utils";
import type { SimMode } from "@/types/simulation";

const MODE_INFO: Record<SimMode, { title: string; points: string[] }> = {
  dynamic: {
    title: "Dynamic model",
    points: [
      "Pressures, flows, temperatures and concentrations evolve over simulated time",
      "Line-pack, wellbore storage and a radial reservoir transient",
      "Annulus, chemical-injection circuits and integrity tests",
      "Transmitter lag, update interval and resolution",
    ],
  },
  steady: {
    title: "Steady model",
    points: [
      "Algebraic operating point of the production path, recalculated instantly",
      "Transient temperatures; valves still travel at their stroke speed",
      "Best for pressure-budget teaching (Exercise 3)",
      "Annulus and injection branches are not modelled",
    ],
  },
};

function scenarioTag(id: string): string {
  if (id.startsWith("dyn_")) return `Scenario ${id.split("_")[1].toUpperCase()}`;
  if (id.startsWith("ex")) return "Exercise";
  if (id === "subsea_dynamic_base") return "Full system";
  if (id === "xt_230xp22b") return "Tree workstation";
  return "Release 1";
}

export function ScenarioPage() {
  const { state, scenarios, actions, sim } = useWorkstation();
  const mode = state.mode ?? "steady";
  const trainingActive = !!sim.training;
  const res = state.reservoir_model;
  const sorted = [...scenarios].sort((a, b) => scenarioTag(a.id).localeCompare(scenarioTag(b.id)) || a.name.localeCompare(b.name));

  return (
    <PageBody>
      <section>
        <div className="mb-2.5 flex items-baseline justify-between gap-3">
          <h2 className="t-heading">Training scenarios</h2>
          {trainingActive && <span className="text-[12.5px] text-warn">Close the training exercise to change scenario.</span>}
        </div>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3" role="radiogroup" aria-label="Scenario">
          {sorted.map((s) => {
            const active = s.id === state.scenario.id;
            return (
              <button
                key={s.id}
                type="button"
                role="radio"
                aria-checked={active}
                disabled={trainingActive && !active}
                onClick={() => !active && actions.scenario(s.id)}
                data-testid={`scenario-${s.id}`}
                className={cn(
                  "pressable group relative flex flex-col rounded-xl border bg-panel p-4 text-left shadow-[var(--shadow-card)] disabled:opacity-50",
                  active ? "border-navy ring-2 ring-navy/10" : "border-line hover:border-line-strong",
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <Badge tone={active ? "accent" : "neutral"}>{scenarioTag(s.id)}</Badge>
                  {active && (
                    <span className="flex items-center gap-1 text-xs font-semibold text-navy">
                      <Check size={14} /> Loaded
                    </span>
                  )}
                </div>
                <div className="t-heading mt-2 text-fg">{s.name.replace(/\s*\(illustrative\)/i, "")}</div>
                <p className="mt-1 line-clamp-3 text-[12.5px] leading-snug text-dim">{s.description}</p>
              </button>
            );
          })}
        </div>
      </section>

      <section className="mt-6">
        <h2 className="t-heading mb-2.5">Simulation model</h2>
        <div className="grid gap-3 md:grid-cols-2">
          {(["dynamic", "steady"] as SimMode[]).map((m) => {
            const active = m === mode;
            return (
              <div key={m} className={cn("rounded-xl border bg-panel p-4 shadow-[var(--shadow-card)]", active ? "border-navy ring-2 ring-navy/10" : "border-line")}>
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    {m === "dynamic" ? <Waves size={18} className="text-flow" /> : <Layers size={18} className="text-dim" />}
                    <span className="t-heading">{MODE_INFO[m].title}</span>
                  </div>
                  {active ? (
                    <Badge tone="accent">Active</Badge>
                  ) : (
                    <Button size="xs" variant="subtle" disabled={trainingActive} onClick={() => actions.mode(m)}>
                      Switch
                    </Button>
                  )}
                </div>
                <ul className="mt-3 space-y-1.5 text-[13px] text-muted">
                  {MODE_INFO[m].points.map((p) => (
                    <li key={p} className="flex gap-2">
                      <Check size={14} className={cn("mt-0.5 shrink-0", active ? "text-ok" : "text-static")} />
                      {p}
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </div>
        <p className="mt-2 text-[12.5px] text-dim">Switching the model restarts the scenario from its initial conditions.</p>
      </section>

      <section className="mt-6 grid gap-4 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <Panel title="Active model equations & assumptions" icon={<Cpu size={16} />}>
          <dl className="divide-y divide-line">
            {Object.entries(state.model).map(([k, v]) => (
              <div key={k} className="grid gap-1 px-4 py-3 sm:grid-cols-[120px_1fr]">
                <dt className="text-[12.5px] font-semibold capitalize text-fg">{k}</dt>
                <dd className="text-[13px] leading-relaxed text-muted">{v}</dd>
              </div>
            ))}
          </dl>
        </Panel>
        <div className="flex flex-col gap-4">
          <Panel title="Fluid & boundaries">
            <dl className="num grid grid-cols-[1fr_auto] gap-x-4 gap-y-1.5 px-4 py-3 text-[13px]">
              <dt className="font-sans text-muted">Fluid</dt>
              <dd className="max-w-[220px] truncate text-right font-sans">{state.fluid.name}</dd>
              <dt className="font-sans text-muted">Density</dt>
              <dd className="text-right">{fmt(state.fluid.density_kg_m3, 0)} kg/m³</dd>
              <dt className="font-sans text-muted">Reservoir pressure</dt>
              <dd className="text-right">{fmt(state.boundary.reservoir_pressure_pa / 1e5, 1)} bara</dd>
              <dt className="font-sans text-muted">Arrival pressure</dt>
              <dd className="text-right">{fmt(state.boundary.downstream_pressure_pa / 1e5, 1)} bara</dd>
              {state.fluid.compressibility_1_pa !== undefined && (
                <>
                  <dt className="font-sans text-muted">Compressibility</dt>
                  <dd className="text-right">{(state.fluid.compressibility_1_pa * 1e5).toExponential(1)} /bar</dd>
                </>
              )}
            </dl>
          </Panel>
          {res && (
            <Panel title="Reservoir transient">
              <dl className="num grid grid-cols-[1fr_auto] gap-x-4 gap-y-1.5 px-4 py-3 text-[13px]">
                <dt className="font-sans text-muted">Permeability</dt>
                <dd className="text-right">{fmt(res.permeability_m2 / 9.869e-16, 0)} mD</dd>
                <dt className="font-sans text-muted">Diffusivity k/(φμc_t)</dt>
                <dd className="text-right">{fmt(res.diffusivity_m2_s, 3)} m²/s</dd>
                <dt className="font-sans text-muted">Drainage radius</dt>
                <dd className="text-right">{fmt(res.radii_m[res.radii_m.length - 1], 0)} m</dd>
                <dt className="font-sans text-muted">Pore volume</dt>
                <dd className="text-right">{fmt(res.pore_volume_m3 / 1e3, 0)} ×10³ m³</dd>
              </dl>
            </Panel>
          )}
        </div>
      </section>
    </PageBody>
  );
}
