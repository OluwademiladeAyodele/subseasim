/**
 * Trend charts of samples produced by the backend engine. No interpolation,
 * smoothing or synthetic points: display downsampling only drops samples.
 */
import { useMemo, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { type DisplayPrefs, FLOW_LABEL, flowFromM3s, formatSimTime, kToC, paToBarDelta, pressureFromPa } from "@/lib/units";
import type { Sample, SimulationState } from "@/types/simulation";

const PALETTE = ["#38bdf8", "#f59e0b", "#22c55e", "#e879f9", "#f87171", "#a3e635", "#2dd4bf", "#fb923c", "#c4b5fd", "#facc15"];
const MAX_POINTS = 600;

interface Series {
  key: string;
  label: string;
  convert: (v: number) => number;
}

interface Group {
  id: string;
  title: string;
  unit: string;
  series: Series[];
  defaults: string[];
}

function buildGroups(state: SimulationState, prefs: DisplayPrefs): Group[] {
  const inst = (type: string) => state.instruments.filter((i) => i.type === type);
  const p = inst("pressure").map((i) => ({ key: `inst:${i.tag}`, label: i.tag, convert: (v: number) => pressureFromPa(v, prefs.pressureRef) }));
  const dp = inst("differential_pressure").map((i) => ({ key: `inst:${i.tag}`, label: i.tag, convert: paToBarDelta }));
  const t = inst("temperature").map((i) => ({ key: `inst:${i.tag}`, label: i.tag, convert: kToC }));
  const f = inst("flow").map((i) => ({ key: `inst:${i.tag}`, label: i.tag, convert: (v: number) => flowFromM3s(v, prefs.flowUnit) }));
  const valves = state.elements.flatMap((e) =>
    e.kind === "valve" || e.kind === "choke"
      ? [
          { key: `pos:${e.tag}`, label: `${e.tag} actual`, convert: (v: number) => v },
          { key: `cmd:${e.tag}`, label: `${e.tag} cmd`, convert: (v: number) => v },
        ]
      : [],
  );
  return [
    { id: "pressure", title: "Pressure", unit: prefs.pressureRef, series: p, defaults: p.slice(0, 4).map((s) => s.key) },
    { id: "dp", title: "Differential pressure", unit: "bar", series: dp, defaults: dp.map((s) => s.key) },
    { id: "temperature", title: "Temperature", unit: "°C", series: t, defaults: t.map((s) => s.key) },
    {
      id: "flow",
      title: "Flow rate",
      unit: FLOW_LABEL[prefs.flowUnit],
      series: [{ key: "q", label: "Model Q", convert: (v: number) => flowFromM3s(v, prefs.flowUnit) }, ...f],
      defaults: f.length ? f.map((s) => s.key) : ["q"],
    },
    {
      id: "position",
      title: "Valve / choke position",
      unit: "%",
      series: valves,
      defaults: valves.filter((s) => s.key.startsWith("pos:")).map((s) => s.key),
    },
  ].filter((g) => g.series.length > 0);
}

function downsample(samples: Sample[]): Sample[] {
  if (samples.length <= MAX_POINTS) return samples;
  const stride = Math.ceil(samples.length / MAX_POINTS);
  const out = samples.filter((_, i) => i % stride === 0);
  if (out[out.length - 1] !== samples[samples.length - 1]) out.push(samples[samples.length - 1]);
  return out;
}

function TrendChart({ group, samples, selected, onToggle }: { group: Group; samples: Sample[]; selected: string[]; onToggle: (k: string) => void }) {
  const data = useMemo(() => {
    const pts = downsample(samples);
    return pts.map((s) => {
      const row: Record<string, number | null> = { t: s.t };
      for (const ser of group.series) {
        const v = s[ser.key];
        row[ser.key] = v === null || v === undefined ? null : ser.convert(v);
      }
      return row;
    });
  }, [samples, group]);

  return (
    <div className="flex min-h-[210px] flex-col border border-line bg-panel" data-testid={`chart-${group.id}`}>
      <div className="flex flex-wrap items-center gap-1 border-b border-line bg-panel-2 px-2 py-1">
        <span className="mr-2 text-[10px] font-bold uppercase tracking-[0.12em] text-muted">
          {group.title} <span className="text-dim">[{group.unit}]</span>
        </span>
        {group.series.map((s, i) => {
          const on = selected.includes(s.key);
          const color = PALETTE[i % PALETTE.length];
          return (
            <button
              key={s.key}
              type="button"
              aria-pressed={on}
              onClick={() => onToggle(s.key)}
              className="num rounded-sm border px-1.5 text-[10px]"
              style={{ borderColor: on ? color : "var(--color-line)", color: on ? color : "var(--color-dim)" }}
            >
              {s.label}
            </button>
          );
        })}
      </div>
      <div className="min-h-0 flex-1 px-1 pt-1">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 4, right: 12, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="#18222e" />
            <XAxis dataKey="t" type="number" domain={["dataMin", "dataMax"]} tickFormatter={formatSimTime} stroke="#56667a" fontSize={10} minTickGap={40} />
            <YAxis stroke="#56667a" fontSize={10} width={52} domain={["auto", "auto"]} tickFormatter={(v: number) => (Math.abs(v) >= 1000 ? v.toFixed(0) : v.toFixed(1))} />
            <Tooltip
              contentStyle={{ background: "#0d141c", border: "1px solid #2f4357", fontSize: 11 }}
              labelFormatter={(t: number) => `sim time ${formatSimTime(t)}`}
              formatter={(v: number, name: string) => [Number.isFinite(v) ? v.toFixed(2) : "—", group.series.find((s) => s.key === name)?.label ?? name]}
            />
            {group.series.map((s, i) =>
              selected.includes(s.key) ? (
                <Line
                  key={s.key}
                  dataKey={s.key}
                  stroke={PALETTE[i % PALETTE.length]}
                  dot={false}
                  strokeWidth={1.6}
                  isAnimationActive={false}
                  connectNulls={false}
                  type="linear"
                  strokeDasharray={s.key.startsWith("cmd:") ? "4 3" : undefined}
                />
              ) : null,
            )}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export function TrendsView({ state, samples, prefs }: { state: SimulationState; samples: Sample[]; prefs: DisplayPrefs }) {
  const groups = useMemo(() => buildGroups(state, prefs), [state.instruments.length, state.scenario.id, prefs.pressureRef, prefs.flowUnit]); // eslint-disable-line react-hooks/exhaustive-deps
  const [selected, setSelected] = useState<Record<string, string[]>>({});
  const sel = (g: Group) => selected[g.id] ?? g.defaults;
  const toggle = (g: Group, k: string) =>
    setSelected((s) => {
      const cur = s[g.id] ?? g.defaults;
      return { ...s, [g.id]: cur.includes(k) ? cur.filter((x) => x !== k) : [...cur, k] };
    });
  return (
    <div className="grid h-full auto-rows-[minmax(210px,1fr)] grid-cols-1 gap-1.5 p-1.5 xl:grid-cols-2" data-testid="trends">
      {groups.map((g) => (
        <TrendChart key={g.id} group={g} samples={samples} selected={sel(g)} onToggle={(k) => toggle(g, k)} />
      ))}
      <p className="col-span-full px-1 text-[10px] text-dim">
        {samples.length} samples recorded by the simulation engine (sim-time interval ≥ 1 s). Hydraulic responses are quasi-steady; temperature trends are
        transient.
      </p>
    </div>
  );
}
