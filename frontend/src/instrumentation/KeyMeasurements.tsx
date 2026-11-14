import { type DisplayPrefs, FLOW_LABEL, flowFromM3s, fmt, instrumentDisplay, paToBarDelta } from "@/lib/units";
import type { SimulationState } from "@/types/simulation";

const TONE: Record<string, string> = { fg: "text-fg", accent: "text-accent", fault: "text-fault", warn: "text-warn" };

function Tile({ label, value, unit, sub, tone = "fg", testId }: { label: string; value: string; unit: string; sub?: string; tone?: string; testId?: string }) {
  return (
    <div className="min-w-[118px] flex-1 border-r border-line px-2.5 py-1.5 last:border-r-0" data-testid={testId}>
      <div className="truncate text-[10px] font-bold uppercase tracking-[0.1em] text-dim">{label}</div>
      <div className={`num text-[17px] leading-tight ${TONE[tone] ?? "text-fg"}`}>
        {value}
        <span className="ml-1 text-[10px] text-muted">{unit}</span>
      </div>
      {sub && <div className="truncate text-[10px] text-dim">{sub}</div>}
    </div>
  );
}

/** Model results and selected transmitter readings, driven by scenario config. */
export function KeyMeasurements({ state, prefs }: { state: SimulationState; prefs: DisplayPrefs }) {
  const h = state.hydraulics;
  const failed = h.status === "failed" || state.diagnostics.some((d) => d.severity === "error");
  const q = h.q_m3s;
  const keyTypes = ["flow", "differential_pressure"];
  const keyInst = state.instruments.filter((i) => keyTypes.includes(i.type));
  const firstOf = (type: string) => state.instruments.filter((i) => i.type === type);
  const pressures = firstOf("pressure");
  const temps = firstOf("temperature");
  const pick = [pressures[0], pressures[1], pressures[pressures.length - 1], temps[1] ?? temps[0], temps[temps.length - 1]].filter(Boolean);
  return (
    <div className="flex flex-wrap border-b border-line bg-panel-2/60">
      <Tile
        testId="kpi-flow"
        label="Flow (model)"
        value={failed ? "INVALID" : fmt(q === null ? null : flowFromM3s(q, prefs.flowUnit), 0)}
        unit={failed ? "" : FLOW_LABEL[prefs.flowUnit]}
        sub={failed ? h.message || "see diagnostics" : `${fmt(h.mass_flow_kg_s, 2)} kg/s · ${h.status.replace("_", "-")}`}
        tone={failed ? "fault" : "accent"}
      />
      <Tile
        label="Net static drive"
        value={fmt(h.driving_pressure_pa === null ? null : paToBarDelta(h.driving_pressure_pa), 1)}
        unit="bar"
        sub="P_res − P_down − ρgΔz"
      />
      {[...keyInst, ...pick].map((i) => {
        const d = instrumentDisplay(i.type, i.value_si, prefs);
        return (
          <Tile key={i.tag} label={i.tag} value={i.value_si === null ? i.status.slice(0, 5) : fmt(d.value, d.digits)} unit={d.unit} sub={i.description}
            tone={i.status === "GOOD" ? "fg" : "warn"} />
        );
      })}
    </div>
  );
}
