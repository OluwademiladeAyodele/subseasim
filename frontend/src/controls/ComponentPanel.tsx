import { useEffect, useState } from "react";

import { Badge, Button, Input, Slider } from "@/components/ui/primitives";
import { valveVisual, VALVE_LABEL } from "@/lib/stateColors";
import {
  type DisplayPrefs,
  FLOW_LABEL,
  flowFromM3s,
  fmt,
  formatDuration,
  instrumentDisplay,
  kToC,
  paToBarDelta,
  piSiToField,
  pressureFromPa,
  unitLabel,
} from "@/lib/units";
import { ALIAS_STATUS_LABEL, aliasOf } from "@/lib/tags";
import type { Selection } from "@/schematic/TreeSchematic";
import type {
  CheckValveSnapshot,
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
        {unit && <span className="ml-1 text-[11.5px] text-muted">{unit}</span>}
      </span>
    </div>
  );
}

/** Display (reference) tag with the engineering tag and the alias provenance. */
function TagHeading({ state, tag }: { state: SimulationState; tag: string }) {
  const a = aliasOf(state, tag);
  if (!a || a.tag === tag) {
    return (
      <div className="num text-base font-bold text-fg" data-testid="tag-heading">
        {tag}
        {a?.status === "addition" && <div className="text-[11px] font-normal text-dim">{ALIAS_STATUS_LABEL.addition}</div>}
      </div>
    );
  }
  return (
    <div data-testid="tag-heading">
      <div className="num text-base font-bold text-fg">
        {a.tag} <span className="text-[12px] font-medium text-dim">· {tag}</span>
      </div>
      <div className="text-[11px] text-dim" title={a.note}>{ALIAS_STATUS_LABEL[a.status]}{a.note ? ` — ${a.note}` : ""}</div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mt-3">
      <h3 className="mb-1 t-eyebrow">{title}</h3>
      {children}
    </div>
  );
}

const SUBTYPE: Record<string, string> = {
  scssv: "Surface-controlled subsurface safety valve",
  master: "Production master valve (gate)",
  wing: "Production wing valve (gate)",
  swab: "Swab valve (vertical bore access, normally closed)",
  service_line: "Annulus service line valve",
  isolation: "Isolation valve",
  choke: "Production choke",
  metering: "Chemical-injection metering valve",
  annulus_master: "Annulus master valve (AMV)",
  annulus_wing: "Annulus wing valve (AWV)",
  crossover: "Crossover valve (annulus ↔ production bore)",
  injection_isolation: "Chemical-injection isolation valve",
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
  if (selection.type !== "element") return null;
  const el = state.elements.find((e) => e.id === selection.id);
  if (!el) return null;
  switch (el.kind) {
    case "valve":
    case "choke":
      return <RestrictionDetail v={el as RestrictionSnapshot} state={state} prefs={prefs} onCommand={onCommand} />;
    case "pipe":
      return <PipeDetail p={el as PipeSnapshot} state={state} prefs={prefs} />;
    case "check_valve":
      return <CheckValveDetail v={el as CheckValveSnapshot} state={state} prefs={prefs} />;
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
          <TagHeading state={state} tag={v.tag} />
          <div className="text-muted">{SUBTYPE[v.subtype] ?? v.name}</div>
        </div>
        <Badge tone={tone} data-testid="valve-state">{VALVE_LABEL[vis]}</Badge>
      </div>

      <Section title="Position">
        <PositionBar actual={v.position_pct} commanded={v.commanded_pct} />
        <Row label="Actual position" value={fmt(v.position_pct, 1)} unit="%" />
        <Row label="Commanded position" value={fmt(v.commanded_pct, 1)} unit="%" />
        <Row
          label="Actuation"
          value={v.moving ? `${v.phase === "delay" ? "control-signal dead time" : "travelling"}, ~${fmt(v.time_to_target_s, 0)} s sim time` : "at commanded position"}
          mono={false}
        />
        <Row label="Full-stroke time (open)" value={fmt(v.full_stroke_time_s, 0)} unit="s" />
        {v.close_stroke_time_s !== undefined && v.close_stroke_time_s !== v.full_stroke_time_s && (
          <Row label="Full-stroke time (close)" value={fmt(v.close_stroke_time_s, 0)} unit="s" />
        )}
        {!!v.actuation_delay_s && <Row label="Actuation dead time" value={fmt(v.actuation_delay_s, 1)} unit="s" />}
        {v.nominal_stroke_time_s != null && <Row label="Datasheet stroke time" value={fmt(v.nominal_stroke_time_s, 0)} unit="s" />}
        {!!v.seat_leak_area_mm2 && (
          <Row label="Seat leak path (closed)" value={v.seat_leak_area_mm2.toExponential(1)} unit="mm² Cd·A" />
        )}
        {v.leaking && <p className="mt-1 text-fault">Closed, but fluid is passing the seat (leak flow {fmt((v.flow_m3s ?? 0) * 6e7, 3)} mL/min).</p>}
        {state.mode === "dynamic" && v.moving && (
          <p className="mt-1 text-[12.5px] text-info">
            The valve's travel and the process response are separate: pressures and flows keep evolving after the valve reaches its position.
          </p>
        )}
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
        <p className="py-1 text-[12.5px] text-dim">{v.characteristic_description}</p>
        {v.cv_max !== undefined && <Row label="Cv at 100 %" value={fmt(v.cv_max, 1)} unit="US gpm/psi½" />}
        {v.cv_max !== undefined && <Row label="Rangeability" value={fmt(v.rangeability, 0)} />}
        {v.loss_coefficient_open !== undefined && <Row label="K fully open" value={fmt(v.loss_coefficient_open, 2)} />}
        {v.bore_diameter_m !== undefined && <Row label="Bore" value={fmt(v.bore_diameter_m * 1000, 0)} unit="mm" />}
        <Row label="Effective Cd·A now" value={(v.capacity_m2 * 1e6).toFixed(2)} unit="mm²" />
        <p className="mt-1 text-[12.5px] text-dim">Generic characteristic for training — not manufacturer performance data.</p>
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
      {p.wave_speed_m_s !== undefined && (
        <Section title="Dynamic model">
          <Row label="Inlet / outlet flow" value={`${fmt(flowFromM3s(p.inlet_flow_m3s ?? 0, prefs.flowUnit), 1)} / ${fmt(flowFromM3s(p.outlet_flow_m3s ?? 0, prefs.flowUnit), 1)}`} unit={FLOW_LABEL[prefs.flowUnit]} />
          <Row label="Internal volume" value={fmt(p.volume_m3, 2)} unit="m³" />
          <Row label="Capacitance V(c_f + c_wall)" value={fmt((p.capacitance_m3_per_pa ?? 0) * 1e5 * 1000, 2)} unit="L/bar" />
          <Row label="Pressure-wave speed a" value={fmt(p.wave_speed_m_s, 0)} unit="m/s" />
          <Row label="Acoustic transit L/a" value={fmt(p.acoustic_transit_s, 1)} unit="s" />
          <Row label="Residence time V/Q (plug flow)" value={formatDuration(p.residence_time_s)} mono={false} />
          <Row label="Line-pack change since t=0" value={fmt((p.linepack_change_m3 ?? 0) * 1000, 1)} unit="L" />
          <Row label="Hydraulic segments" value={fmt(p.segments, 0)} />
          {p.pressure_profile && <Profile p={p} prefs={prefs} />}
          <p className="mt-1 text-[12.5px] text-dim">
            Pressure changes travel at ~a (waves) but the fluid itself — and any chemical in it — moves at the flow velocity. These are separate effects.
          </p>
        </Section>
      )}
    </div>
  );
}

function Profile({ p, prefs }: { p: PipeSnapshot; prefs: DisplayPrefs }) {
  const pts = p.pressure_profile ?? [];
  if (pts.length < 2) return null;
  const W = 300;
  const H = 60;
  const ys = pts.map((q) => pressureFromPa(q.p_pa, prefs.pressureRef));
  const lo = Math.min(...ys);
  const hi = Math.max(...ys);
  const span = Math.max(hi - lo, 0.05);
  const d = pts.map((q, i) => `${i ? "L" : "M"}${((q.x_m / p.length_m) * W).toFixed(1)},${(H - 6 - ((ys[i] - lo) / span) * (H - 12)).toFixed(1)}`).join(" ");
  return (
    <div className="mt-1">
      <div className="text-[11.5px] text-dim">Pressure along the pipe (hydraulic nodes)</div>
      <svg viewBox={`0 0 ${W} ${H}`} className="h-[60px] w-full rounded-md bg-bg">
        <path d={d} fill="none" stroke="#38bdf8" strokeWidth={1.5} />
        {pts.map((q, i) => (
          <circle key={i} cx={(q.x_m / p.length_m) * W} cy={H - 6 - ((ys[i] - lo) / span) * (H - 12)} r={1.6} fill="#38bdf8" />
        ))}
        <text x={3} y={9} fontSize={8} fill="#7d8da1" className="num">
          {fmt(hi, 1)}
        </text>
        <text x={3} y={H - 1} fontSize={8} fill="#7d8da1" className="num">
          {fmt(lo, 1)} {prefs.pressureRef}
        </text>
      </svg>
    </div>
  );
}

function CheckValveDetail({ v, state, prefs }: { v: CheckValveSnapshot; state: SimulationState; prefs: DisplayPrefs }) {
  return (
    <div className="p-3" data-testid="component-panel">
      <div className="flex items-start justify-between gap-2">
        <div>
          <TagHeading state={state} tag={v.tag} />
          <div className="text-muted">{v.name}</div>
        </div>
        <Badge tone={v.state === "flowing" ? "ok" : "neutral"}>{v.state === "flowing" ? "OPEN (flowing)" : v.state === "closed" ? "CLOSED" : "NO FLOW"}</Badge>
      </div>
      <Section title="Non-return valve">
        <Row label="Cracking pressure" value={fmt(paToBarDelta(v.cracking_pressure_pa), 2)} unit="bar" />
        <Row label="Upstream pressure" value={<P pa={nodePressure(state, v.from)} prefs={prefs} />} unit={prefs.pressureRef} />
        <Row label="Downstream pressure" value={<P pa={nodePressure(state, v.to)} prefs={prefs} />} unit={prefs.pressureRef} />
        <Row label="Flow" value={fmt((v.flow_m3s ?? 0) * 3.6e6, 2)} unit="L/h" />
      </Section>
      <p className="mt-2 text-[12.5px] text-dim">Opens when the forward differential exceeds the cracking pressure; reverse flow is blocked. Not operable.</p>
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
      <p className="mt-2 text-[12.5px] text-dim">Reservoir pressure is a fixed boundary (no depletion in Release 1). Change it under Conditions.</p>
    </div>
  );
}

function InstrumentDetail({ inst, state, prefs }: { inst: InstrumentSnapshot; state: SimulationState; prefs: DisplayPrefs }) {
  const u = inst.display_unit;
  const m = instrumentDisplay(inst.type, inst.value_si, prefs, u);
  const pv = instrumentDisplay(inst.type, inst.pv_si, prefs, u);
  const lo = instrumentDisplay(inst.type, inst.range_min_si, prefs, u);
  const hi = instrumentDisplay(inst.type, inst.range_max_si, prefs, u);
  const unit = inst.type === "concentration" ? (u ?? "ppm") : unitLabel(inst.type, prefs);
  const node = (id: string | null) => state.nodes.find((n) => n.id === id)?.name ?? id ?? "—";
  const where =
    inst.type === "differential_pressure"
      ? `${node(inst.high_node)} → ${node(inst.low_node)}`
      : inst.element
        ? `${state.elements.find((e) => e.id === inst.element)?.name ?? inst.element}${inst.distance_m != null ? ` @ ${fmt(inst.distance_m, 0)} m` : ""}`
        : node(inst.node);
  const r = inst.response;
  return (
    <div className="p-3" data-testid="component-panel">
      <div className="flex items-start justify-between">
        <div>
          <TagHeading state={state} tag={inst.tag} />
          <div className="text-muted">{inst.description}</div>
        </div>
        <Badge tone={inst.status === "GOOD" ? "ok" : inst.status.startsWith("OUT") ? "warn" : "fault"}>{inst.status.replace(/_/g, " ")}</Badge>
      </div>
      <Section title="Measurement (simulated)">
        <Row label="Displayed measurement" value={fmt(m.value, m.digits)} unit={unit} />
        <Row label="Model process value" value={fmt(pv.value, pv.digits)} unit={unit} />
        <Row label="Calibrated range" value={`${fmt(lo.value, 0)} – ${fmt(hi.value, 0)}`} unit={unit} />
        <Row label="Location" value={where} mono={false} />
        <Row label="Type" value={inst.type.replace("_", " ")} mono={false} />
      </Section>
      {r && state.mode === "dynamic" ? (
        <Section title="Transmitter response (dynamic model)">
          <Row label="Sensor time constant" value={fmt(r.time_constant_s, 1)} unit="s" />
          <Row label="Update interval" value={r.update_interval_s > 0 ? fmt(r.update_interval_s, 0) : "every solver step"} unit={r.update_interval_s > 0 ? "s" : undefined} mono={r.update_interval_s > 0} />
          <Row
            label="Resolution"
            value={r.resolution_si > 0 ? fmt(instrumentDisplay(inst.type === "pressure" ? "differential_pressure" : inst.type, r.resolution_si, prefs, u).value, 4) : "none"}
          />
          <p className="mt-1 text-[12.5px] text-dim">
            Sensor dynamics act ON TOP of the modelled process dynamics: the process value above already evolves in time; the displayed measurement
            additionally lags, holds and quantises it.
          </p>
        </Section>
      ) : (
        <p className="mt-2 text-[12.5px] text-dim">
          {inst.status === "NOT_MODELLED"
            ? "This transmitter is on a subsystem that the quasi-steady model does not represent. Switch to the dynamic model."
            : "Quasi-steady transmitters are ideal: measurement equals the model value within range, saturates at range limits outside it, and shows no value when the model cannot determine one."}
        </p>
      )}
    </div>
  );
}
