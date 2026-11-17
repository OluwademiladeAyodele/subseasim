/**
 * Christmas-tree engineering workstation (SVG).
 *
 * Positions come ONLY from the schematic layout file (backend
 * app/scenarios/layouts/<id>.json, traced from the reference control-system
 * page); every state shown - valve positions, line flow state, transmitter
 * values, hydraulic header pressures, chemical injection - comes from the
 * live simulation snapshot. Components are linked to the model through the
 * layout's stable references (element:, instrument:, chemical:, selector:,
 * header:, supply:). The frontend never computes process values.
 */
import { memo, useEffect, useRef, useState } from "react";

import { COLORS, SCH, valveVisual } from "@/lib/stateColors";
import { aliasOf, displayTag } from "@/lib/tags";
import { type DisplayPrefs, fmt, instrumentDisplay, paToBarDelta, pressureFromPa } from "@/lib/units";
import type {
  CheckValveSnapshot,
  ElementSnapshot,
  InstrumentSnapshot,
  RestrictionSnapshot,
  SchComponent,
  SchematicLayout,
  SchLine,
  SimulationState,
} from "@/types/simulation";

import type { Selection } from "./TreeSchematic";

/** Reference-HMI colour convention used on this page (shown in the legend). */
export const XT = {
  open: "#0d9488",
  closed: "#dc2626",
  partial: "#d97706",
  moving: "#d97706",
  fault: "#c026d3",
  line: {
    production: "#9f1239",
    annulus: "#0f766e",
    service: "#0f766e",
    chemical: "#64748b",
    methanol: "#64748b",
    downhole_chemical: "#64748b",
    hydraulic: "#1d4ed8",
  } as Record<SchLine["cls"], string>,
  panel: "#ffffff",
  panelHead: "#f1f5f9",
  ink: "#0f172a",
};

interface Props {
  state: SimulationState;
  schematic: SchematicLayout;
  selection: Selection;
  onSelect: (s: Selection) => void;
  onNavigate: (page: string) => void;
  prefs: DisplayPrefs;
}

const ref = (r: string | null | undefined): [string, string] => {
  if (!r) return ["", ""];
  const i = r.indexOf(":");
  return [r.slice(0, i), r.slice(i + 1)];
};

function useZoomPan(width: number, height: number) {
  const svgRef = useRef<SVGSVGElement>(null);
  const drag = useRef<{ sx: number; sy: number; box: { x: number; y: number; w: number; h: number } } | null>(null);
  const [vb, setVb] = useState<{ x: number; y: number; w: number; h: number } | null>(null);
  useEffect(() => setVb(null), [width, height]);
  const full = { x: 0, y: 0, w: width, h: height };
  const box = vb ?? full;
  const toSvg = (cx: number, cy: number) => {
    const m = svgRef.current?.getScreenCTM();
    if (!m) return null;
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
  const handlers = {
    onWheel: (ev: React.WheelEvent) => zoom(ev.deltaY > 0 ? 1.15 : 1 / 1.15, ev.clientX, ev.clientY),
    onDoubleClick: (ev: React.MouseEvent) => !(ev.target as Element).closest("[role=button]") && setVb(null),
    onPointerDown: (ev: React.PointerEvent) => {
      if (!vb || (ev.target as Element).closest("[role=button]")) return;
      const p = toSvg(ev.clientX, ev.clientY);
      if (p) drag.current = { sx: p.x, sy: p.y, box: vb };
    },
    onPointerMove: (ev: React.PointerEvent) => {
      const d = drag.current;
      const p = d && toSvg(ev.clientX, ev.clientY);
      if (!d || !p) return;
      setVb({ ...d.box, x: Math.min(full.w - d.box.w, Math.max(0, d.box.x - (p.x - d.sx))), y: Math.min(full.h - d.box.h, Math.max(0, d.box.y - (p.y - d.sy))) });
    },
    onPointerUp: () => (drag.current = null),
    onPointerLeave: () => (drag.current = null),
  };
  return { svgRef, box, vb, zoom, reset: () => setVb(null), handlers };
}

/* ------------------------------------------------------------------ symbols */

function TagLabel({ x, y, text, anchor, status, selected }: { x: number; y: number; text: string; anchor: "start" | "middle" | "end"; status?: string; selected?: boolean }) {
  const w = Math.max(44, text.length * 6.6 + 10);
  const x0 = anchor === "start" ? x : anchor === "end" ? x - w : x - w / 2;
  const dashed = status === "addition" ? "3 2" : status === "uncertain" || status === "placeholder" ? "1.5 1.5" : undefined;
  return (
    <g pointerEvents="none">
      <rect x={x0} y={y - 8} width={w} height={15} rx={2} fill={XT.panel} stroke={selected ? COLORS.accent : "#94a3b8"} strokeWidth={selected ? 1.6 : 0.8} strokeDasharray={dashed} />
      <text x={x0 + w / 2} y={y + 3.5} textAnchor="middle" fontSize={10} fontWeight={700} fill={status === "addition" ? COLORS.muted : XT.ink} fontStyle={status === "addition" ? "italic" : undefined}>
        {text}
      </text>
    </g>
  );
}

function valveColor(v: RestrictionSnapshot): string {
  return XT[valveVisual(v)];
}

/** Gate / injection / selector valve: bow-tie with actuator box (flow along local x). */
function ValveGlyph({ v, size = 12, actuator = true }: { v: RestrictionSnapshot | null; size?: number; actuator?: boolean }) {
  const s = size;
  const h = s * 0.72;
  const c = v ? valveColor(v) : COLORS.static;
  const vis = v ? valveVisual(v) : "closed";
  const fill = vis === "partial" || vis === "moving" ? XT.panel : c;
  return (
    <g className={vis === "moving" ? "moving-blink" : undefined}>
      <polygon points={`${-s},${-h} ${-s},${h} 0,0`} fill={fill} stroke={c} strokeWidth={1.6} strokeLinejoin="round" />
      <polygon points={`${s},${-h} ${s},${h} 0,0`} fill={fill} stroke={c} strokeWidth={1.6} strokeLinejoin="round" />
      {actuator && (
        <>
          <line x1={0} y1={0} x2={0} y2={-s * 0.95} stroke={c} strokeWidth={1.6} />
          <rect x={-s * 0.42} y={-s * 1.55} width={s * 0.84} height={s * 0.62} rx={1} fill={c} stroke={c} />
        </>
      )}
      {vis === "partial" && <rect x={-2.5} y={-2.5} width={5} height={5} fill={c} />}
      {vis === "fault" && <line x1={-s} y1={-s} x2={s} y2={s} stroke={XT.fault} strokeWidth={2} />}
    </g>
  );
}

function Clickable({ id, label, selected, onClick, children, testid }: { id: string; label: string; selected: boolean; onClick: () => void; children: React.ReactNode; testid: string }) {
  return (
    <g role="button" tabIndex={0} aria-label={label} data-testid={testid} data-component={id} onClick={(e) => { e.stopPropagation(); onClick(); }}
      onKeyDown={(ev) => (ev.key === "Enter" || ev.key === " ") && onClick()} className="cursor-pointer outline-none" aria-pressed={selected}>
      {children}
    </g>
  );
}

/* ------------------------------------------------------------- main view */

function XtSchematicInner({ state, schematic: L, selection, onSelect, onNavigate, prefs }: Props) {
  const { svgRef, box, vb, zoom, reset, handlers } = useZoomPan(L.width, L.height);
  const elById = new Map<string, ElementSnapshot>(state.elements.map((e) => [e.id, e]));
  const instByTag = new Map<string, InstrumentSnapshot>(state.instruments.map((i) => [i.tag, i]));
  const hyd = state.control_hydraulics ?? null;
  const chemColor: Record<string, string> = Object.fromEntries((state.chemical_config ?? []).map((c) => [c.id, c.color]));
  const chemSnap = Object.fromEntries((state.chemicals ?? []).map((c) => [c.id, c]));
  const selEl = selection?.type === "element" ? selection.id : null;
  const selInst = selection?.type === "instrument" ? selection.tag : null;
  const selSel = selection?.type === "selector" ? selection.tag : null;
  const selChem = selection?.type === "chemical" ? selection.id : null;
  const selHyd = selection?.type === "hydraulic" ? selection.id : null;
  const dynamic = state.mode === "dynamic";

  const hydPressure = (r: string | null | undefined): { p: number; ok: boolean } | null => {
    const [k, id] = ref(r);
    if (!hyd) return null;
    if (k === "header") {
      const h = hyd.headers.find((x) => x.id === id);
      const s = h && hyd.supplies.find((x) => x.id === h.supply);
      return h && s ? { p: h.pressure_pa, ok: h.pressure_pa >= s.minimum_operating_pressure_pa } : null;
    }
    if (k === "supply") {
      const s = hyd.supplies.find((x) => x.id === id);
      return s ? { p: s.pressure_pa, ok: s.available } : null;
    }
    return null;
  };

  const lineFlowing = (ln: SchLine): boolean => {
    if (ln.cls === "hydraulic") return !!hydPressure(ln.model)?.ok;
    return ln.elements.some((id) => elById.get(id)?.state === "flowing");
  };

  const d = (pts: [number, number][]) => pts.map((p, i) => `${i ? "L" : "M"}${p[0]} ${p[1]}`).join(" ");

  const instPanel = (c: SchComponent) => {
    const tags = c.models.map((m) => ref(m)[1]);
    const rows = tags.map((t) => instByTag.get(t)).filter(Boolean) as InstrumentSnapshot[];
    const row = c.h < 45; // single-row panel (tag | value), as PD3014 on the reference
    const alias = rows[0] ? aliasOf(state, rows[0].tag) : null;
    const anySel = rows.some((r) => r.tag === selInst);
    const H_HEAD = row ? c.h : 15;
    const H_ROW = rows.length ? (c.h - (row ? 0 : H_HEAD)) / (row ? 1 : rows.length) : 0;
    return (
      <g key={c.id} data-testid={`panel-${c.id}`}>
        {c.tap && <TapLeader c={c} />}
        <rect x={c.x} y={c.y} width={c.w} height={c.h} rx={2} fill={XT.panel} stroke={anySel ? COLORS.accent : "#94a3b8"} strokeWidth={anySel ? 2 : 0.9}
          strokeDasharray={alias?.status === "addition" || !alias ? "3 2" : undefined} filter="url(#xtsoft)" />
        {!row && <rect x={c.x} y={c.y} width={c.w} height={H_HEAD} rx={2} fill={XT.panelHead} />}
        <text x={c.x + 5} y={c.y + (row ? c.h / 2 + 3.5 : 11)} fontSize={10} fontWeight={700} fill={XT.ink} pointerEvents="none">
          {c.id}
        </text>
        {rows.map((inst, k) => {
          const dsp = instrumentDisplay(inst.type, inst.value_si, prefs, inst.display_unit);
          const bad = inst.status === "BAD" || inst.status === "UNDETERMINED";
          const nm = inst.status === "NOT_MODELLED";
          const txt = nm ? "N/M" : bad ? inst.status : fmt(dsp.value, dsp.digits);
          const y0 = row ? c.y : c.y + H_HEAD + k * H_ROW;
          const sel = inst.tag === selInst;
          return (
            <Clickable key={inst.tag} id={inst.tag} label={`${displayTag(state, inst.tag)} ${inst.description}`} selected={sel} testid={`inst-${inst.tag}`}
              onClick={() => onSelect({ type: "instrument", tag: inst.tag })}>
              <rect x={row ? c.x + c.w * 0.45 : c.x + 1} y={y0 + 1} width={row ? c.w * 0.55 - 1 : c.w - 2} height={(row ? c.h : H_ROW) - 2}
                fill={sel ? SCH.selected : "transparent"} />
              <text x={c.x + c.w - 5} y={y0 + (row ? c.h : H_ROW) / 2 + 4} textAnchor="end" fontSize={10.5} className="num"
                fill={bad ? XT.fault : nm ? COLORS.static : XT.ink}>
                {txt} <tspan fontSize={8.5} fill={COLORS.muted}>{bad || nm ? "" : dsp.unit}</tspan>
              </text>
            </Clickable>
          );
        })}
      </g>
    );
  };

  const TapLeader = ({ c }: { c: SchComponent }) => {
    const [tx, ty] = c.tap!;
    const cx = Math.min(Math.max(tx, c.x), c.x + c.w);
    const cy = Math.min(Math.max(ty, c.y), c.y + c.h);
    return (
      <g pointerEvents="none">
        <line x1={tx} y1={ty} x2={cx} y2={cy} stroke="#94a3b8" strokeWidth={0.9} />
        <circle cx={tx} cy={ty} r={4.2} fill="#e2e8f0" stroke="#475569" strokeWidth={1} />
      </g>
    );
  };

  const component = (c: SchComponent) => {
    const [kind, id] = ref(c.model);
    switch (c.type) {
      case "tag_panel":
        return instPanel(c);
      case "choke_panel": {
        const v = elById.get(id) as RestrictionSnapshot | undefined;
        if (!v) return null;
        const rows: [string, string][] = [
          ["Act", `${fmt(v.position_pct, 1)} %`],
          ["Set", `${fmt(v.commanded_pct, 1)} %`],
          ["ΔP", v.dp_pa == null ? "—" : `${fmt(paToBarDelta(v.dp_pa), 1)} bar`],
        ];
        const hh = (c.h - 15) / 3;
        return (
          <Clickable key={c.id} id={c.id} label={`${displayTag(state, v.tag)} choke position`} selected={selEl === id} testid={`panel-${c.id}`}
            onClick={() => onSelect({ type: "element", id })}>
            <rect x={c.x} y={c.y} width={c.w} height={c.h} rx={2} fill={XT.panel} stroke={selEl === id ? COLORS.accent : "#94a3b8"} strokeWidth={selEl === id ? 2 : 0.9} filter="url(#xtsoft)" />
            <rect x={c.x} y={c.y} width={c.w} height={15} rx={2} fill={XT.panelHead} />
            <text x={c.x + 5} y={c.y + 11} fontSize={10} fontWeight={700} fill={XT.ink}>{displayTag(state, v.tag)}</text>
            {rows.map(([k, val], i) => (
              <g key={k}>
                <text x={c.x + 5} y={c.y + 15 + hh * i + hh / 2 + 3.5} fontSize={9} fill={COLORS.muted}>{k}</text>
                <text x={c.x + c.w - 5} y={c.y + 15 + hh * i + hh / 2 + 3.5} textAnchor="end" fontSize={10.5} className="num" fill={XT.ink}>{val}</text>
              </g>
            ))}
          </Clickable>
        );
      }
      case "sand_detector": {
        const det = state.sand_choke?.available ? state.sand_choke.detector : undefined;
        const alarm = !!det?.alarm;
        const txt = !det ? "three-phase model off" : det.reading_g_s == null ? det.status.toLowerCase().replace(/_/g, " ") : `${fmt(det.reading_g_s, 3)} g/s`;
        return (
          <g key={c.id} data-testid={`panel-${c.id}`}>
            {c.tap && <TapLeader c={c} />}
            <Clickable id={c.id} label={`${c.id} sand detector`} selected={false} testid="sand-detector" onClick={() => onNavigate("sand")}>
              <title>{det ? `${det.tag}: ${det.type.replace(/_/g, " ")} - click for sand monitoring` : c.note}</title>
              <rect x={c.x} y={c.y} width={c.w} height={c.h} rx={2} fill={alarm ? "#fee2e2" : XT.panel} stroke={alarm ? XT.closed : "#94a3b8"} strokeWidth={alarm ? 1.6 : 0.9}
                strokeDasharray={det ? undefined : "1.5 1.5"} />
              <text x={c.x + 5} y={c.y + c.h / 2 + 3.5} fontSize={10} fontWeight={700} fill={XT.ink}>{c.id}</text>
              <text x={c.x + c.w - 5} y={c.y + c.h / 2 + 3.5} textAnchor="end" fontSize={9.5} className="num" fill={alarm ? XT.closed : det ? XT.ink : COLORS.static}>
                {txt}
              </text>
            </Clickable>
          </g>
        );
      }
      case "header_panel": {
        const hp = hydPressure(c.model);
        const engTag = kind === "header" ? hyd?.headers.find((h) => h.id === id)?.tag : hyd?.supplies.find((s) => s.id === id)?.tag;
        const sel = selHyd === id;
        return (
          <g key={c.id} data-testid={`panel-${c.id}`}>
            {c.tap && <TapLeader c={c} />}
            <Clickable id={c.id} label={`${c.id} hydraulic pressure`} selected={sel} testid={`hyd-${id}`} onClick={() => onSelect({ type: "hydraulic", id })}>
              <rect x={c.x} y={c.y} width={c.w} height={c.h} rx={2} fill={sel ? SCH.selected : XT.panel} stroke={sel ? COLORS.accent : hp && !hp.ok ? XT.closed : "#94a3b8"} strokeWidth={sel ? 2 : 0.9}
                strokeDasharray={engTag && aliasOf(state, engTag)?.status !== "verified" ? "1.5 1.5" : undefined} />
              <text x={c.x + 4} y={c.y + 10} fontSize={8.5} fontWeight={700} fill={XT.ink}>{c.id}</text>
              <text x={c.x + c.w - 4} y={c.y + c.h - 4} textAnchor="end" fontSize={10} className="num" fill={hp && !hp.ok ? XT.closed : XT.ink}>
                {hp ? fmt(pressureFromPa(hp.p, prefs.pressureRef), 1) : "—"} <tspan fontSize={8} fill={COLORS.muted}>{prefs.pressureRef}</tspan>
              </text>
            </Clickable>
          </g>
        );
      }
      case "selector_valve": {
        const sv = hyd?.selector_valves.find((s) => s.tag === id);
        if (!sv) return null;
        const pseudo = { available: true, moving: sv.moving, position_pct: sv.opening_pct } as RestrictionSnapshot;
        const sel = selSel === id;
        return (
          <Clickable key={c.id} id={c.id} label={`${displayTag(state, id)} ${sv.name}`} selected={sel} testid={`selector-${id}`} onClick={() => onSelect({ type: "selector", tag: id })}>
            <rect x={c.x - 16} y={c.y - 22} width={32} height={34} fill="transparent" />
            {sel && <rect x={c.x - 15} y={c.y - 21} width={30} height={32} fill="none" stroke={COLORS.accent} strokeDasharray="3 2" />}
            <g transform={`translate(${c.x} ${c.y}) rotate(${c.rotation})`}>
              <ValveGlyph v={pseudo} size={11} />
            </g>
          </Clickable>
        );
      }
      case "button":
        return (
          <Clickable key={c.id} id={c.id} label={c.note || c.id} selected={false} testid={`btn-${c.id}`} onClick={() => onNavigate(id)}>
            <rect x={c.x} y={c.y} width={c.w} height={c.h} rx={3} fill="#f8fafc" stroke="#64748b" strokeWidth={0.9} />
            <text x={c.x + c.w / 2} y={c.y + c.h / 2 + 3.5} textAnchor="middle" fontSize={9.5} fontWeight={600} fill={XT.ink}>SCM Diagnostic</text>
          </Clickable>
        );
      case "mpfm": {
        const m = state.mpfm;
        const sel = selection?.type === "mpfm";
        const qcol = !m || m.quality === "NOT_MODELLED" ? COLORS.static : m.quality === "GOOD" ? XT.open : m.quality === "DEGRADED" ? XT.partial : XT.closed;
        const meas = m?.measured;
        return (
          <Clickable key={c.id} id={c.id} label={`${m?.tag ?? c.id} multiphase flow meter`} selected={sel} testid="mpfm-symbol" onClick={() => onSelect({ type: "mpfm" })}>
            <g transform={`translate(${c.x} ${c.y}) rotate(${c.rotation})`}>
              <rect x={-16} y={-10} width={32} height={20} rx={4} fill={XT.panel} stroke={qcol} strokeWidth={2} />
              <path d="M -12 -6 L -4 -2 L 4 -2 L 12 -6 M -12 6 L -4 2 L 4 2 L 12 6" fill="none" stroke="#475569" strokeWidth={1.2} />
            </g>
            {c.w > 0 && (
              <g>
                <rect x={c.x + c.w * 0 + 22} y={c.y - c.h / 2} width={c.w} height={c.h} rx={2} fill={sel ? SCH.selected : XT.panel}
                  stroke={sel ? COLORS.accent : "#94a3b8"} strokeWidth={sel ? 2 : 0.9} strokeDasharray="3 2" filter="url(#xtsoft)" />
                <circle cx={c.x + 30} cy={c.y - c.h / 2 + 9} r={3.5} fill={qcol} />
                <text x={c.x + 37} y={c.y - c.h / 2 + 12} fontSize={10} fontWeight={700} fill={XT.ink}>{m?.tag ?? c.id}</text>
                <text x={c.x + 22 + c.w - 5} y={c.y - c.h / 2 + 12} textAnchor="end" fontSize={8.5} fill={qcol}>{m?.quality ?? ""}</text>
                <text x={c.x + 27} y={c.y + c.h / 2 - 6} fontSize={9.5} className="num" fill={XT.ink}>
                  {meas ? `${fmt(meas.oil_sm3_d, 0)} Sm³/d oil · WC ${fmt(meas.water_cut * 100, 0)}%` : m?.quality === "NOT_MODELLED" ? "three-phase model off" : "—"}
                </text>
              </g>
            )}
          </Clickable>
        );
      }
      case "inline_device":
        return (
          <g key={c.id} transform={`translate(${c.x} ${c.y}) rotate(${c.rotation})`} pointerEvents="none">
            <title>{c.note}</title>
            <rect x={-11} y={-7} width={22} height={14} rx={3} fill={XT.panel} stroke="#475569" strokeWidth={1.2} />
            <line x1={-5} y1={-7} x2={-5} y2={7} stroke="#475569" />
            <line x1={5} y1={-7} x2={5} y2={7} stroke="#475569" />
          </g>
        );
      case "check_valve": {
        const v = elById.get(id) as CheckValveSnapshot | undefined;
        if (!v) return null;
        const open = v.state === "flowing";
        const col = open ? XT.open : "#94a3b8";
        const sel = selEl === id;
        return (
          <Clickable key={c.id} id={c.id} label={`${v.tag} ${v.name}`} selected={sel} testid={`check-${v.tag}`} onClick={() => onSelect({ type: "element", id })}>
            <title>{`${v.tag} - SubseaSim addition (not drawn on the reference page)`}</title>
            <rect x={c.x - 9} y={c.y - 9} width={18} height={18} fill="transparent" />
            {sel && <rect x={c.x - 9} y={c.y - 9} width={18} height={18} fill="none" stroke={COLORS.accent} strokeDasharray="3 2" />}
            <g transform={`translate(${c.x} ${c.y}) rotate(${c.rotation})`}>
              <polygon points="-5,-4.5 -5,4.5 4,0" fill={open ? col : XT.panel} stroke={col} strokeWidth={1.3} />
              <line x1={5} y1={-5.5} x2={5} y2={5.5} stroke={col} strokeWidth={1.6} />
            </g>
          </Clickable>
        );
      }
      case "metering_valve": {
        const v = elById.get(id) as RestrictionSnapshot | undefined;
        if (!v) return null;
        const sel = selEl === id;
        const a = aliasOf(state, v.tag);
        const col = valveColor(v);
        return (
          <Clickable key={c.id} id={c.id} label={`${displayTag(state, v.tag)} ${v.name}`} selected={sel} testid={`valve-${v.tag}`} onClick={() => onSelect({ type: "element", id })}>
            <rect x={c.x - 14} y={c.y - 9} width={28} height={18} fill="transparent" />
            <g transform={`translate(${c.x} ${c.y}) rotate(${c.rotation})`}>
              <circle cx={-6} cy={0} r={4.5} fill={XT.panel} stroke={col} strokeWidth={1.5} />
              <circle cx={6} cy={0} r={4.5} fill={XT.panel} stroke={col} strokeWidth={1.5} />
              <line x1={-1.5} y1={0} x2={1.5} y2={0} stroke={col} strokeWidth={1.5} />
              <rect x={-6} y={-1.2} width={12 * (v.position_pct / 100)} height={2.4} fill={col} />
            </g>
            {c.label && (
              <g>
                <TagLabel x={c.x + c.label.dx} y={c.y + c.label.dy - 9} text={displayTag(state, v.tag)} anchor={c.label.anchor} status={a?.status} selected={sel} />
                <TagLabel x={c.x + c.label.dx} y={c.y + c.label.dy + 6} text={`${fmt(v.position_pct, 2)} %`} anchor={c.label.anchor} />
              </g>
            )}
          </Clickable>
        );
      }
      case "choke": {
        const v = elById.get(id) as RestrictionSnapshot | undefined;
        if (!v) return null;
        const sel = selEl === id;
        const col = valveColor(v);
        return (
          <Clickable key={c.id} id={c.id} label={`${displayTag(state, v.tag)} production choke`} selected={sel} testid={`valve-${v.tag}`} onClick={() => onSelect({ type: "element", id })}>
            <rect x={c.x - 18} y={c.y - 14} width={36} height={44} fill="transparent" />
            {sel && <rect x={c.x - 17} y={c.y - 13} width={34} height={42} fill="none" stroke={COLORS.accent} strokeDasharray="3 2" />}
            <g transform={`translate(${c.x} ${c.y + 10}) rotate(90)`}>
              <ValveGlyph v={v} size={11} actuator={false} />
              <line x1={-11} y1={11} x2={9} y2={-9} stroke={col} strokeWidth={1.6} />
              <polygon points="11,-11 4,-9 9,-4" fill={col} />
            </g>
            <rect x={c.x + 12} y={c.y + 4} width={8} height={12} rx={1} fill={col} />
            <line x1={c.x + 7} y1={c.y + 10} x2={c.x + 12} y2={c.y + 10} stroke={col} strokeWidth={1.4} />
          </Clickable>
        );
      }
      default: {
        // gate, master, wing, swab, annulus, crossover, service-line, scssv, injection valves
        const v = elById.get(id) as RestrictionSnapshot | undefined;
        if (!v) return null;
        const sel = selEl === id;
        const a = aliasOf(state, v.tag);
        const small = c.type === "injection_valve";
        const s = small ? 10 : 12;
        return (
          <Clickable key={c.id} id={c.id} label={`${displayTag(state, v.tag)} ${v.name}`} selected={sel} testid={`valve-${v.tag}`} onClick={() => onSelect({ type: "element", id })}>
            <rect x={c.x - s - 8} y={c.y - s - 10} width={2 * s + 16} height={2 * s + 16} fill="transparent" />
            {sel && <rect x={c.x - s - 7} y={c.y - s - 9} width={2 * s + 14} height={2 * s + 14} fill="none" stroke={COLORS.accent} strokeWidth={1.5} strokeDasharray="3 2" />}
            <g transform={`translate(${c.x} ${c.y}) rotate(${c.rotation})`}>
              <ValveGlyph v={v} size={s} />
            </g>
            {v.leaking && <circle cx={c.x} cy={c.y} r={s + 4} fill="none" stroke={XT.fault} strokeWidth={1.5} className="leak-pulse" />}
            {c.label && <TagLabel x={c.x + c.label.dx} y={c.y + c.label.dy} text={displayTag(state, v.tag)} anchor={c.label.anchor} status={a?.status} selected={sel} />}
            {v.moving && (
              <text x={c.x} y={c.y + s + 14} textAnchor="middle" fontSize={8.5} fontWeight={700} fill={XT.moving} className="num">
                {fmt(v.position_pct, 0)}→{fmt(v.commanded_pct, 0)} %
              </text>
            )}
          </Clickable>
        );
      }
    }
  };

  return (
    <div className="relative h-full w-full">
      <svg ref={svgRef} viewBox={`${box.x} ${box.y} ${box.w} ${box.h}`} preserveAspectRatio="xMidYMid meet" role="img" data-testid="xt-schematic"
        aria-label={`${L.title} Christmas tree workstation (simulated)`} className={`h-full w-full select-none ${vb ? "cursor-grab active:cursor-grabbing" : ""}`}
        onClick={() => onSelect(null)} {...handlers}>
        <defs>
          <pattern id="xtgrid" width="26" height="26" patternUnits="userSpaceOnUse">
            <path d="M 26 0 L 0 0 0 26" fill="none" stroke={SCH.grid} strokeWidth="1" />
          </pattern>
          <filter id="xtsoft" x="-10%" y="-10%" width="120%" height="130%">
            <feDropShadow dx="0" dy="1" stdDeviation="1.2" floodColor="#0f172a" floodOpacity="0.10" />
          </filter>
        </defs>
        <rect width={L.width} height={L.height} fill="#fbfcfe" />
        <rect width={L.width} height={L.height} fill="url(#xtgrid)" />

        {/* groups */}
        {L.groups.map((g) => (
          <g key={g.id} pointerEvents="none">
            {g.frame && <rect x={g.x} y={g.y} width={g.w} height={g.h} rx={4} fill={g.id === "additions" ? "#f8fafc" : "none"} stroke="#94a3b8" strokeWidth={1} strokeDasharray={g.id === "additions" ? "6 4" : undefined} />}
            <text x={g.x + 6} y={g.y + (g.frame ? 14 : -4)} fontSize={g.frame ? 10.5 : 9} fontWeight={600} fill={g.frame ? XT.ink : "#94a3b8"} letterSpacing={g.frame ? 0 : 1}>
              {g.frame ? g.label : g.label.toUpperCase()}
            </text>
          </g>
        ))}

        {/* annotations */}
        {L.annotations.map((a, i) => {
          if (a.type === "title")
            return <text key={i} x={a.x} y={a.y} textAnchor="middle" fontSize={17} fontWeight={700} fill={XT.ink} pointerEvents="none">{a.text}</text>;
          if (a.type === "bar")
            return <rect key={i} x={a.x} y={a.y} width={a.w} height={a.h} rx={2} fill="#475569" pointerEvents="none"><title>{a.label}</title></rect>;
          if (a.type === "body")
            return <rect key={i} x={a.x} y={a.y} width={a.w} height={a.h} rx={2} fill="#a08a5c" fillOpacity={0.55} stroke="#7c6a45" strokeWidth={1} pointerEvents="none"><title>{a.label}</title></rect>;
          if (a.type === "manifold")
            return (
              <g key={i} pointerEvents="none">
                <rect x={a.x} y={a.y} width={a.w} height={a.h} rx={4} fill="#e2e8f0" stroke="#64748b" />
                <text x={(a.x ?? 0) + (a.w ?? 0) / 2} y={(a.y ?? 0) + (a.h ?? 0) / 2 + 4} textAnchor="middle" fontSize={10.5} fontWeight={700} fill={XT.ink} letterSpacing={1}>{a.label}</text>
              </g>
            );
          return null;
        })}

        {/* flow lines */}
        {L.lines.map((ln) => {
          const flowing = lineFlowing(ln);
          const isChem = !!ln.chemical;
          const base = XT.line[ln.cls];
          const active = isChem && flowing;
          const color = active ? chemColor[ln.chemical!] ?? base : base;
          const w = ln.cls === "production" ? 5 : ln.cls === "annulus" || ln.cls === "service" ? 4 : ln.cls === "hydraulic" ? 3.5 : 2.6;
          const path = d(ln.points);
          const sel = isChem && selChem === ln.chemical;
          return (
            <g key={ln.id} data-testid={`line-${ln.id}`} data-flowing={flowing}>
              <path d={path} stroke="#ffffff" strokeWidth={w + 3} fill="none" strokeLinejoin="round" />
              <path d={path} stroke={color} strokeWidth={w} fill="none" strokeLinejoin="round" strokeOpacity={flowing ? 1 : 0.42}
                className={isChem ? "cursor-pointer" : undefined}
                onClick={isChem ? (e) => { e.stopPropagation(); onSelect({ type: "chemical", id: ln.chemical! }); } : undefined} />
              {sel && <path d={path} stroke={COLORS.accent} strokeWidth={1.4} strokeDasharray="4 3" fill="none" pointerEvents="none" transform="translate(4 -4)" />}
              {flowing && dynamic && ln.cls !== "hydraulic" && (
                <path d={path} stroke="#ffffff" strokeOpacity={0.9} strokeWidth={Math.max(1, w / 3)} fill="none" strokeDasharray="2 16" className="flow-dash" pointerEvents="none" />
              )}
            </g>
          );
        })}

        {/* connectors */}
        {L.connectors.map((k) => {
          const rot = { left: 180, right: 0, up: -90, down: 90 }[k.direction];
          const [kk, cid] = ref(k.model);
          const clickable = kk === "chemical";
          const injecting = clickable && chemSnap[cid]?.status === "injecting";
          // labels: left connectors above the line (page edge), right connectors beyond the tip, down connectors to the left
          const vRight = k.label_side === "right";
          const lx = k.direction === "left" ? k.x - 14 : k.direction === "right" ? k.x + 20 : vRight ? k.x + 10 : k.x - 10;
          const ly = k.direction === "down" ? k.y + 16 : k.direction === "up" ? k.y - 10 : k.direction === "left" ? k.y - 10 : k.y + 3.5;
          const anchor = k.direction === "right" || k.direction === "left" || vRight ? "start" : "end";
          const body = (
            <>
              <g transform={`translate(${k.x} ${k.y}) rotate(${rot})`}>
                <polygon points="0,-6 10,-6 16,0 10,6 0,6" fill={injecting ? chemColor[cid] ?? XT.panel : XT.panel} stroke="#475569" strokeWidth={1.2} strokeLinejoin="round" />
              </g>
              <text x={lx} y={ly} textAnchor={anchor} fontSize={9.5} fontWeight={600} fill="#475569">{k.label}</text>
            </>
          );
          return clickable ? (
            <Clickable key={k.id} id={k.id} label={`${k.label} injection controls`} selected={selChem === cid} testid={`connector-${k.id}`} onClick={() => onSelect({ type: "chemical", id: cid })}>
              {body}
            </Clickable>
          ) : (
            <g key={k.id} pointerEvents="none">{body}</g>
          );
        })}

        {/* components */}
        {L.components.map(component)}

        <Legend x={24} y={L.height - 180} chems={state.chemical_config ?? []} />
        <text x={10} y={16} fontSize={9.5} fontWeight={700} fill={COLORS.partial} letterSpacing={1.4}>SIMULATED VALUES — TRAINING ONLY</text>
      </svg>
      <div className="absolute right-2 top-2 flex flex-col gap-1" aria-label="Schematic zoom">
        {([
          ["+", "Zoom in", () => zoom(1 / 1.4)],
          ["−", "Zoom out", () => zoom(1.4)],
          ["⤢", "Fit", reset],
        ] as [string, string, () => void][]).map(([l, t, f]) => (
          <button key={t} type="button" title={`${t} (wheel to zoom, drag to pan, double-click to fit)`} aria-label={t} onClick={f}
            className="h-6 w-6 rounded-sm border border-line-strong bg-panel/90 text-[13px] leading-none text-muted hover:text-accent">
            {l}
          </button>
        ))}
      </div>
    </div>
  );
}

function Legend({ x, y, chems }: { x: number; y: number; chems: { id: string; name: string; color: string }[] }) {
  const valves: [string, string, boolean][] = [["Open", XT.open, true], ["Closed", XT.closed, true], ["Throttling / moving", XT.partial, false]];
  const lines: [string, string][] = [["Production", XT.line.production], ["Annulus / service", XT.line.annulus], ["Chemical (idle)", XT.line.chemical], ["Control hydraulics", XT.line.hydraulic]];
  return (
    <g transform={`translate(${x} ${y})`} pointerEvents="none" data-testid="xt-legend">
      <rect width={228} height={168} rx={4} fill={XT.panel} fillOpacity={0.97} stroke="#cbd5e1" filter="url(#xtsoft)" />
      <text x={10} y={15} fontSize={9.5} fontWeight={700} fill={XT.ink}>LEGEND (reference HMI colours)</text>
      {valves.map(([l, c, solid], i) => (
        <g key={l} transform={`translate(${16 + (i % 2) * 104} ${32 + Math.floor(i / 2) * 16})`}>
          <polygon points="-7,-4.5 -7,4.5 0,0" fill={solid ? c : "none"} stroke={c} strokeWidth={1.4} />
          <polygon points="7,-4.5 7,4.5 0,0" fill={solid ? c : "none"} stroke={c} strokeWidth={1.4} />
          <text x={13} y={3.5} fontSize={9.5} fill={XT.ink}>{l}</text>
        </g>
      ))}
      {lines.map(([l, c], i) => (
        <g key={l} transform={`translate(${10 + (i % 2) * 108} ${70 + Math.floor(i / 2) * 15})`}>
          <line x1={0} y1={0} x2={16} y2={0} stroke={c} strokeWidth={4} />
          <text x={21} y={3.5} fontSize={9} fill={XT.ink}>{l}</text>
        </g>
      ))}
      <g transform="translate(10 104)">
        <line x1={0} y1={0} x2={16} y2={0} stroke={XT.line.production} strokeWidth={4} />
        <text x={21} y={3.5} fontSize={9} fill={XT.ink}>Flowing</text>
        <line x1={70} y1={0} x2={86} y2={0} stroke={XT.line.production} strokeWidth={4} strokeOpacity={0.42} />
        <text x={91} y={3.5} fontSize={9} fill={XT.ink}>No flow / isolated</text>
      </g>
      <g transform="translate(10 122)">
        <text x={0} y={3.5} fontSize={8.5} fill={COLORS.muted}>Injecting:</text>
        {chems.map((c, i) => (
          <g key={c.id} transform={`translate(${48 + i * 44} 0)`}>
            <line x1={0} y1={0} x2={10} y2={0} stroke={c.color} strokeWidth={4} />
            <text x={13} y={3.5} fontSize={8.5} fill={XT.ink}>{c.id === "methanol" ? "MeOH" : c.id === "corrosion_inhibitor" ? "CI" : c.id === "wax_inhibitor" ? "Wax" : c.id === "biocide" ? "Bio" : c.id}</text>
          </g>
        ))}
      </g>
      <g transform="translate(10 140)">
        <rect x={0} y={-6} width={20} height={11} rx={2} fill="none" stroke="#94a3b8" strokeDasharray="1.5 1.5" />
        <text x={25} y={3} fontSize={8.5} fill={XT.ink}>tag uncertain</text>
        <rect x={100} y={-6} width={20} height={11} rx={2} fill="none" stroke="#94a3b8" strokeDasharray="3 2" />
        <text x={125} y={3} fontSize={8.5} fill={XT.ink}>SubseaSim addition</text>
      </g>
      <text x={10} y={160} fontSize={8} fill={COLORS.muted}>Arrangement traced from the reference page; values simulated.</text>
    </g>
  );
}

export const XtSchematic = memo(XtSchematicInner);
