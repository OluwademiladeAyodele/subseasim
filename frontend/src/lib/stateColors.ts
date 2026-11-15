/**
 * Visual state conventions (single source of truth for schematic + legend).
 * NOTE: site HMI colour conventions differ (some use red = open). These are
 * SubseaSim training conventions and are shown in the schematic legend.
 */
import type { ElementState, RestrictionSnapshot } from "@/types/simulation";

export const COLORS = {
  open: "#16a34a",
  closed: "#dc2626",
  partial: "#d97706",
  moving: "#d97706",
  fault: "#c026d3",
  flow: "#0891b2",
  static: "#a8b3c2",
  trapped: "#7c3aed",
  annulus: "#0d9488",
  line: "#cbd5e1",
  fg: "#1e293b",
  muted: "#64748b",
  panel: "#ffffff",
  accent: "#0369a1",
  rise: "#ea580c",
  fall: "#2563eb",
  ref: "#64748b",
} as const;

/** Schematic canvas palette (light P&ID style). */
export const SCH = {
  bg: "#ffffff",
  bg2: "#f8fafc",
  grid: "#eef1f5",
  boxFill: "#f1f5f9",
  boxStroke: "#cbd5e1",
  seabed: "#b9a684",
  subsurface: "#f6f0e6",
  bubble: "#ffffff",
  valueBox: "#f8fafc",
  valueText: "#0f172a",
  pipeOutline: "#ffffff",
  arrow: "#ffffff",
  selected: "#e0f2fe",
} as const;

export type ValveVisual = "open" | "closed" | "partial" | "moving" | "fault";

export function valveVisual(v: RestrictionSnapshot): ValveVisual {
  if (!v.available) return "fault";
  if (v.moving) return "moving";
  if (v.position_pct <= 0) return "closed";
  if (v.position_pct >= 100) return "open";
  return "partial";
}

export const VALVE_LABEL: Record<ValveVisual, string> = {
  open: "OPEN",
  closed: "CLOSED",
  partial: "THROTTLING",
  moving: "MOVING",
  fault: "UNAVAILABLE",
};

/** Flowing colour of a branch subsystem by its fluid zone. */
export function zoneColor(zone: string | undefined, chemColors: Record<string, string>): string {
  if (!zone || zone === "production") return COLORS.flow;
  if (zone === "annulus") return COLORS.annulus;
  return chemColors[zone] ?? COLORS.flow;
}

export function pipeColor(state: ElementState | undefined, trapped: boolean, flowingColor: string = COLORS.flow): string {
  if (trapped) return COLORS.trapped;
  if (state === "flowing") return flowingColor;
  return COLORS.static;
}
