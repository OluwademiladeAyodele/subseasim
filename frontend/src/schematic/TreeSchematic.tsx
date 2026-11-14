/**
 * Configuration-driven SVG schematic. Every drawn component comes from the
 * scenario topology (elements, nodes) + layout (coordinates). Nothing about a
 * specific tree arrangement is hard-coded here.
 */
import { memo } from "react";

import { COLORS, pipeColor, valveVisual, VALVE_LABEL } from "@/lib/stateColors";
import { instrumentDisplay, type DisplayPrefs, fmt } from "@/lib/units";
import type {
  ElementSnapshot,
  InstrumentSnapshot,
  Layout,
  LayoutPoint,
  RestrictionSnapshot,
  SimulationState,
} from "@/types/simulation";

import { arrowPositions, pointAlong } from "./geometry";

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

function ValveSymbol({ v, at, selected, onClick }: { v: RestrictionSnapshot; at: { x: number; y: number; angle: number }; selected: boolean; onClick: () => void }) {
  const vis = valveVisual(v);
  const color = VALVE_COLOR[vis];
  const s = v.kind === "choke" ? 13 : 11;
  const h = s * 0.75;
  const vertical = Math.abs(Math.abs(at.angle) - 90) < 20;
  const fill = vis === "closed" || vis === "open" ? color : COLORS.panel;
  const label = v.kind === "choke" ? `${fmt(v.position_pct, 1)} %` : VALUE_SHORT(vis);
  const tagPos = vertical ? { x: at.x + s + 8, y: at.y - 3, anchor: "start" as const } : { x: at.x, y: at.y - s - 9, anchor: "middle" as const };
  const statePos = vertical ? { x: at.x + s + 8, y: at.y + 10, anchor: "start" as const } : { x: at.x, y: at.y + s + 15, anchor: "middle" as const };

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
        <rect x={at.x - s - 5} y={at.y - s - 5} width={2 * s + 10} height={2 * s + 10} fill="none" stroke="#38bdf8" strokeWidth={1.5} strokeDasharray="3 2" />
      )}
      <g transform={`translate(${at.x} ${at.y}) rotate(${at.angle})`} className={vis === "moving" ? "moving-blink" : undefined}>
        <polygon points={`${-s},${-h} ${-s},${h} 0,0`} fill={fill} stroke={color} strokeWidth={2} strokeLinejoin="round" />
        <polygon points={`${s},${-h} ${s},${h} 0,0`} fill={fill} stroke={color} strokeWidth={2} strokeLinejoin="round" />
        {v.kind === "choke" && (
          <>
            <line x1={-s} y1={s} x2={s - 2} y2={-s + 2} stroke={color} strokeWidth={1.8} />
            <polygon points={`${s},${-s} ${s - 7},${-s + 2} ${s - 2},${-s + 7}`} fill={color} />
            {vis === "partial" && <rect x={-3} y={-3} width={6} height={6} fill={color} />}
          </>
        )}
        {vis === "fault" && (
          <>
            <line x1={-s} y1={-s} x2={s} y2={s} stroke={COLORS.fault} strokeWidth={2} />
            <line x1={-s} y1={s} x2={s} y2={-s} stroke={COLORS.fault} strokeWidth={2} />
          </>
        )}
      </g>
      <text x={tagPos.x} y={tagPos.y} textAnchor={tagPos.anchor} fontSize={11} fontWeight={700} fill={COLORS.fg}>
        {v.tag}
      </text>
      <text x={statePos.x} y={statePos.y} textAnchor={statePos.anchor} fontSize={10} fontWeight={700} fill={color} className="num">
        {label}
        {v.moving ? ` → ${fmt(v.commanded_pct, 0)} %` : ""}
      </text>
    </g>
  );
}

function VALUE_SHORT(vis: ReturnType<typeof valveVisual>): string {
  return vis === "partial" ? "PARTIAL" : VALVE_LABEL[vis];
}

function InstrumentBubble({
  inst,
  at,
  target,
  selected,
  onClick,
  prefs,
}: {
  inst: InstrumentSnapshot;
  at: LayoutPoint;
  target: LayoutPoint | null;
  selected: boolean;
  onClick: () => void;
  prefs: DisplayPrefs;
}) {
  const [prefix, num] = inst.tag.split("-");
  const d = instrumentDisplay(inst.type, inst.value_si, prefs);
  const bad = inst.status === "BAD" || inst.status === "UNDETERMINED";
  const oor = inst.status.startsWith("OUT_OF_RANGE");
  const ring = bad ? COLORS.fault : oor ? COLORS.partial : selected ? "#38bdf8" : COLORS.muted;
  const text = bad ? (inst.status === "BAD" ? "BAD" : "UNDET") : `${fmt(d.value, d.digits)}`;
  return (
    <g role="button" tabIndex={0} aria-label={`${inst.tag} ${inst.description}`} data-testid={`inst-${inst.tag}`} onClick={onClick}
      onKeyDown={(ev) => (ev.key === "Enter" || ev.key === " ") && onClick()} className="cursor-pointer outline-none">
      {target && <line x1={at.x} y1={at.y} x2={target.x} y2={target.y} stroke={COLORS.muted} strokeWidth={1} strokeDasharray="2 3" />}
      <circle cx={at.x} cy={at.y} r={15} fill="#0b121a" stroke={ring} strokeWidth={selected ? 2 : 1.3} />
      <line x1={at.x - 15} y1={at.y} x2={at.x + 15} y2={at.y} stroke={ring} strokeWidth={0.8} />
      <text x={at.x} y={at.y - 3} textAnchor="middle" fontSize={8.5} fontWeight={700} fill={COLORS.fg}>
        {prefix}
      </text>
      <text x={at.x} y={at.y + 10} textAnchor="middle" fontSize={8.5} fill={COLORS.fg}>
        {num}
      </text>
      <rect x={at.x - 32} y={at.y + 18} width={64} height={15} fill="#060a0e" stroke={oor ? COLORS.partial : COLORS.line} strokeWidth={1} />
      <text x={at.x} y={at.y + 29} textAnchor="middle" fontSize={10} className="num" fill={bad ? COLORS.fault : oor ? COLORS.partial : "#e6f6ff"}>
        {text} <tspan fill={COLORS.muted} fontSize={8}>{bad ? "" : d.unit}</tspan>
      </text>
    </g>
  );
}

function TreeSchematicInner({ state, layout, selection, onSelect, prefs }: Props) {
  const nodeState = Object.fromEntries(state.nodes.map((n) => [n.id, n.state]));
  const q = state.hydraulics.q_m3s ?? 0;
  const reverse = q < 0;
  const selEl = selection?.type === "element" ? selection.id : null;
  const selInst = selection?.type === "instrument" ? selection.tag : null;

  const instTarget = (i: InstrumentSnapshot): LayoutPoint | null => {
    if (i.node) return layout.nodes[i.node] ?? null;
    const a = i.high_node ? layout.nodes[i.high_node] : null;
    const b = i.low_node ? layout.nodes[i.low_node] : null;
    return a && b ? { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 } : null;
  };

  return (
    <svg
      viewBox={`0 0 ${layout.width} ${layout.height}`}
      className="h-full w-full select-none"
      preserveAspectRatio="xMidYMid meet"
      role="img"
      aria-label="Subsea production system schematic (simulated)"
      onClick={(ev) => ev.target === ev.currentTarget && onSelect(null)}
    >
      <defs>
        <pattern id="hatch" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <line x1="0" y1="0" x2="0" y2="8" stroke="#6b5434" strokeWidth="2" />
        </pattern>
        <pattern id="grid" width="20" height="20" patternUnits="userSpaceOnUse">
          <path d="M 20 0 L 0 0 0 20" fill="none" stroke="#101a24" strokeWidth="1" />
        </pattern>
      </defs>
      <rect width={layout.width} height={layout.height} fill="url(#grid)" onClick={() => onSelect(null)} />

      {/* annotations */}
      {layout.annotations.map((a, i) => {
        if (a.type === "rect")
          return (
            <g key={i}>
              <rect x={a.x} y={a.y} width={a.w} height={a.h} fill="none" stroke={COLORS.line} strokeWidth={1.2} strokeDasharray="6 3" />
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
            <g key={i}>
              <line x1={a.x1} y1={a.y1} x2={a.x2} y2={a.y2} stroke="#3b3022" strokeWidth={2} />
              <text x={a.x ?? (a.x1 ?? 0) + 6} y={a.y ?? (a.y1 ?? 0) - 6} fontSize={9.5} fill={COLORS.muted} letterSpacing={1}>
                {a.label}
              </text>
            </g>
          );
        return (
          <text key={i} x={a.x} y={a.y} fontSize={9.5} fill={COLORS.muted} letterSpacing={1}>
            {a.text}
          </text>
        );
      })}

      {/* pipes & flow paths */}
      {state.elements.map((e) => {
        const pts = elementPoints(e, layout);
        if (!pts) return null;
        const trapped = nodeState[e.from] === "trapped" && nodeState[e.to] === "trapped";
        const color = pipeColor(e.state === "closed" ? "no_flow" : e.state, trapped);
        const d = pts.map((p, i) => `${i ? "L" : "M"}${p.x},${p.y}`).join(" ");
        const selected = selEl === e.id;
        if (e.kind === "inflow") {
          const r = pts[0];
          return (
            <g key={e.id} data-testid={`element-${e.id}`} className="cursor-pointer" onClick={() => onSelect({ type: "element", id: e.id })}>
              <rect x={r.x - 90} y={r.y - 12} width={180} height={26} fill="url(#hatch)" stroke={selected ? "#38bdf8" : "#6b5434"} strokeWidth={selected ? 2 : 1} />
              <path d={d} stroke={color} strokeWidth={7} fill="none" />
              {[-30, -15, 15, 30].map((dx) => (
                <line key={dx} x1={r.x + dx} y1={r.y - 2} x2={r.x + (dx > 0 ? 8 : -8)} y2={r.y - 22} stroke={color} strokeWidth={1.5} opacity={0.8} />
              ))}
            </g>
          );
        }
        const width = e.kind === "pipe" ? 8 : 6;
        return (
          <g key={e.id} data-testid={`element-${e.id}`}>
            <path d={d} stroke="#05080b" strokeWidth={width + 4} fill="none" strokeLinejoin="round" />
            <path
              d={d}
              stroke={color}
              strokeWidth={width}
              fill="none"
              strokeLinejoin="round"
              opacity={e.state === "flowing" ? 1 : 0.75}
              className={e.kind === "pipe" ? "cursor-pointer" : undefined}
              onClick={e.kind === "pipe" ? () => onSelect({ type: "element", id: e.id }) : undefined}
            />
            {selected && e.kind === "pipe" && <path d={d} stroke="#38bdf8" strokeWidth={1.5} strokeDasharray="4 3" fill="none" transform="translate(6 0)" />}
            {e.kind === "pipe" &&
              e.state === "flowing" &&
              arrowPositions(pts).map((a, i) => (
                <g key={i} transform={`translate(${a.x} ${a.y}) rotate(${a.angle + (reverse ? 180 : 0)})`} pointerEvents="none">
                  <polygon points="-6,-6 6,0 -6,6" fill="#04131a" stroke="#04131a" strokeWidth={1} />
                </g>
              ))}
          </g>
        );
      })}

      {/* boundary */}
      {(() => {
        const last = state.elements[state.elements.length - 1];
        const p = last ? layout.nodes[last.to] : null;
        if (!p) return null;
        return <circle cx={p.x} cy={p.y} r={5} fill={COLORS.flow} stroke="#04131a" strokeWidth={2} />;
      })()}

      {/* valves & choke */}
      {state.elements
        .filter((e): e is RestrictionSnapshot => e.kind === "valve" || e.kind === "choke")
        .map((v) => {
          const pts = elementPoints(v, layout);
          if (!pts) return null;
          return <ValveSymbol key={v.id} v={v} at={pointAlong(pts, 0.5)} selected={selEl === v.id} onClick={() => onSelect({ type: "element", id: v.id })} />;
        })}

      {/* instruments */}
      {state.instruments.map((i) => {
        const at = layout.instruments[i.tag];
        if (!at) return null;
        return (
          <InstrumentBubble key={i.tag} inst={i} at={at} target={instTarget(i)} selected={selInst === i.tag}
            onClick={() => onSelect({ type: "instrument", tag: i.tag })} prefs={prefs} />
        );
      })}

      <Legend x={layout.width - 300} y={layout.height - 74} />
      <text x={12} y={18} fontSize={10} fontWeight={700} fill={COLORS.partial} letterSpacing={2}>
        SIMULATED VALUES — TRAINING ONLY — NOT CONNECTED TO ANY REAL SYSTEM
      </text>
    </svg>
  );
}

function Legend({ x, y }: { x: number; y: number }) {
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
  return (
    <g transform={`translate(${x} ${y})`} pointerEvents="none">
      <rect width={290} height={66} fill="#081018" stroke={COLORS.line} />
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
    </g>
  );
}

export const TreeSchematic = memo(TreeSchematicInner);
