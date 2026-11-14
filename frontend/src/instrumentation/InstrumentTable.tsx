import { Badge } from "@/components/ui/primitives";
import { valveVisual, VALVE_LABEL } from "@/lib/stateColors";
import { type DisplayPrefs, fmt, instrumentDisplay, paToBarDelta } from "@/lib/units";
import type { InstrumentStatus, RestrictionSnapshot, SimulationState } from "@/types/simulation";

const STATUS_TONE: Record<InstrumentStatus, "ok" | "warn" | "fault"> = {
  GOOD: "ok",
  OUT_OF_RANGE_HIGH: "warn",
  OUT_OF_RANGE_LOW: "warn",
  UNDETERMINED: "fault",
  BAD: "fault",
};

const th = "border-b border-line px-2 py-1 text-left text-[10px] font-bold uppercase tracking-[0.1em] text-dim";
const td = "border-b border-line/50 px-2 py-1";

export function InstrumentTable({ state, prefs, onSelect }: { state: SimulationState; prefs: DisplayPrefs; onSelect?: (tag: string) => void }) {
  const nodeName = (id: string | null) => state.nodes.find((n) => n.id === id)?.name ?? "—";
  const groups: [string, string[]][] = [
    ["Pressure", ["pressure", "differential_pressure"]],
    ["Temperature", ["temperature"]],
    ["Flow", ["flow"]],
  ];
  return (
    <table className="w-full border-collapse" data-testid="instrument-table">
      <thead className="sticky top-0 bg-panel-2">
        <tr>
          <th className={th}>Tag</th>
          <th className={th}>Description</th>
          <th className={th}>Location</th>
          <th className={`${th} text-right`}>Measured</th>
          <th className={th}>Unit</th>
          <th className={`${th} text-right`}>Range</th>
          <th className={th}>Quality</th>
        </tr>
      </thead>
      <tbody>{groups.map(([label, types]) => renderGroup(label, types))}</tbody>
    </table>
  );

  function renderGroup(label: string, types: string[]) {
    const rows = state.instruments.filter((i) => types.includes(i.type));
    if (!rows.length) return null;
    return [
      <tr key={`g-${label}`}>
        <td colSpan={7} className="bg-panel-3/50 px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] text-muted">
          {label}
        </td>
      </tr>,
      ...rows.map((i) => {
        const d = instrumentDisplay(i.type, i.value_si, prefs);
        const lo = instrumentDisplay(i.type, i.range_min_si, prefs);
        const hi = instrumentDisplay(i.type, i.range_max_si, prefs);
        const loc = i.type === "differential_pressure" ? `${nodeName(i.high_node)} − ${nodeName(i.low_node)}` : nodeName(i.node);
        return (
          <tr key={i.tag} className="cursor-pointer hover:bg-panel-3/60" onClick={() => onSelect?.(i.tag)} data-testid={`row-${i.tag}`}>
            <td className={`${td} num font-bold`}>{i.tag}</td>
            <td className={`${td} text-muted`}>{i.description}</td>
            <td className={`${td} text-muted`}>{loc}</td>
            <td className={`${td} num text-right text-[13px] text-fg`}>{fmt(d.value, d.digits)}</td>
            <td className={`${td} text-dim`}>{d.unit}</td>
            <td className={`${td} num text-right text-dim`}>
              {fmt(lo.value, 0)}–{fmt(hi.value, 0)}
            </td>
            <td className={td}>
              <Badge tone={STATUS_TONE[i.status]}>{i.status.replace(/_/g, " ")}</Badge>
            </td>
          </tr>
        );
      }),
    ];
  }
}

export function ValveTable({ state, onSelect }: { state: SimulationState; onSelect?: (id: string) => void }) {
  const valves = state.elements.filter((e): e is RestrictionSnapshot => e.kind === "valve" || e.kind === "choke");
  return (
    <table className="w-full border-collapse" data-testid="valve-table">
      <thead className="sticky top-0 bg-panel-2">
        <tr>
          <th className={th}>Tag</th>
          <th className={th}>Type</th>
          <th className={`${th} text-right`}>Commanded</th>
          <th className={`${th} text-right`}>Actual</th>
          <th className={th}>State</th>
          <th className={th}>Actuation</th>
          <th className={`${th} text-right`}>ΔP across [bar]</th>
          <th className={th}>Operations</th>
        </tr>
      </thead>
      <tbody>
        {valves.map((v) => {
          const vis = valveVisual(v);
          return (
            <tr key={v.tag} className="cursor-pointer hover:bg-panel-3/60" onClick={() => onSelect?.(v.id)}>
              <td className={`${td} num font-bold`}>{v.tag}</td>
              <td className={`${td} text-muted`}>{v.name}</td>
              <td className={`${td} num text-right`}>{fmt(v.commanded_pct, 1)} %</td>
              <td className={`${td} num text-right`}>{fmt(v.position_pct, 1)} %</td>
              <td className={td}>
                <Badge tone={{ open: "ok", closed: "bad", partial: "warn", moving: "warn", fault: "fault" }[vis] as "ok"}>{VALVE_LABEL[vis]}</Badge>
              </td>
              <td className={`${td} text-muted`}>{v.moving ? `travelling (${fmt(v.time_to_target_s, 0)} s)` : "idle"}</td>
              <td className={`${td} num text-right`}>{v.dp_pa === null ? "undet." : fmt(paToBarDelta(v.dp_pa), 2)}</td>
              <td className={`${td} text-dim`}>{v.supported_commands.join(", ") || "none (unavailable)"}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
