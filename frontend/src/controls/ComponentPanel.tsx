import { useEffect, useState } from "react";

import { Badge, Button, Input, Slider } from "@/components/ui/primitives";
import { valveVisual, VALVE_LABEL } from "@/lib/stateColors";
import {
  type DisplayPrefs,
  fmt,
  instrumentDisplay,
  kToC,
  paToBarDelta,
  piSiToField,
  pressureFromPa,
  unitLabel,
} from "@/lib/units";
import type { Selection } from "@/schematic/TreeSchematic";
import type {
  InflowSnapshot,
  InstrumentSnapshot,
  PipeSnapshot,
  RestrictionSnapshot,
  SimulationState,
  ValveCommand,
} from "@/types/simulation";

interface Props {
  state: SimulationState;
  selection: Selection;
  prefs: DisplayPrefs;
  onCommand: (tag: string, command: ValveCommand, position?: number) => Promise<boolean>;
}

function Row({ label, value, unit, mono = true }: { label: string; value: React.ReactNode; unit?: string; mono?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-line/60 py-1">
      <span className="text-muted">{label}</span>
      <span className={mono ? "num text-right text-fg" : "text-right text-fg"}>
        {value}
        {unit && <span className="ml-1 text-[10px] text-muted">{unit}</span>}
      </span>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mt-3">
      <h3 className="mb-1 text-[10px] font-bold uppercase tracking-[0.14em] text-dim">{title}</h3>
      {children}
    </div>
  );
}

const SUBTYPE: Record<string, string> = {
  scssv: "Surface-controlled subsurface safety valve",
  master: "Production master valve (gate)",
  wing: "Production wing valve (gate)",
  isolation: "Isolation valve",
  choke: "Production choke",
};

export function ComponentPanel({ state, selection, prefs, onCommand }: Props) {
  if (!selection) {
    return (
      <div className="p-3 text-muted">
        <p className="mb-2">Select a valve, choke, pipe, reservoir or transmitter on the schematic to inspect it.</p>
        <p className="text-dim">Valves and the choke show their available operations here.</p>
      </div>
    );
  }
  if (selection.type === "instrument") {
    const inst = state.instruments.find((i) => i.tag === selection.tag);
    return inst ? <InstrumentDetail inst={inst} state={state} prefs={prefs} /> : null;
  }
  const el = state.elements.find((e) => e.id === selection.id);
  if (!el) return null;
  switch (el.kind) {
    case "valve":
    case "choke":
      return <RestrictionDetail v={el as RestrictionSnapshot} state={state} prefs={prefs} onCommand={onCommand} />;
    case "pipe":
      return <PipeDetail p={el as PipeSnapshot} state={state} prefs={prefs} />;
    default:
      return <InflowDetail e={el as InflowSnapshot} state={state} prefs={prefs} />;
  }
}

function nodePressure(state: SimulationState, id: string) {
  return state.nodes.find((n) => n.id === id)?.pressure_pa ?? null;
}

function P({ pa, prefs }: { pa: number | null; prefs: DisplayPrefs }) {
  return <>{pa === null ? "undetermined" : fmt(pressureFromPa(pa, prefs.pressureRef), 1)}</>;
}

function RestrictionDetail({ v, state, prefs, onCommand }: { v: RestrictionSnapshot; state: SimulationState; prefs: DisplayPrefs; onCommand: Props["onCommand"] }) {
  const vis = valveVisual(v);
  const tone = { open: "ok", closed: "bad", partial: "warn", moving: "warn", fault: "fault" }[vis] as "ok" | "bad" | "warn" | "fault";
  const [target, setTarget] = useState(v.commanded_pct);
  const [busy, setBusy] = useState(false);
  useEffect(() => setTarget(v.commanded_pct), [v.tag, v.commanded_pct]);
  const up = nodePressure(state, v.from);
  const dn = nodePressure(state, v.to);
  const can = (c: ValveCommand) => v.supported_commands.includes(c);
  const send = async (c: ValveCommand, pos?: number) => {
    setBusy(true);
    await onCommand(v.tag, c, pos);
    setBusy(false);
  };
  const validTarget = Number.isFinite(target) && target >= 0 && target <= 100;

  return (
    <div className="p-3" data-testid="component-panel">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="num text-base font-bold text-fg">{v.tag}</div>
          <div className="text-muted">{SUBTYPE[v.subtype] ?? v.name}</div>
        </div>
        <Badge tone={tone} data-testid="valve-state">{VALVE_LABEL[vis]}</Badge>
      </div>

      <Section title="Position">
        <PositionBar actual={v.position_pct} commanded={v.commanded_pct} />
        <Row label="Actual position" value={fmt(v.position_pct, 1)} unit="%" />
        <Row label="Commanded position" value={fmt(v.commanded_pct, 1)} unit="%" />
        <Row label="Actuation" value={v.moving ? `travelling, ~${fmt(v.time_to_target_s, 0)} s sim time` : "at commanded position"} mono={false} />
        <Row label="Full-stroke time" value={fmt(v.full_stroke_time_s, 0)} unit="s" />
        {!v.available && <p className="mt-1 text-fault">Component unavailable (faulted): no operations accepted.</p>}
        {state.status !== "running" && v.moving && (
          <p className="mt-1 text-warn">Simulation is not running: travel resumes when simulation time runs.</p>
        )}
      </Section>

      <Section title="Operations">
        <div className="flex gap-2">
          <Button variant="ok" disabled={!can("open") || busy} onClick={() => send("open")}>Open</Button>
          <Button variant="bad" disabled={!can("close") || busy} onClick={() => send("close")}>Close</Button>
        </div>
        {can("set_position") ? (
          <div className="mt-3 space-y-1">
            <label className="text-muted" htmlFor={`pos-${v.tag}`}>Set position (0–100 %)</label>
            <Slider aria-label={`${v.tag} position`} min={0} max={100} step={0.5} value={[validTarget ? target : 0]} onValueChange={([x]) => setTarget(x)} />
            <div className="flex items-center gap-2">
              <Input id={`pos-${v.tag}`} type="number" min={0} max={100} step={0.5} value={Number.isFinite(target) ? target : ""}
                aria-invalid={!validTarget} onChange={(e) => setTarget(e.target.valueAsNumber)} className="w-24" />
              <span className="text-muted">%</span>
              <Button variant="primary" disabled={!validTarget || busy} onClick={() => send("set_position", target)}>Apply</Button>
            </div>
          </div>
        ) : (
          v.available && <p className="mt-2 text-dim">Discrete isolation valve: OPEN / CLOSE only (intermediate positions occur only while stroking).</p>
        )}
      </Section>

      <Section title="Process (simulated)">
        <Row label="Upstream pressure" value={<P pa={up} prefs={prefs} />} unit={prefs.pressureRef} />
        <Row label="Downstream pressure" value={<P pa={dn} prefs={prefs} />} unit={prefs.pressureRef} />
        <Row label="Differential across" value={v.dp_pa === null ? "undetermined" : fmt(paToBarDelta(v.dp_pa), 2)} unit="bar" />
        <Row label="Flow state" value={v.state.replace("_", " ")} mono={false} />
      </Section>

      <Section title="Model parameters">
        <Row label="Characteristic" value={v.characteristic.replace("_", " ")} mono={false} />
        <p className="py-1 text-[11px] text-dim">{v.characteristic_description}</p>
        {v.cv_max !== undefined && <Row label="Cv at 100 %" value={fmt(v.cv_max, 1)} unit="US gpm/psi½" />}
        {v.cv_max !== undefined && <Row label="Rangeability" value={fmt(v.rangeability, 0)} />}
        {v.loss_coefficient_open !== undefined && <Row label="K fully open" value={fmt(v.loss_coefficient_open, 2)} />}
        {v.bore_diameter_m !== undefined && <Row label="Bore" value={fmt(v.bore_diameter_m * 1000, 0)} unit="mm" />}
        <Row label="Effective Cd·A now" value={(v.capacity_m2 * 1e6).toFixed(2)} unit="mm²" />
        <p className="mt-1 text-[11px] text-dim">Generic characteristic for training — not manufacturer performance data.</p>
      </Section>
    </div>
  );
}

function PositionBar({ actual, commanded }: { actual: number; commanded: number }) {
  return (
    <div className="relative my-1 h-3 w-full border border-line-strong bg-bg" aria-hidden>
      <div className="absolute inset-y-0 left-0 bg-accent/50" style={{ width: `${actual}%` }} />
      <div className="absolute -inset-y-1 w-0.5 bg-warn" style={{ left: `calc(${commanded}% - 1px)` }} title="commanded" />
    </div>
  );
}

function PipeDetail({ p, state, prefs }: { p: PipeSnapshot; state: SimulationState; prefs: DisplayPrefs }) {
  return (
    <div className="p-3" data-testid="component-panel">
      <div className="num text-base font-bold">{p.id}</div>
      <div className="text-muted">{p.name}</div>
      <Section title="Geometry">
        <Row label="Measured length" value={fmt(p.length_m, 0)} unit="m" />
        <Row label="Elevation change" value={fmt(p.dz_m, 0)} unit="m" />
        <Row label="Inner diameter" value={fmt(p.inner_diameter_m * 1000, 1)} unit="mm" />
        <Row label="Roughness" value={fmt(p.roughness_m * 1e6, 0)} unit="µm" />
        <Row label="Overall U (inner)" value={fmt(p.overall_htc_w_m2k, 1)} unit="W/m²K" />
      </Section>
      <Section title="Hydraulics (simulated)">
        <Row label="Inlet pressure" value={<P pa={nodePressure(state, p.from)} prefs={prefs} />} unit={prefs.pressureRef} />
        <Row label="Outlet pressure" value={<P pa={nodePressure(state, p.to)} prefs={prefs} />} unit={prefs.pressureRef} />
        <Row label="Total ΔP" value={p.dp_pa === null ? "—" : fmt(paToBarDelta(p.dp_pa), 2)} unit="bar" />
        <Row label="  Hydrostatic" value={fmt(paToBarDelta(p.hydrostatic_dp_pa), 2)} unit="bar" />
        <Row label="  Friction" value={p.friction_dp_pa === undefined ? "—" : fmt(paToBarDelta(p.friction_dp_pa), 2)} unit="bar" />
        <Row label="Velocity" value={fmt(p.velocity_m_s, 2)} unit="m/s" />
        <Row label="Reynolds number" value={fmt(p.reynolds, 0)} />
      </Section>
    </div>
  );
}

function InflowDetail({ e, state, prefs }: { e: InflowSnapshot; state: SimulationState; prefs: DisplayPrefs }) {
  const pwf = nodePressure(state, e.to);
  return (
    <div className="p-3" data-testid="component-panel">
      <div className="text-base font-bold">Reservoir inflow</div>
      <div className="text-muted">Linear IPR: Q = J (P_res − P_wf)</div>
      <Section title="Inflow (simulated)">
        <Row label="Reservoir pressure" value={fmt(pressureFromPa(state.boundary.reservoir_pressure_pa, prefs.pressureRef), 1)} unit={prefs.pressureRef} />
        <Row label="Flowing bottomhole P_wf" value={<P pa={pwf} prefs={prefs} />} unit={prefs.pressureRef} />
        <Row label="Drawdown" value={e.dp_pa === null ? "—" : fmt(paToBarDelta(e.dp_pa), 2)} unit="bar" />
        <Row label="Productivity index J" value={fmt(piSiToField(e.productivity_index_si), 2)} unit="(m³/d)/bar" />
        <Row label="Reservoir temperature" value={fmt(kToC(state.boundary.reservoir_temperature_k), 1)} unit="°C" />
      </Section>
      <p className="mt-2 text-[11px] text-dim">Reservoir pressure is a fixed boundary (no depletion in Release 1). Change it under Conditions.</p>
    </div>
  );
}

function InstrumentDetail({ inst, state, prefs }: { inst: InstrumentSnapshot; state: SimulationState; prefs: DisplayPrefs }) {
  const m = instrumentDisplay(inst.type, inst.value_si, prefs);
  const pv = instrumentDisplay(inst.type, inst.pv_si, prefs);
  const lo = instrumentDisplay(inst.type, inst.range_min_si, prefs);
  const hi = instrumentDisplay(inst.type, inst.range_max_si, prefs);
  const node = (id: string | null) => state.nodes.find((n) => n.id === id)?.name ?? id ?? "—";
  const where = inst.type === "differential_pressure" ? `${node(inst.high_node)} → ${node(inst.low_node)}` : node(inst.node);
  return (
    <div className="p-3" data-testid="component-panel">
      <div className="flex items-start justify-between">
        <div>
          <div className="num text-base font-bold">{inst.tag}</div>
          <div className="text-muted">{inst.description}</div>
        </div>
        <Badge tone={inst.status === "GOOD" ? "ok" : inst.status.startsWith("OUT") ? "warn" : "fault"}>{inst.status.replace(/_/g, " ")}</Badge>
      </div>
      <Section title="Measurement (simulated)">
        <Row label="Displayed measurement" value={fmt(m.value, m.digits)} unit={unitLabel(inst.type, prefs)} />
        <Row label="Model process value" value={fmt(pv.value, pv.digits)} unit={unitLabel(inst.type, prefs)} />
        <Row label="Calibrated range" value={`${fmt(lo.value, 0)} – ${fmt(hi.value, 0)}`} unit={unitLabel(inst.type, prefs)} />
        <Row label="Location" value={where} mono={false} />
        <Row label="Type" value={inst.type.replace("_", " ")} mono={false} />
      </Section>
      <p className="mt-2 text-[11px] text-dim">
        Release 1 transmitters are ideal: measurement equals the model value within range, saturates at range limits outside it, and shows no value when
        the model cannot determine one.
      </p>
    </div>
  );
}
