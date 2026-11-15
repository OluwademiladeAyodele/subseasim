/**
 * Configuration-driven SVG schematic. Every drawn component comes from the
 * scenario topology (elements, nodes) + layout (coordinates). Nothing about a
 * specific tree arrangement is hard-coded here.
 *
 * Everything animated or coloured is derived from backend values: flow-dash
 * speed from the calculated velocity, chemical bands from the calculated
 * concentration profile, trend arrows from the calculated dP/dt. The
 * frontend never computes process values.
 */
import { memo, useEffect, useRef, useState } from "react";

import { COLORS, pipeColor, SCH, valveVisual, VALVE_LABEL, zoneColor } from "@/lib/stateColors";
import { instrumentDisplay, type DisplayPrefs, fmt, pressureFromPa } from "@/lib/units";
import type {
  CheckValveSnapshot,
  ElementSnapshot,
  InstrumentSnapshot,
  Layout,
  LayoutPoint,
  PipeSnapshot,
  RestrictionSnapshot,
  SimulationState,
} from "@/types/simulation";

import { arrowPositions, pathD, pointAlong, subPath } from "./geometry";

export type Selection = { type: "element"; id: string } | { type: "instrument"; tag: string } | null;

interface Props {
  state: SimulationState;
  layout: Layout;
  selection: Selection;
  onSelect: (s: Selection) => void;
  prefs: DisplayPrefs;
}

function elementPoints(e: ElementSnapshot, layout: Layout): LayoutPoint[] | null {
  const a = layout.nodes[e.from];
  const b = layout.nodes[e.to];
  if (!a || !b) return null;
  return [a, ...(layout.waypoints[e.id] ?? []), b];
}

const VALVE_COLOR = {
  open: COLORS.open,
  closed: COLORS.closed,
  partial: COLORS.partial,
  moving: COLORS.moving,
  fault: COLORS.fault,
} as const;

function ValveSymbol({
  v,
  at,
  selected,
  onClick,
  small,
}: {
  v: RestrictionSnapshot;
  at: { x: number; y: number; angle: number };
  selected: boolean;
  onClick: () => void;
  small: boolean;
}) {
  const vis = valveVisual(v);
  const color = VALVE_COLOR[vis];
  const s = small ? (v.kind === "choke" ? 9 : 8) : v.kind === "choke" ? 13 : 11;
  const h = s * 0.75;
  const vertical = Math.abs(Math.abs(at.angle) - 90) < 20;
  const fill = vis === "closed" || vis === "open" ? color : COLORS.panel;
  const label = v.kind === "choke" ? `${fmt(v.position_pct, small ? 0 : 1)} %` : VALUE_SHORT(vis);
  const fs = small ? 9 : 11;
  const tagPos = vertical ? { x: at.x + s + 6, y: at.y - 2, anchor: "start" as const } : { x: at.x, y: at.y - s - 7, anchor: "middle" as const };
  const statePos = vertical ? { x: at.x + s + 6, y: at.y + 9, anchor: "start" as const } : { x: at.x, y: at.y + s + 13, anchor: "middle" as const };

  return (
    <g
      role="button"
      tabIndex={0}
      aria-label={`${v.tag} ${v.name}`}
      data-testid={`valve-${v.tag}`}
      onClick={onClick}
      onKeyDown={(ev) => (ev.key === "Enter" || ev.key === " ") && onClick()}
      className="cursor-pointer outline-none"
    >
      <rect x={at.x - s - 6} y={at.y - s - 6} width={2 * s + 12} height={2 * s + 12} fill="transparent" />
      {selected && (
        <rect x={at.x - s - 5} y={at.y - s - 5} width={2 * s + 10} height={2 * s + 10} fill="none" stroke={COLORS.accent} strokeWidth={1.5} strokeDasharray="3 2" />
      )}
      <g transform={`translate(${at.x} ${at.y}) rotate(${at.angle})`} className={vis === "moving" ? "moving-blink" : undefined}>
        <polygon points={`${-s},${-h} ${-s},${h} 0,0`} fill={fill} stroke={color} strokeWidth={small ? 1.5 : 2} strokeLinejoin="round" />
        <polygon points={`${s},${-h} ${s},${h} 0,0`} fill={fill} stroke={color} strokeWidth={small ? 1.5 : 2} strokeLinejoin="round" />
        {v.kind === "choke" && (
          <>
            <line x1={-s} y1={s} x2={s - 2} y2={-s + 2} stroke={color} strokeWidth={1.6} />
            <polygon points={`${s},${-s} ${s - 6},${-s + 2} ${s - 2},${-s + 6}`} fill={color} />
            {vis === "partial" && <rect x={-2.5} y={-2.5} width={5} height={5} fill={color} />}
          </>
        )}
        {vis === "fault" && (
          <>
            <line x1={-s} y1={-s} x2={s} y2={s} stroke={COLORS.fault} strokeWidth={2} />
            <line x1={-s} y1={s} x2={s} y2={-s} stroke={COLORS.fault} strokeWidth={2} />
          </>
        )}
      </g>
      {v.leaking && (
        <circle cx={at.x} cy={at.y} r={s + 3} fill="none" stroke={COLORS.fault} strokeWidth={1.5} className="leak-pulse" aria-label="seat leakage" />
      )}
      <text x={tagPos.x} y={tagPos.y} textAnchor={tagPos.anchor} fontSize={fs} fontWeight={700} fill={COLORS.fg}>
        {v.tag}
      </text>
      <text x={statePos.x} y={statePos.y} textAnchor={statePos.anchor} fontSize={fs - 1} fontWeight={700} fill={color} className="num">
        {label}
        {v.moving ? (v.phase === "delay" ? " (signal)" : ` → ${fmt(v.commanded_pct, 0)} %`) : ""}
      </text>
    </g>
  );
}

function CheckValveSymbol({ v, at, selected, onClick }: { v: CheckValveSnapshot; at: { x: number; y: number; angle: number }; selected: boolean; onClick: () => void }) {
  const open = v.state === "flowing";
  const color = open ? COLORS.open : v.state === "not_modelled" ? COLORS.static : COLORS.muted;
  const vertical = Math.abs(Math.abs(at.angle) - 90) < 20;
  return (
    <g role="button" tabIndex={0} aria-label={`${v.tag} ${v.name}`} data-testid={`check-${v.tag}`} onClick={onClick} className="cursor-pointer outline-none">
      <rect x={at.x - 12} y={at.y - 12} width={24} height={24} fill="transparent" />
      {selected && <rect x={at.x - 11} y={at.y - 11} width={22} height={22} fill="none" stroke={COLORS.accent} strokeDasharray="3 2" />}
      <g transform={`translate(${at.x} ${at.y}) rotate(${at.angle})`}>
        <polygon points="-7,-6 -7,6 5,0" fill={open ? color : COLORS.panel} stroke={color} strokeWidth={1.5} />
        <line x1={6} y1={-7} x2={6} y2={7} stroke={color} strokeWidth={2} />
      </g>
      <text x={vertical ? at.x + 12 : at.x} y={vertical ? at.y + 3 : at.y - 11} textAnchor={vertical ? "start" : "middle"} fontSize={8.5} fill={COLORS.muted}>
        {v.tag}
      </text>
    </g>
  );
}

function VALUE_SHORT(vis: ReturnType<typeof valveVisual>): string {
  return vis === "partial" ? "PARTIAL" : VALVE_LABEL[vis];
}

/** Rate thresholds for the trend arrow [SI units per second]. */
const RATE_EPS: Record<string, number> = { pressure: 2, temperature: 2e-5 };

function InstrumentBubble({
  inst,
  at,
  target,
  selected,
  onClick,
  prefs,
  rate,
  steady,
  litresPerHour = false,
}: {
  inst: InstrumentSnapshot;
  at: LayoutPoint;
  target: LayoutPoint | null;
  selected: boolean;
  onClick: () => void;
  prefs: DisplayPrefs;
  rate: number | null;
  steady: number | null;
  litresPerHour?: boolean;
}) {
  const [prefix, num] = inst.tag.split("-");
  const d = litresPerHour && inst.value_si !== null
    ? { value: inst.value_si * 3.6e6, unit: "L/h", digits: inst.value_si * 3.6e6 < 10 ? 2 : 0 }
    : instrumentDisplay(inst.type, inst.value_si, prefs, inst.display_unit);
  const bad = inst.status === "BAD" || inst.status === "UNDETERMINED";
  const nm = inst.status === "NOT_MODELLED";
  const oor = inst.status.startsWith("OUT_OF_RANGE");
  const ring = bad ? COLORS.fault : nm ? COLORS.static : oor ? COLORS.partial : selected ? COLORS.accent : COLORS.muted;
  const text = nm ? "N/M" : bad ? (inst.status === "BAD" ? "BAD" : "UNDET") : `${fmt(d.value, d.digits)}`;
  const eps = RATE_EPS[inst.type] ?? Infinity;
  const arrow = rate === null || Math.abs(rate) < eps ? null : rate > 0 ? "▲" : "▼";
  const fast = rate !== null && Math.abs(rate) > 50 * eps;
  return (
    <>
    {/* leader line outside the clickable group: the target is the bubble + value box only */}
    {target && <line x1={at.x} y1={at.y} x2={target.x} y2={target.y} stroke={COLORS.muted} strokeWidth={1} strokeDasharray="2 3" pointerEvents="none" />}
    <g role="button" tabIndex={0} aria-label={`${inst.tag} ${inst.description}`} data-testid={`inst-${inst.tag}`} onClick={onClick}
      onKeyDown={(ev) => (ev.key === "Enter" || ev.key === " ") && onClick()} className="cursor-pointer outline-none">
      {/* generous invisible hit area (bubble + value box) */}
      <rect x={at.x - 36} y={at.y - 17} width={72} height={52} fill="transparent" />
      {fast && <circle cx={at.x} cy={at.y} r={18} fill="none" stroke={COLORS.accent} strokeWidth={1} className="halo" />}
      <circle cx={at.x} cy={at.y} r={15} fill={SCH.bubble} stroke={ring} strokeWidth={selected ? 2 : 1.3} />
      <line x1={at.x - 15} y1={at.y} x2={at.x + 15} y2={at.y} stroke={ring} strokeWidth={0.8} />
      <text x={at.x} y={at.y - 3} textAnchor="middle" fontSize={8.5} fontWeight={700} fill={COLORS.fg}>
        {prefix}
      </text>
      <text x={at.x} y={at.y + 10} textAnchor="middle" fontSize={8.5} fill={COLORS.fg}>
        {num}
      </text>
      <rect x={at.x - 34} y={at.y + 18} width={68} height={15} rx={2} fill={SCH.valueBox} stroke={oor ? COLORS.partial : COLORS.line} strokeWidth={1} />
      <text x={at.x} y={at.y + 29} textAnchor="middle" fontSize={10} className="num" fill={bad ? COLORS.fault : nm ? COLORS.static : oor ? COLORS.partial : SCH.valueText}>
        {text} <tspan fill={COLORS.muted} fontSize={8}>{bad || nm ? "" : d.unit}</tspan>
        {arrow && (
          <tspan fill={arrow === "▲" ? COLORS.rise : COLORS.fall} fontSize={8}>
            {" "}
            {arrow}
          </tspan>
        )}
      </text>
      {steady !== null && (
        <text x={at.x} y={at.y + 43} textAnchor="middle" fontSize={8.5} className="num" fill={COLORS.ref} data-testid={`ref-${inst.tag}`}>
          → {fmt(steady, 1)} ss
        </text>
      )}
    </g>
    </>
  );
}

function AnalyserStack({
  items,
  at,
  target,
  prefs,
  colors,
  onSelect,
  selected,
}: {
  items: InstrumentSnapshot[];
  at: LayoutPoint;
  target: LayoutPoint | null;
  prefs: DisplayPrefs;
  colors: Record<string, string>;
  onSelect: (tag: string) => void;
  selected: string | null;
}) {
  const w = 128;
  const rh = 15;
  return (
    <g data-testid="analyser-stack">
      {target && <line x1={at.x} y1={at.y} x2={target.x} y2={target.y} stroke={COLORS.muted} strokeWidth={1} strokeDasharray="2 3" pointerEvents="none" />}
      <rect x={at.x - w / 2} y={at.y - 4} width={w} height={items.length * rh + 8} rx={3} fill={SCH.bg} filter="url(#soft)" stroke={COLORS.line} />
      {items.map((i, k) => {
        const d = instrumentDisplay(i.type, i.value_si, prefs, i.display_unit);
        const y = at.y + k * rh + 8;
        const c = colors[i.chemical ?? ""] ?? COLORS.fg;
        const nm = i.status === "NOT_MODELLED";
        return (
          <g key={i.tag} role="button" tabIndex={0} data-testid={`inst-${i.tag}`} aria-label={`${i.tag} ${i.description}`} className="cursor-pointer"
            onClick={() => onSelect(i.tag)}>
            <rect x={at.x - w / 2 + 2} y={y - 7} width={w - 4} height={rh - 1} fill={selected === i.tag ? SCH.selected : "transparent"} />
            <circle cx={at.x - w / 2 + 9} cy={y} r={3.5} fill={c} opacity={(i.value_si ?? 0) > 0 ? 1 : 0.35} />
            <text x={at.x - w / 2 + 17} y={y + 3.5} fontSize={9} fontWeight={700} fill={COLORS.fg}>
              {i.tag}
            </text>
            <text x={at.x + w / 2 - 6} y={y + 3.5} fontSize={9.5} textAnchor="end" className="num" fill={nm ? COLORS.static : SCH.valueText}>
              {nm ? "N/M" : fmt(d.value, d.digits)} <tspan fill={COLORS.muted} fontSize={7.5}>{nm ? "" : d.unit}</tspan>
            </text>
          </g>
        );
      })}
    </g>
  );
}

/** Flow-dash animation duration from the calculated velocity (visual only). */
function dashDuration(v: number): number {
  const s = Math.abs(v);
  return Math.max(0.35, Math.min(12, 1.2 / Math.max(0.02, Math.sqrt(s))));
}

function ChemicalBands({ p, pts, colors, refs }: { p: PipeSnapshot; pts: LayoutPoint[]; colors: Record<string, string>; refs: Record<string, number> }) {
  if (!p.profile) return null;
  const L = p.length_m;
  const xs = p.profile.x_m;
  // ignore numerically negligible traces (< 0.1 ppm): opacity is relative to the reference
  const chems = Object.entries(p.profile.c).filter(([id, c]) => (refs[id] ?? 0) > 1e-7 && c.some((v) => v > Math.max(1e-7, 1e-3 * refs[id])));
  if (!chems.length) return null;
  return (
    <g pointerEvents="none">
      {chems.map(([id, c], k) => {
        const width = Math.max(2, 5.5 - k * 1.3);
        return (
          <g key={id}>
            {xs.map((x, i) => {
              const x0 = i === 0 ? 0 : (xs[i - 1] + x) / 2;
              const x1 = i === xs.length - 1 ? L : (x + xs[i + 1]) / 2;
              const op = Math.min(1, c[i] / refs[id]);
              if (op < 0.02) return null;
              return (
                <path key={i} d={pathD(subPath(pts, x0 / L, x1 / L))} stroke={colors[id] ?? "#fff"} strokeWidth={width} strokeOpacity={0.15 + 0.85 * op}
                  fill="none" strokeLinecap="butt" />
              );
            })}
          </g>
        );
      })}
    </g>
  );
}

function TreeSchematicInner({ state, layout, selection, onSelect, prefs }: Props) {
  const svgRef = useRef<SVGSVGElement>(null);
  const drag = useRef<{ sx: number; sy: number; box: { x: number; y: number; w: number; h: number } } | null>(null);
  const [vb, setVb] = useState<{ x: number; y: number; w: number; h: number } | null>(null);
  useEffect(() => setVb(null), [layout.width, layout.height]);
  const nodeState = Object.fromEntries(state.nodes.map((n) => [n.id, n.state]));
  const nodeById = Object.fromEntries(state.nodes.map((n) => [n.id, n]));
  const selEl = selection?.type === "element" ? selection.id : null;
  const selInst = selection?.type === "instrument" ? selection.tag : null;
  const dynamic = state.mode === "dynamic";
  const elementById = Object.fromEntries(state.elements.map((e) => [e.id, e]));
  const chemColors: Record<string, string> = Object.fromEntries((state.chemical_config ?? []).map((c) => [c.id, c.color]));
  const chemTx = new Set((state.chemicals ?? []).map((c) => c.flow_transmitter).filter(Boolean) as string[]);
  // reference concentration per chemical for band opacity: current fully-mixed value (or the max seen in any profile)
  const refs: Record<string, number> = {};
  for (const c of state.chemicals ?? []) refs[c.id] = c.fully_mixed_concentration;
  for (const e of state.elements)
    if (e.kind === "pipe" && (e as PipeSnapshot).profile)
      for (const [id, arr] of Object.entries((e as PipeSnapshot).profile!.c)) refs[id] = Math.max(refs[id] ?? 0, ...arr);

  const instTarget = (i: InstrumentSnapshot): LayoutPoint | null => {
    if (i.element) {
      const el = elementById[i.element];
      const pts = el ? elementPoints(el, layout) : null;
      if (!pts) return null;
      if (el.kind === "pipe" && i.distance_m != null) return pointAlong(pts, i.distance_m / (el as PipeSnapshot).length_m);
      return pointAlong(pts, 0.5);
    }
    if (i.node) return layout.nodes[i.node] ?? null;
    const a = i.high_node ? layout.nodes[i.high_node] : null;
    const b = i.low_node ? layout.nodes[i.low_node] : null;
    return a && b ? { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 } : null;
  };

  const instRate = (i: InstrumentSnapshot): number | null => {
    if (!dynamic) return null;
    if (i.type === "pressure" && i.node) return nodeById[i.node]?.rate_pa_s ?? null;
    return null;
  };
  const instSteady = (i: InstrumentSnapshot): number | null => {
    if (!dynamic || i.type !== "pressure" || !i.node || i.value_si === null) return null;
    const ref = state.steady_reference?.node_pressure_pa[i.node];
    if (ref === undefined || ref === null) return null;
    return Math.abs(ref - i.value_si) > 0.5e5 ? pressureFromPa(ref, prefs.pressureRef) : null;
  };

  // analyser stacks grouped by layout position
  const stacks = new Map<string, InstrumentSnapshot[]>();
  for (const i of state.instruments) {
    if (i.type !== "concentration") continue;
    const at = layout.instruments[i.tag];
    if (!at) continue;
    const k = `${at.x},${at.y}`;
    stacks.set(k, [...(stacks.get(k) ?? []), i]);
  }

  const full = { x: 0, y: 0, w: layout.width, h: layout.height };
  const box = vb ?? full;
  const toSvg = (cx: number, cy: number) => {
    const svg = svgRef.current;
    const m = svg?.getScreenCTM();
    if (!svg || !m) return null;
    const p = new DOMPoint(cx, cy).matrixTransform(m.inverse());
    return { x: p.x, y: p.y };
  };
  const zoom = (factor: number, cx?: number, cy?: number) => {
    const c = cx !== undefined && cy !== undefined ? toSvg(cx, cy) : { x: box.x + box.w / 2, y: box.y + box.h / 2 };
    if (!c) return;
    const w = Math.min(full.w, Math.max(full.w / 6, box.w * factor));
    const h = (w / full.w) * full.h;
    const x = Math.min(full.w - w, Math.max(0, c.x - ((c.x - box.x) / box.w) * w));
    const y = Math.min(full.h - h, Math.max(0, c.y - ((c.y - box.y) / box.h) * h));
    setVb(w >= full.w ? null : { x, y, w, h });
  };
  const onPointerDown = (ev: React.PointerEvent<SVGSVGElement>) => {
    const tgt = ev.target as Element;
    if (!vb || tgt.closest("[role=button]")) return;
    const p = toSvg(ev.clientX, ev.clientY);
    if (p) drag.current = { sx: p.x, sy: p.y, box: vb };
  };
  const onPointerMove = (ev: React.PointerEvent<SVGSVGElement>) => {
    const d = drag.current;
    if (!d) return;
    const p = toSvg(ev.clientX, ev.clientY);
    if (!p) return;
    // pointer position is measured in the CURRENT viewBox: shift by the delta
    const dx = p.x - d.sx;
    const dy = p.y - d.sy;
    const x = Math.min(full.w - d.box.w, Math.max(0, d.box.x - dx));
    const y = Math.min(full.h - d.box.h, Math.max(0, d.box.y - dy));
    setVb({ ...d.box, x, y });
  };

  return (
    <div className="relative h-full w-full">
    <svg
      ref={svgRef}
      viewBox={`${box.x} ${box.y} ${box.w} ${box.h}`}
      className={`h-full w-full select-none ${vb ? "cursor-grab active:cursor-grabbing" : ""}`}
      preserveAspectRatio="xMidYMid meet"
      role="img"
      aria-label="Subsea production system schematic (simulated)"
      onClick={(ev) => ev.target === ev.currentTarget && onSelect(null)}
      onWheel={(ev) => zoom(ev.deltaY > 0 ? 1.15 : 1 / 1.15, ev.clientX, ev.clientY)}
      onDoubleClick={(ev) => !(ev.target as Element).closest("[role=button]") && setVb(null)}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={() => (drag.current = null)}
      onPointerLeave={() => (drag.current = null)}
    >
      <defs>
        <pattern id="hatch" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <line x1="0" y1="0" x2="0" y2="8" stroke={SCH.seabed} strokeWidth="2" />
        </pattern>
        <pattern id="grid" width="20" height="20" patternUnits="userSpaceOnUse">
          <path d="M 20 0 L 0 0 0 20" fill="none" stroke={SCH.grid} strokeWidth="1" />
        </pattern>
        <linearGradient id="sea" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={SCH.bg} stopOpacity="1" />
          <stop offset="1" stopColor={SCH.bg2} stopOpacity="1" />
        </linearGradient>
        <filter id="soft" x="-10%" y="-10%" width="120%" height="130%">
          <feDropShadow dx="0" dy="1" stdDeviation="1.6" floodColor="#0f172a" floodOpacity="0.10" />
        </filter>
        <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="2.2" result="b" />
          <feMerge>
            <feMergeNode in="b" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>
      <rect width={layout.width} height={layout.height} fill="url(#sea)" onClick={() => onSelect(null)} />
      <rect width={layout.width} height={layout.height} fill="url(#grid)" onClick={() => onSelect(null)} />

      {/* annotations */}
      {layout.annotations.map((a, i) => {
        if (a.type === "rect")
          return (
            <g key={i} pointerEvents="none">
              <rect x={a.x} y={a.y} width={a.w} height={a.h} rx={4} fill={SCH.boxFill} fillOpacity={0.6} stroke={COLORS.line} strokeWidth={1.2} strokeDasharray="6 3" />
              <text
                x={a.label_position === "bottom" ? (a.x ?? 0) + (a.w ?? 0) - 6 : (a.x ?? 0) + 6}
                y={a.label_position === "bottom" ? (a.y ?? 0) + (a.h ?? 0) - 6 : (a.y ?? 0) + 13}
                textAnchor={a.label_position === "bottom" ? "end" : "start"}
                fontSize={9.5} fontWeight={700} fill={COLORS.muted} letterSpacing={1.2}>
                {a.label}
              </text>
            </g>
          );
        if (a.type === "line")
          return (
            <g key={i} pointerEvents="none">
              <line x1={a.x1} y1={a.y1} x2={a.x2} y2={a.y2} stroke={SCH.seabed} strokeWidth={1.5} />
              <rect x={a.x1} y={a.y1} width={(a.x2 ?? 0) - (a.x1 ?? 0)} height={layout.height - (a.y1 ?? 0)} fill={SCH.subsurface} fillOpacity={0.8} />
              <text x={a.x ?? (a.x1 ?? 0) + 6} y={a.y ?? (a.y1 ?? 0) - 6} fontSize={9.5} fill={COLORS.muted} letterSpacing={1}>
                {a.label}
              </text>
            </g>
          );
        return (
          <text key={i} x={a.x} y={a.y} fontSize={9.5} fill={COLORS.muted} letterSpacing={1} pointerEvents="none">
            {a.text}
          </text>
        );
      })}

      {/* pipes & flow paths */}
      {state.elements.map((e) => {
        const pts = elementPoints(e, layout);
        if (!pts) return null;
        const trapped = nodeState[e.from] === "trapped" && nodeState[e.to] === "trapped";
        const zone = (e as PipeSnapshot).zone;
        const branch = !!e.branch;
        const base = branch ? zoneColor(zone, chemColors) : undefined;
        const color = e.state === "not_modelled" ? COLORS.static : pipeColor(e.state === "closed" ? "no_flow" : e.state, trapped, base);
        const d = pathD(pts);
        const selected = selEl === e.id;
        if (e.kind === "inflow") {
          const r = pts[0];
          return (
            <g key={e.id} data-testid={`element-${e.id}`} className="cursor-pointer" onClick={() => onSelect({ type: "element", id: e.id })}>
              <rect x={r.x - 90} y={r.y - 12} width={180} height={26} fill="url(#hatch)" stroke={selected ? COLORS.accent : SCH.seabed} strokeWidth={selected ? 2 : 1} />
              <path d={d} stroke={color} strokeWidth={7} fill="none" />
              {[-30, -15, 15, 30].map((dx) => (
                <line key={dx} x1={r.x + dx} y1={r.y - 2} x2={r.x + (dx > 0 ? 8 : -8)} y2={r.y - 22} stroke={color} strokeWidth={1.5} opacity={0.8} />
              ))}
            </g>
          );
        }
        const isPipe = e.kind === "pipe";
        const width = isPipe ? (branch ? (zone === "annulus" ? 5 : 3) : 8) : branch ? 3 : 6;
        const q = isPipe ? ((e as PipeSnapshot).inlet_flow_m3s ?? null) : (e.flow_m3s ?? null);
        const v = isPipe ? ((e as PipeSnapshot).velocity_m_s ?? 0) : 0;
        const flowing = e.state === "flowing";
        const reverse = (q ?? 0) < 0;
        return (
          <g key={e.id} data-testid={`element-${e.id}`}>
            <path d={d} stroke={SCH.pipeOutline} strokeWidth={width + 4} fill="none" strokeLinejoin="round" />
            <path
              d={d}
              stroke={color}
              strokeWidth={width}
              fill="none"
              strokeLinejoin="round"
              opacity={flowing ? 1 : 0.7}
              strokeDasharray={!flowing && branch && !trapped ? "6 4" : undefined}
              className={isPipe ? "cursor-pointer" : undefined}
              onClick={isPipe ? () => onSelect({ type: "element", id: e.id }) : undefined}
            />
            {isPipe && <ChemicalBands p={e as PipeSnapshot} pts={pts} colors={chemColors} refs={refs} />}
            {flowing && dynamic && (
              <path d={d} stroke="#ffffff" strokeOpacity={0.9} strokeWidth={Math.max(1, width / 3)} fill="none" strokeDasharray="2 18"
                className="flow-dash" pointerEvents="none"
                style={{ animationDuration: `${dashDuration(branch && !isPipe ? 0.05 : v)}s`, animationDirection: reverse ? "reverse" : "normal" }} />
            )}
            {selected && isPipe && <path d={d} stroke={COLORS.accent} strokeWidth={1.5} strokeDasharray="4 3" fill="none" transform="translate(6 0)" />}
            {isPipe && !branch && flowing &&
              arrowPositions(pts).map((a, i) => (
                <g key={i} transform={`translate(${a.x} ${a.y}) rotate(${a.angle + (reverse ? 180 : 0)})`} pointerEvents="none">
                  <polygon points="-6,-6 6,0 -6,6" fill={SCH.arrow} stroke={SCH.arrow} strokeWidth={1} />
                </g>
              ))}
          </g>
        );
      })}

      {/* boundary nodes */}
      {state.nodes
        .filter((n) => n.boundary || n.id === state.elements.filter((e) => !e.branch).slice(-1)[0]?.to)
        .map((n) => {
          const p = layout.nodes[n.id];
          if (!p || n.id === state.elements[0]?.from) return null;
          return <circle key={n.id} cx={p.x} cy={p.y} r={5} fill={COLORS.flow} stroke={SCH.pipeOutline} strokeWidth={2} />;
        })}

      {/* valves, choke, metering valves, check valves */}
      {state.elements.map((v) => {
        const pts = elementPoints(v, layout);
        if (!pts) return null;
        if (v.kind === "valve" || v.kind === "choke")
          return (
            <ValveSymbol key={v.id} v={v as RestrictionSnapshot} at={pointAlong(pts, 0.5)} selected={selEl === v.id} small={!!v.branch}
              onClick={() => onSelect({ type: "element", id: v.id })} />
          );
        if (v.kind === "check_valve")
          return <CheckValveSymbol key={v.id} v={v as CheckValveSnapshot} at={pointAlong(pts, 0.5)} selected={selEl === v.id} onClick={() => onSelect({ type: "element", id: v.id })} />;
        return null;
      })}

      {/* instruments */}
      {state.instruments.map((i) => {
        if (i.type === "concentration") return null;
        const at = layout.instruments[i.tag];
        if (!at) return null;
        return (
          <InstrumentBubble key={i.tag} inst={i} at={at} target={instTarget(i)} selected={selInst === i.tag} rate={instRate(i)} steady={instSteady(i)} litresPerHour={chemTx.has(i.tag)}
            onClick={() => onSelect({ type: "instrument", tag: i.tag })} prefs={prefs} />
        );
      })}
      {[...stacks.entries()].map(([k, items]) => (
        <AnalyserStack key={k} items={items} at={layout.instruments[items[0].tag]} target={instTarget(items[0])} prefs={prefs} colors={chemColors}
          selected={selInst} onSelect={(tag) => onSelect({ type: "instrument", tag })} />
      ))}

      <Legend x={layout.width - 300} y={layout.height - (state.chemical_config?.length ? 104 : 74)} chems={state.chemical_config ?? []} dynamic={dynamic} />
      <text x={12} y={16} fontSize={9.5} fontWeight={700} fill={COLORS.partial} letterSpacing={1.5}>
        SIMULATED VALUES — TRAINING ONLY
      </text>
    </svg>
      <div className="absolute right-2 top-2 flex flex-col gap-1" aria-label="Schematic zoom">
        {[
          ["+", "Zoom in", () => zoom(1 / 1.4)],
          ["−", "Zoom out", () => zoom(1.4)],
          ["⤢", "Fit", () => setVb(null)],
        ].map(([l, t, f]) => (
          <button key={t as string} type="button" title={`${t} (wheel to zoom, drag to pan, double-click to fit)`} aria-label={t as string}
            onClick={f as () => void}
            className="h-6 w-6 rounded-sm border border-line-strong bg-panel/90 text-[13px] leading-none text-muted hover:text-accent">
            {l as string}
          </button>
        ))}
      </div>
    </div>
  );
}

function Legend({ x, y, chems, dynamic }: { x: number; y: number; chems: { id: string; name: string; color: string }[]; dynamic: boolean }) {
  const valves: [string, string, boolean][] = [
    ["Open", COLORS.open, true],
    ["Closed", COLORS.closed, true],
    ["Partial / moving", COLORS.partial, false],
    ["Unavailable", COLORS.fault, false],
  ];
  const pipes: [string, string][] = [
    ["Flowing", COLORS.flow],
    ["No flow (static)", COLORS.static],
    ["Trapped", COLORS.trapped],
  ];
  const h = chems.length ? 96 : 66;
  return (
    <g transform={`translate(${x} ${y})`} pointerEvents="none">
      <rect width={290} height={h} rx={3} fill={SCH.bg} fillOpacity={0.96} filter="url(#soft)" stroke={COLORS.line} />
      {valves.map(([l, c, solid], i) => (
        <g key={l} transform={`translate(${10 + (i % 2) * 140} ${14 + Math.floor(i / 2) * 16})`}>
          <polygon points="-6,-4 -6,4 0,0" fill={solid ? c : "none"} stroke={c} strokeWidth={1.5} transform="translate(6 0)" />
          <polygon points="6,-4 6,4 0,0" fill={solid ? c : "none"} stroke={c} strokeWidth={1.5} transform="translate(6 0)" />
          <text x={20} y={3.5} fontSize={9.5} fill={COLORS.fg}>
            {l}
          </text>
        </g>
      ))}
      {pipes.map(([l, c], i) => (
        <g key={l} transform={`translate(${10 + i * 95} 54)`}>
          <line x1={0} y1={0} x2={14} y2={0} stroke={c} strokeWidth={5} />
          <text x={19} y={3.5} fontSize={9.5} fill={COLORS.fg}>
            {l}
          </text>
        </g>
      ))}
      {chems.length > 0 && (
        <g transform="translate(10 76)">
          <text x={0} y={3.5} fontSize={8.5} fill={COLORS.muted}>
            {dynamic ? "Chemical in line:" : "Chemicals:"}
          </text>
          {chems.map((c, i) => (
            <g key={c.id} transform={`translate(${78 + i * 52} 0)`}>
              <line x1={0} y1={0} x2={12} y2={0} stroke={c.color} strokeWidth={4} />
              <text x={15} y={3.5} fontSize={8.5} fill={COLORS.fg}>
                {c.id === "methanol" ? "MeOH" : c.id === "corrosion_inhibitor" ? "CI" : c.id === "wax_inhibitor" ? "Wax" : c.id === "biocide" ? "Bio" : c.id}
              </text>
            </g>
          ))}
        </g>
      )}
    </g>
  );
}

export const TreeSchematic = memo(TreeSchematicInner);
