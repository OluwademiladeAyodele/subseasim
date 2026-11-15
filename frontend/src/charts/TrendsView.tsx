/**
 * Trend charts of samples produced by the backend engine, keyed by
 * SIMULATION time. No interpolation, smoothing or synthetic points: display
 * downsampling only drops samples. Dashed lines are the backend's
 * steady-state reference (where the production path would settle);
 * vertical markers are logged events.
 *
 * Two views:
 *  - the board: every condition as a large card with a live readout strip;
 *  - the focus view (expand / double-click): one condition near full screen
 *    with time zoom (brush), cursor readout, statistics over the visible
 *    range, the events in range and CSV export, for studying a response.
 */
import { ChevronLeft, ChevronRight, Download, LayoutGrid, Maximize2, Rows3, X, ZoomOut } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Brush, CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Button, Segmented } from "@/components/ui/primitives";
import { EVENT_STYLE } from "@/dashboard/EventLog";
import { concFromFraction, type DisplayPrefs, FLOW_LABEL, flowFromM3s, formatSimTime, kToC, paToBarDelta, pressureFromPa } from "@/lib/units";
import { cn } from "@/lib/utils";
import type { InstrumentSnapshot, Sample, SimEvent, SimulationState } from "@/types/simulation";

// Categorical palette validated for contrast on white (>= 3:1 for lines)
const PALETTE = ["#2563eb", "#ea580c", "#16a34a", "#9333ea", "#dc2626", "#0891b2", "#ca8a04", "#db2777", "#4f46e5", "#65a30d"];
const MAX_POINTS_BOARD = 600;
const MAX_POINTS_FOCUS = 2000;
const LAYOUT_KEY = "subseasim.trends.layout";

const EVENT_COLOR: Record<string, string> = {
  operation: "#0369a1",
  valve: "#16a34a",
  chemical: "#c026d3",
  integrity: "#d97706",
  process: "#64748b",
  boundary: "#2563eb",
  fluid: "#2563eb",
};
const MARKED = new Set(Object.keys(EVENT_COLOR));

interface Series {
  key: string;
  label: string;
  /** Longer description (instrument description) for the focus view. */
  description?: string;
  convert: (v: number) => number;
  color?: string;
  refKey?: string;
}

interface Group {
  id: string;
  title: string;
  unit: string;
  series: Series[];
  defaults: string[];
}

type Row = Record<string, number | null>;

function buildGroups(state: SimulationState, prefs: DisplayPrefs): Group[] {
  const prodNodes = new Set(state.elements.filter((e) => !e.branch).flatMap((e) => [e.from, e.to]));
  const prodElements = new Set(state.elements.filter((e) => !e.branch).map((e) => e.id));
  const chemTx = new Set((state.chemicals ?? []).flatMap((c) => [c.pressure_transmitter, c.flow_transmitter]).filter(Boolean) as string[]);
  const chemColor = Object.fromEntries((state.chemical_config ?? []).map((c) => [c.id, c.color]));
  const isProd = (i: InstrumentSnapshot) => (i.node ? prodNodes.has(i.node) : i.element ? prodElements.has(i.element) : true);
  const inst = (type: string) => state.instruments.filter((i) => i.type === type);
  const dynamic = state.mode === "dynamic";
  const pSeries = (i: InstrumentSnapshot): Series => ({
    key: `inst:${i.tag}`,
    label: i.tag,
    description: i.description,
    convert: (v: number) => pressureFromPa(v, prefs.pressureRef),
    refKey: dynamic && isProd(i) && i.node ? `ref:${i.tag}` : undefined,
  });
  const pressures = inst("pressure");
  const pProd = pressures.filter(isProd).map(pSeries);
  const pAnn = pressures.filter((i) => !isProd(i) && !chemTx.has(i.tag)).map(pSeries);
  const pInj = pressures.filter((i) => chemTx.has(i.tag)).map(pSeries);
  const dp = inst("differential_pressure").map((i) => ({ key: `inst:${i.tag}`, label: i.tag, description: i.description, convert: paToBarDelta }));
  const t = inst("temperature").map((i) => ({ key: `inst:${i.tag}`, label: i.tag, description: i.description, convert: kToC }));
  const flows = inst("flow");
  const fProd = flows.filter((i) => !chemTx.has(i.tag)).map((i) => ({
    key: `inst:${i.tag}`,
    label: i.tag,
    description: i.description,
    convert: (v: number) => flowFromM3s(v, prefs.flowUnit),
    refKey: dynamic ? `ref:${i.tag}` : undefined,
  }));
  const fInj = flows
    .filter((i) => chemTx.has(i.tag))
    .map((i) => {
      const chem = (state.chemicals ?? []).find((c) => c.flow_transmitter === i.tag);
      return { key: `inst:${i.tag}`, label: i.tag, description: i.description, convert: (v: number) => v * 3.6e6, color: chem ? chemColor[chem.id] : undefined };
    });
  const conc = (unit: "ppm" | "vol%") =>
    inst("concentration")
      .filter((i) => (i.display_unit ?? "ppm") === unit)
      .map((i) => ({
        key: `inst:${i.tag}`,
        label: i.tag,
        description: i.description,
        convert: (v: number) => concFromFraction(v, unit),
        color: chemColor[i.chemical ?? ""],
      }));
  const valves = state.elements.flatMap((e) =>
    e.kind === "valve" || e.kind === "choke"
      ? [
          { key: `pos:${e.tag}`, label: `${e.tag}`, description: `${e.name} — actual position`, convert: (v: number) => v },
          { key: `cmd:${e.tag}`, label: `${e.tag} cmd`, description: `${e.name} — commanded position`, convert: (v: number) => v },
        ]
      : [],
  );
  const cVol = conc("vol%");
  const cPpm = conc("ppm");
  return [
    { id: "pressure", title: "Production pressure", unit: prefs.pressureRef, series: pProd, defaults: pProd.slice(0, 4).map((s) => s.key) },
    { id: "annulus", title: "Annulus pressure", unit: prefs.pressureRef, series: pAnn, defaults: pAnn.map((s) => s.key) },
    { id: "temperature", title: "Temperature", unit: "°C", series: t, defaults: t.slice(0, 5).map((s) => s.key) },
    {
      id: "flow",
      title: "Production flow",
      unit: FLOW_LABEL[prefs.flowUnit],
      series: [{ key: "q", label: "Model Q", description: "Flowline flow from the model", convert: (v: number) => flowFromM3s(v, prefs.flowUnit) }, ...fProd],
      defaults: fProd.length ? fProd.map((s) => s.key) : ["q"],
    },
    { id: "inj_flow", title: "Chemical injection flow", unit: "L/h", series: fInj, defaults: fInj.map((s) => s.key) },
    { id: "conc_vol", title: "Chemical concentration", unit: "vol%", series: cVol, defaults: cVol.map((s) => s.key) },
    { id: "conc_ppm", title: "Chemical concentration", unit: "ppm", series: cPpm, defaults: cPpm.map((s) => s.key) },
    { id: "inj_p", title: "Injection pressure", unit: prefs.pressureRef, series: pInj, defaults: pInj.map((s) => s.key) },
    { id: "dp", title: "Differential pressure", unit: "bar", series: dp, defaults: dp.map((s) => s.key) },
    {
      id: "position",
      title: "Valve & choke position",
      unit: "%",
      series: valves,
      defaults: valves.filter((s) => s.key.startsWith("pos:")).slice(0, 6).map((s) => s.key),
    },
  ].filter((g) => g.series.length > 0);
}

function downsample(samples: Sample[], max: number): Sample[] {
  if (samples.length <= max) return samples;
  const stride = Math.ceil(samples.length / max);
  const out = samples.filter((_, i) => i % stride === 0);
  if (out[out.length - 1] !== samples[samples.length - 1]) out.push(samples[samples.length - 1]);
  return out;
}

function toRows(samples: Sample[], group: Group, max: number): Row[] {
  return downsample(samples, max).map((s) => {
    const row: Row = { t: s.t };
    for (const ser of group.series) {
      const v = s[ser.key];
      row[ser.key] = v === null || v === undefined ? null : ser.convert(v);
      if (ser.refKey) {
        const r = s[ser.refKey];
        row[ser.refKey] = r === null || r === undefined ? null : ser.convert(r);
      }
    }
    return row;
  });
}

const colorOf = (g: Group, s: Series) => s.color ?? PALETTE[g.series.indexOf(s) % PALETTE.length];

/** Value formatting precision from the span of the data shown. */
function precision(rows: Row[], keys: string[]): number {
  let lo = Infinity;
  let hi = -Infinity;
  for (const row of rows)
    for (const k of keys) {
      const v = row[k];
      if (v !== null && v !== undefined && Number.isFinite(v)) {
        lo = Math.min(lo, v);
        hi = Math.max(hi, v);
      }
    }
  const span = hi - lo;
  const mag = Math.max(Math.abs(lo), Math.abs(hi));
  if (!Number.isFinite(span)) return 1;
  if (span < 0.05) return mag < 10 ? 4 : 3;
  return span < 0.5 ? 3 : span < 5 ? 2 : span < 100 ? 1 : 0;
}

interface Stats {
  current: number | null;
  min: number | null;
  tMin: number | null;
  max: number | null;
  tMax: number | null;
  mean: number | null;
  change: number | null;
  ratePerMin: number | null;
}

function statsOf(rows: Row[], key: string): Stats {
  let min = Infinity;
  let max = -Infinity;
  let tMin: number | null = null;
  let tMax: number | null = null;
  let sum = 0;
  let n = 0;
  let first: number | null = null;
  let last: number | null = null;
  for (const r of rows) {
    const v = r[key];
    if (v === null || v === undefined || !Number.isFinite(v)) continue;
    if (first === null) first = v;
    last = v;
    sum += v;
    n++;
    if (v < min) {
      min = v;
      tMin = r.t ?? null;
    }
    if (v > max) {
      max = v;
      tMax = r.t ?? null;
    }
  }
  // rate at the end of the range: least-squares slope over the last ~10 % of points
  const tail = rows.filter((r) => r[key] !== null && r[key] !== undefined).slice(-Math.max(3, Math.ceil(n * 0.1)));
  let ratePerMin: number | null = null;
  if (tail.length >= 2) {
    const ts = tail.map((r) => r.t as number);
    const vs = tail.map((r) => r[key] as number);
    const mt = ts.reduce((a, b) => a + b, 0) / ts.length;
    const mv = vs.reduce((a, b) => a + b, 0) / vs.length;
    let num = 0;
    let den = 0;
    for (let i = 0; i < ts.length; i++) {
      num += (ts[i] - mt) * (vs[i] - mv);
      den += (ts[i] - mt) ** 2;
    }
    ratePerMin = den > 0 ? (num / den) * 60 : null;
  }
  return {
    current: last,
    min: n ? min : null,
    tMin,
    max: n ? max : null,
    tMax,
    mean: n ? sum / n : null,
    change: first !== null && last !== null ? last - first : null,
    ratePerMin,
  };
}

const f = (v: number | null | undefined, d: number) => (v === null || v === undefined || !Number.isFinite(v) ? "—" : v.toFixed(d));
const signed = (v: number | null | undefined, d: number) => (v === null || v === undefined || !Number.isFinite(v) ? "—" : `${v >= 0 ? "+" : ""}${v.toFixed(d)}`);

const TOOLTIP_STYLE = {
  background: "#ffffff",
  border: "1px solid #e3e8ef",
  borderRadius: 10,
  boxShadow: "0 12px 32px -8px rgb(15 23 42 / .18)",
  fontSize: 12.5,
  fontFamily: "JetBrains Mono Variable, monospace",
};

/** The chart body, shared by the board card and the focus view. */
function Plot({
  group,
  rows,
  selected,
  events,
  showRef,
  digits,
  large,
  brush,
  onBrush,
  onHover,
  highlightEvent,
}: {
  group: Group;
  rows: Row[];
  selected: string[];
  events: SimEvent[];
  showRef: boolean;
  digits: number;
  large?: boolean;
  brush?: { start: number; end: number };
  onBrush?: (b: { start: number; end: number }) => void;
  onHover?: (i: number | null) => void;
  highlightEvent?: number | null;
}) {
  const t0 = rows.length ? (rows[0].t ?? 0) : 0;
  const t1 = rows.length ? (rows[rows.length - 1].t ?? 0) : 0;
  const marks = events.filter((e) => MARKED.has(e.category) && e.sim_time_s >= t0 && e.sim_time_s <= t1).slice(large ? -80 : -30);
  const fs = large ? 13 : 12;
  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart
        data={rows}
        margin={{ top: 10, right: large ? 24 : 16, bottom: large ? 4 : 0, left: 4 }}
        onMouseMove={(s: { activeTooltipIndex?: number }) => onHover?.(s?.activeTooltipIndex ?? null)}
        onMouseLeave={() => onHover?.(null)}
      >
        <CartesianGrid stroke="#eef1f5" vertical={!!large} />
        <XAxis
          dataKey="t"
          type="number"
          domain={["dataMin", "dataMax"]}
          tickFormatter={formatSimTime}
          stroke="#94a3b8"
          tick={{ fill: "#475569" }}
          tickLine={false}
          fontSize={fs}
          minTickGap={large ? 70 : 56}
          allowDataOverflow
        />
        <YAxis
          stroke="#94a3b8"
          tick={{ fill: "#475569" }}
          tickLine={false}
          axisLine={false}
          fontSize={fs}
          width={large ? 72 : 64}
          domain={["auto", "auto"]}
          tickFormatter={(v: number) => v.toFixed(digits)}
          label={large ? { value: group.unit, angle: -90, position: "insideLeft", fill: "#64748b", fontSize: 12, dx: 8 } : undefined}
        />
        <Tooltip
          contentStyle={TOOLTIP_STYLE}
          labelStyle={{ color: "#0f172a", fontWeight: 600, marginBottom: 4 }}
          labelFormatter={(t: number) => `sim time ${formatSimTime(t)}`}
          formatter={(v: number, name: string) => {
            const ref = group.series.find((s) => s.refKey === name);
            const label = ref ? `${ref.label} steady-state` : (group.series.find((s) => s.key === name)?.label ?? name);
            return [Number.isFinite(v) ? `${v.toFixed(digits)} ${group.unit}` : "—", label];
          }}
          cursor={{ stroke: "#0b1d4a", strokeOpacity: 0.35, strokeWidth: 1 }}
        />
        {marks.map((e) => (
          <ReferenceLine
            key={e.id}
            x={e.sim_time_s}
            stroke={EVENT_COLOR[e.category]}
            strokeOpacity={highlightEvent === e.id ? 1 : 0.55}
            strokeWidth={highlightEvent === e.id ? 2 : 1}
            strokeDasharray={highlightEvent === e.id ? undefined : "3 3"}
            ifOverflow="hidden"
          />
        ))}
        {group.series.map((s) =>
          selected.includes(s.key) ? (
            <Line
              key={s.key}
              dataKey={s.key}
              stroke={colorOf(group, s)}
              dot={false}
              activeDot={{ r: large ? 4.5 : 3.5, strokeWidth: 0 }}
              strokeWidth={large ? 2.2 : 1.9}
              isAnimationActive={false}
              connectNulls={false}
              type="linear"
              strokeDasharray={s.key.startsWith("cmd:") ? "5 4" : undefined}
            />
          ) : null,
        )}
        {showRef &&
          group.series.map((s) =>
            selected.includes(s.key) && s.refKey ? (
              <Line
                key={s.refKey}
                dataKey={s.refKey}
                stroke={colorOf(group, s)}
                strokeOpacity={0.5}
                dot={false}
                activeDot={false}
                strokeWidth={1.2}
                isAnimationActive={false}
                strokeDasharray="7 5"
                type="stepAfter"
              />
            ) : null,
          )}
        {brush && onBrush && rows.length > 2 && (
          <Brush
            dataKey="t"
            height={34}
            stroke="#0b1d4a"
            fill="#f8fafc"
            travellerWidth={10}
            startIndex={brush.start}
            endIndex={brush.end}
            tickFormatter={formatSimTime}
            onChange={(r: { startIndex?: number; endIndex?: number }) => {
              if (r.startIndex !== undefined && r.endIndex !== undefined) onBrush({ start: r.startIndex, end: r.endIndex });
            }}
          />
        )}
      </LineChart>
    </ResponsiveContainer>
  );
}

function SeriesChips({ group, selected, onToggle, size = "sm" }: { group: Group; selected: string[]; onToggle: (k: string) => void; size?: "sm" | "md" }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {group.series.map((s) => {
        const on = selected.includes(s.key);
        const c = colorOf(group, s);
        return (
          <button
            key={s.key}
            type="button"
            aria-pressed={on}
            title={s.description}
            onClick={() => onToggle(s.key)}
            className={cn(
              "num pressable flex items-center gap-1.5 rounded-full border font-medium",
              size === "md" ? "px-2.5 py-1 text-[12.5px]" : "px-2 py-0.5 text-[12px]",
            )}
            style={{ borderColor: on ? c : "var(--color-line)", color: on ? c : "var(--color-dim)", background: on ? `${c}12` : undefined }}
          >
            <span className="h-2 w-2 rounded-full" style={{ background: on ? c : "var(--color-line-strong)" }} />
            {s.label}
          </button>
        );
      })}
    </div>
  );
}

/** Board card: one condition, large, with a live readout strip. */
function TrendCard({
  group,
  samples,
  selected,
  onToggle,
  events,
  showRef,
  height,
  onExpand,
}: {
  group: Group;
  samples: Sample[];
  selected: string[];
  onToggle: (k: string) => void;
  events: SimEvent[];
  showRef: boolean;
  height: number;
  onExpand: () => void;
}) {
  const rows = useMemo(() => toRows(samples, group, MAX_POINTS_BOARD), [samples, group]);
  const digits = useMemo(() => precision(rows, selected), [rows, selected]);
  const last = rows[rows.length - 1];
  const empty = rows.length < 2;
  const active = group.series.filter((s) => selected.includes(s.key));

  return (
    <section className="flex flex-col overflow-hidden rounded-xl border border-line bg-panel shadow-[var(--shadow-card)]" data-testid={`chart-${group.id}`}>
      <header className="flex flex-wrap items-start justify-between gap-3 border-b border-line px-4 py-3">
        <div className="min-w-0">
          <h2 className="t-heading text-[16px] text-fg">
            {group.title} <span className="font-normal text-dim">· {group.unit}</span>
          </h2>
          <div className="mt-2">
            <SeriesChips group={group} selected={selected} onToggle={onToggle} />
          </div>
        </div>
        <Button size="sm" variant="subtle" onClick={onExpand} aria-label={`Expand ${group.title} ${group.unit}`} data-testid={`expand-${group.id}`} title="Expand to study (or double-click the chart)">
          <Maximize2 size={14} /> Expand
        </Button>
      </header>
      {/* live readout: the latest value of every plotted series */}
      {active.length > 0 && (
        <div className="flex flex-wrap gap-x-6 gap-y-1 border-b border-line/70 bg-panel-2/60 px-4 py-2">
          {active.map((s) => (
            <div key={s.key} className="flex items-baseline gap-1.5" title={s.description}>
              <span className="h-2 w-2 translate-y-[-1px] rounded-full" style={{ background: colorOf(group, s) }} />
              <span className="num text-[12px] text-muted">{s.label}</span>
              <span className="num text-[16px] font-semibold text-fg">{f(last?.[s.key] as number | null, digits)}</span>
            </div>
          ))}
        </div>
      )}
      <div className="relative px-1 pt-1" style={{ height }} onDoubleClick={onExpand}>
        {empty && (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-panel/85 text-[13.5px] text-dim">
            Start the simulation to record this trend against simulated time.
          </div>
        )}
        <Plot group={group} rows={rows} selected={selected} events={events} showRef={showRef} digits={digits} />
      </div>
    </section>
  );
}

/** Focus view: one condition near full screen, for studying a response. */
function TrendFocus({
  group,
  samples,
  selected,
  onToggle,
  events,
  showRef,
  onShowRef,
  dynamic,
  onClose,
  onPrev,
  onNext,
  position,
}: {
  group: Group;
  samples: Sample[];
  selected: string[];
  onToggle: (k: string) => void;
  events: SimEvent[];
  showRef: boolean;
  onShowRef: (v: boolean) => void;
  dynamic: boolean;
  onClose: () => void;
  onPrev: () => void;
  onNext: () => void;
  position: string;
}) {
  const rows = useMemo(() => toRows(samples, group, MAX_POINTS_FOCUS), [samples, group]);
  // time zoom as a SIMULATED-TIME range (stable while new data streams in and
  // the downsampling stride changes); null = whole range, following live data
  const [zoom, setZoom] = useState<{ ta: number; tb: number } | null>(null);
  const [hover, setHover] = useState<number | null>(null);
  const [hlEvent, setHlEvent] = useState<number | null>(null);
  useEffect(() => {
    setZoom(null);
    setHover(null);
    setHlEvent(null);
  }, [group.id]);
  const last = Math.max(0, rows.length - 1);
  const b = useMemo(() => {
    if (!zoom || rows.length < 3) return { start: 0, end: last };
    let start = rows.findIndex((r) => (r.t ?? 0) >= zoom.ta);
    let end = rows.findIndex((r) => (r.t ?? 0) > zoom.tb) - 1;
    if (start < 0) start = 0;
    if (end < 0) end = last;
    return { start, end: Math.max(end, Math.min(start + 1, last)) };
  }, [zoom, rows, last]);
  const setBrush = useCallback(
    (r: { start: number; end: number }) => {
      if (r.start <= 0 && r.end >= last) setZoom(null);
      else setZoom({ ta: rows[r.start]?.t ?? 0, tb: rows[r.end]?.t ?? 0 });
    },
    [rows, last],
  );
  const range = useMemo(() => rows.slice(b.start, b.end + 1), [rows, b.start, b.end]);
  const digits = useMemo(() => precision(range, selected), [range, selected]);
  const active = group.series.filter((s) => selected.includes(s.key));
  const stats = useMemo(() => Object.fromEntries(active.map((s) => [s.key, statsOf(range, s.key)])), [range, active]);
  const t0 = range[0]?.t ?? 0;
  const t1 = range[range.length - 1]?.t ?? 0;
  const inRange = events.filter((e) => MARKED.has(e.category) && e.sim_time_s >= t0 && e.sim_time_s <= t1);
  const cursor = hover !== null ? rows[hover] : null;
  const dialog = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null;
    dialog.current?.focus();
    return () => prev?.focus?.();
  }, []);

  const zoomToEvent = (e: SimEvent) => {
    setHlEvent(e.id);
    if (rows.length < 3) return;
    const span = Math.max(((rows[rows.length - 1].t ?? 0) - (rows[0].t ?? 0)) * 0.08, 120);
    setZoom({ ta: e.sim_time_s - span, tb: e.sim_time_s + span * 2 });
  };

  const downloadCsv = () => {
    const keys = active.flatMap((s) => (s.refKey && showRef ? [s.key, s.refKey] : [s.key]));
    const head = ["sim_time_s", "sim_time", ...keys.map((k) => {
      const s = group.series.find((x) => x.key === k || x.refKey === k)!;
      return `${s.label}${k === s.refKey ? " steady-state" : ""} [${group.unit}]`;
    })];
    const src = toRows(samples, group, Number.MAX_SAFE_INTEGER).filter((r) => (r.t ?? 0) >= t0 && (r.t ?? 0) <= t1);
    const lines = [head.join(","), ...src.map((r) => [r.t, formatSimTime(r.t ?? 0), ...keys.map((k) => (r[k] ?? ""))].join(","))];
    const blob = new Blob([lines.join("\n")], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `subseasim-${group.id}-${Math.round(t0)}-${Math.round(t1)}s.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  // Portal to <body>: an ancestor with a transform animation (page entrance)
  // would otherwise become the containing block of this fixed overlay.
  return createPortal(
    <div className="fixed inset-0 z-50 flex" role="dialog" aria-modal="true" aria-label={`${group.title} trend`} data-testid="trend-focus">
      <div className="scrim-in absolute inset-0 bg-navy/30 backdrop-blur-[2px]" onClick={onClose} />
      <div
        ref={dialog}
        tabIndex={-1}
        onKeyDown={(e) => {
          if (e.key === "Escape") onClose();
          else if (e.key === "ArrowLeft" && !(e.target as HTMLElement).closest("input")) onPrev();
          else if (e.key === "ArrowRight" && !(e.target as HTMLElement).closest("input")) onNext();
        }}
        className="palette-in relative m-3 flex min-w-0 flex-1 flex-col overflow-hidden rounded-2xl border border-line bg-panel shadow-[var(--shadow-float)] outline-none md:m-5"
      >
        {/* header */}
        <header className="flex flex-wrap items-center gap-3 border-b border-line px-5 py-3">
          <div className="flex items-center gap-1">
            <Button size="icon" variant="ghost" onClick={onPrev} aria-label="Previous chart" title="Previous chart (←)">
              <ChevronLeft size={18} />
            </Button>
            <Button size="icon" variant="ghost" onClick={onNext} aria-label="Next chart" title="Next chart (→)">
              <ChevronRight size={18} />
            </Button>
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-xs text-dim">Trend {position}</div>
            <h2 className="t-title truncate">
              {group.title} <span className="font-normal text-dim">· {group.unit}</span>
            </h2>
          </div>
          <div className="num text-[12.5px] text-muted">
            {formatSimTime(t0)} → {formatSimTime(t1)} <span className="text-dim">({((t1 - t0) / 60).toFixed(1)} min)</span>
          </div>
          {zoom && (
            <Button size="sm" variant="subtle" onClick={() => setZoom(null)} title="Show the whole recorded range and follow live data">
              <ZoomOut size={14} /> Full range
            </Button>
          )}
          {dynamic && active.some((s) => s.refKey) && (
            <label className="flex items-center gap-1.5 text-[13px] text-muted">
              <input type="checkbox" checked={showRef} onChange={(e) => onShowRef(e.target.checked)} className="h-4 w-4 accent-[#0b1d4a]" />
              Steady-state reference
            </label>
          )}
          <Button size="sm" onClick={downloadCsv} disabled={range.length < 2} title="Download the visible range as CSV">
            <Download size={14} /> CSV
          </Button>
          <Button size="icon" variant="ghost" onClick={onClose} aria-label="Close expanded trend" title="Close (Esc)">
            <X size={18} />
          </Button>
        </header>

        <div className="border-b border-line px-5 py-2.5">
          <SeriesChips group={group} selected={selected} onToggle={onToggle} size="md" />
        </div>

        <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
          {/* chart */}
          <div className="relative min-h-[360px] min-w-0 flex-1 px-2 pb-2 pt-3">
            {rows.length < 2 && (
              <div className="absolute inset-0 z-10 flex items-center justify-center text-[14px] text-dim">
                Start the simulation to record this trend against simulated time.
              </div>
            )}
            <Plot
              group={group}
              rows={rows}
              selected={selected}
              events={events}
              showRef={showRef && dynamic}
              digits={digits}
              large
              brush={b}
              onBrush={setBrush}
              onHover={setHover}
              highlightEvent={hlEvent}
            />
            <p className="pointer-events-none absolute right-8 top-0 text-[11.5px] text-dim">Drag the handles under the chart to zoom in time · click an event to zoom to it</p>
          </div>

          {/* analysis side panel */}
          <aside className="flex w-full shrink-0 flex-col overflow-y-auto border-t border-line bg-panel-2/50 lg:w-[420px] lg:border-l lg:border-t-0">
            <section className="px-4 py-3">
              <div className="t-eyebrow mb-2">{cursor ? `At cursor · ${formatSimTime(cursor.t ?? 0)}` : "Latest values"}</div>
              <ul className="space-y-1.5">
                {active.map((s) => {
                  const v = (cursor ?? range[range.length - 1])?.[s.key];
                  const ref = s.refKey ? (cursor ?? range[range.length - 1])?.[s.refKey] : null;
                  return (
                    <li key={s.key} className="flex items-baseline justify-between gap-2">
                      <span className="flex min-w-0 items-center gap-2">
                        <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: colorOf(group, s) }} />
                        <span className="min-w-0">
                          <span className="num block text-[13px] font-semibold text-fg">{s.label}</span>
                          {s.description && <span className="block truncate text-[11.5px] text-dim">{s.description}</span>}
                        </span>
                      </span>
                      <span className="text-right">
                        <span className="num block text-[18px] font-semibold text-fg">{f(v as number | null, digits)}</span>
                        {showRef && dynamic && ref !== null && ref !== undefined && (
                          <span className="num block text-[11.5px] text-dim">steady state {f(ref, digits)}</span>
                        )}
                      </span>
                    </li>
                  );
                })}
              </ul>
            </section>

            <section className="border-t border-line px-4 py-3">
              <div className="t-eyebrow mb-2">Statistics · visible range</div>
              <div className="overflow-x-auto">
                <table className="num w-full text-[12.5px]">
                  <thead>
                    <tr className="text-left text-[11px] font-sans font-semibold text-dim">
                      <th className="pb-1 pr-2 font-semibold">Series</th>
                      <th className="pb-1 pr-2 text-right font-semibold">Min</th>
                      <th className="pb-1 pr-2 text-right font-semibold">Max</th>
                      <th className="pb-1 pr-2 text-right font-semibold">Mean</th>
                      <th className="pb-1 pr-2 text-right font-semibold" title="Last minus first value in the range">Δ</th>
                      <th className="pb-1 text-right font-semibold" title="Least-squares slope over the last 10 % of the range">Rate/min</th>
                    </tr>
                  </thead>
                  <tbody>
                    {active.map((s) => {
                      const st = stats[s.key];
                      return (
                        <tr key={s.key} className="border-t border-line/60">
                          <td className="py-1 pr-2">
                            <span className="flex items-center gap-1.5">
                              <span className="h-2 w-2 rounded-full" style={{ background: colorOf(group, s) }} />
                              {s.label}
                            </span>
                          </td>
                          <td className="py-1 pr-2 text-right" title={st.tMin !== null ? `at ${formatSimTime(st.tMin)}` : undefined}>{f(st.min, digits)}</td>
                          <td className="py-1 pr-2 text-right" title={st.tMax !== null ? `at ${formatSimTime(st.tMax)}` : undefined}>{f(st.max, digits)}</td>
                          <td className="py-1 pr-2 text-right">{f(st.mean, digits)}</td>
                          <td className={cn("py-1 pr-2 text-right", (st.change ?? 0) > 0 ? "text-[#c2410c]" : (st.change ?? 0) < 0 ? "text-info" : "")}>{signed(st.change, digits)}</td>
                          <td className="py-1 text-right">{signed(st.ratePerMin, Math.min(digits + 1, 4))}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <p className="mt-2 text-[11.5px] leading-snug text-dim">Hover min / max to see when they occurred. Values in {group.unit}; rate in {group.unit}/min.</p>
            </section>

            <section className="border-t border-line px-4 py-3">
              <div className="t-eyebrow mb-2">Events in range ({inRange.length})</div>
              {inRange.length === 0 ? (
                <p className="text-[12.5px] text-dim">No operations or system events in this time range.</p>
              ) : (
                <ol className="space-y-1">
                  {[...inRange].reverse().map((e) => (
                    <li key={e.id}>
                      <button
                        type="button"
                        onClick={() => zoomToEvent(e)}
                        className={cn(
                          "w-full rounded-lg px-2 py-1.5 text-left hover:bg-panel",
                          hlEvent === e.id && "bg-panel shadow-[var(--shadow-card)]",
                        )}
                        title="Zoom the chart to this event"
                      >
                        <span className="flex items-center gap-2 text-[11.5px] text-dim">
                          <span className="h-2 w-2 rounded-full" style={{ background: EVENT_COLOR[e.category] }} />
                          <span className="num">{formatSimTime(e.sim_time_s)}</span>
                          <span>{EVENT_STYLE[e.category]?.label ?? e.category}</span>
                        </span>
                        <span className="mt-0.5 line-clamp-2 block text-[12.5px] leading-snug text-fg">{e.message}</span>
                      </button>
                    </li>
                  ))}
                </ol>
              )}
            </section>
          </aside>
        </div>
      </div>
    </div>,
    document.body,
  );
}

const WINDOWS: [string, number][] = [
  ["All", Infinity],
  ["4 h", 4 * 3600],
  ["1 h", 3600],
  ["15 min", 900],
];

type BoardLayout = "large" | "grid";

export function TrendsView({ state, samples, prefs, events = [] }: { state: SimulationState; samples: Sample[]; prefs: DisplayPrefs; events?: SimEvent[] }) {
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const groups = useMemo(() => buildGroups(state, prefs), [state.instruments.length, state.scenario.id, state.mode, prefs.pressureRef, prefs.flowUnit]);
  const [selected, setSelected] = useState<Record<string, string[]>>({});
  const [win, setWin] = useState(Infinity);
  const [showRef, setShowRef] = useState(true);
  const [focus, setFocus] = useState<string | null>(null);
  const [layout, setLayoutState] = useState<BoardLayout>(() => {
    try {
      return (localStorage.getItem(LAYOUT_KEY) as BoardLayout) || "large";
    } catch {
      return "large";
    }
  });
  const setLayout = (l: BoardLayout) => {
    setLayoutState(l);
    try {
      localStorage.setItem(LAYOUT_KEY, l);
    } catch {
      /* ignore */
    }
  };
  const visible = useMemo(() => {
    if (!Number.isFinite(win) || !samples.length) return samples;
    const tEnd = samples[samples.length - 1].t ?? 0;
    return samples.filter((s) => (s.t ?? 0) >= tEnd - win);
  }, [samples, win]);
  const sel = (g: Group) => selected[g.id] ?? g.defaults;
  const toggle = (g: Group, k: string) =>
    setSelected((s) => {
      const cur = s[g.id] ?? g.defaults;
      return { ...s, [g.id]: cur.includes(k) ? cur.filter((x) => x !== k) : [...cur, k] };
    });
  const dynamic = state.mode === "dynamic";
  const fi = groups.findIndex((g) => g.id === focus);
  const step = useCallback(
    (d: number) => setFocus((cur) => {
      const i = groups.findIndex((g) => g.id === cur);
      return groups[(i + d + groups.length) % groups.length].id;
    }),
    [groups],
  );

  return (
    <div className="flex h-full flex-col" data-testid="trends">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 border-b border-line px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="text-[12.5px] font-medium text-muted">Time window</span>
          <Segmented<number> label="Time window" size="sm" value={win} onChange={setWin} options={WINDOWS.map(([l, w]) => ({ value: w, label: l }))} />
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[12.5px] font-medium text-muted">Layout</span>
          <Segmented<BoardLayout>
            label="Chart layout"
            size="sm"
            value={layout}
            onChange={setLayout}
            options={[
              { value: "large", label: (<span className="flex items-center gap-1.5"><Rows3 size={13} /> Large</span>), title: "One large chart per row" },
              { value: "grid", label: (<span className="flex items-center gap-1.5"><LayoutGrid size={13} /> Grid</span>), title: "Two charts per row" },
            ]}
          />
        </div>
        {dynamic && (
          <label className="flex items-center gap-1.5 text-[12.5px] text-muted">
            <input type="checkbox" checked={showRef} onChange={(e) => setShowRef(e.target.checked)} className="h-4 w-4 accent-[#0b1d4a]" />
            Steady-state reference (dashed)
          </label>
        )}
        <span className="ml-auto flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px] text-dim">
          <span className="font-medium text-muted">Event markers:</span>
          {Object.entries(EVENT_COLOR)
            .filter(([k]) => k !== "fluid")
            .map(([k, c]) => (
              <span key={k} className="flex items-center gap-1">
                <span className="inline-block h-3 w-0 border-l-2 border-dashed" style={{ borderColor: c }} />
                {EVENT_STYLE[k]?.label ?? k}
              </span>
            ))}
        </span>
      </div>
      <div className={cn("grid gap-4 p-4", layout === "grid" ? "grid-cols-1 xl:grid-cols-2" : "grid-cols-1")}>
        {groups.map((g) => (
          <TrendCard
            key={g.id}
            group={g}
            samples={visible}
            selected={sel(g)}
            onToggle={(k) => toggle(g, k)}
            events={events}
            showRef={showRef && dynamic}
            height={layout === "large" ? 420 : 320}
            onExpand={() => setFocus(g.id)}
          />
        ))}
        <p className="col-span-full px-1 text-[12px] text-dim">
          {samples.length} samples recorded by the simulation engine against simulation time. Double-click a chart or press Expand to study it in detail.{" "}
          {dynamic
            ? "Dynamic model: every trend is the time integration of the mass, momentum and energy balances; sample spacing grows with simulation speed."
            : "Quasi-steady model: hydraulic responses are instantaneous; temperature trends are transient."}
        </p>
      </div>
      {fi >= 0 && (
        <TrendFocus
          group={groups[fi]}
          samples={visible}
          selected={sel(groups[fi])}
          onToggle={(k) => toggle(groups[fi], k)}
          events={events}
          showRef={showRef}
          onShowRef={setShowRef}
          dynamic={dynamic}
          onClose={() => setFocus(null)}
          onPrev={() => step(-1)}
          onNext={() => step(1)}
          position={`${fi + 1} of ${groups.length}`}
        />
      )}
    </div>
  );
}
