/**
 * Visual state conventions (single source of truth for schematic + legend).
 * NOTE: site HMI colour conventions differ (some use red = open). These are
 * SubseaSim training conventions and are shown in the schematic legend.
 */
import type { ElementState, RestrictionSnapshot } from "@/types/simulation";

export const COLORS = {
  open: "#22c55e",
  closed: "#ef4444",
  partial: "#f59e0b",
  moving: "#f59e0b",
  fault: "#d946ef",
  flow: "#22d3ee",
  static: "#5b6b80",
  trapped: "#a78bfa",
  line: "#2f4357",
  fg: "#d6dee8",
  muted: "#7d8da1",
  panel: "#0d141c",
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

export function pipeColor(state: ElementState | undefined, trapped: boolean): string {
  if (trapped) return COLORS.trapped;
  if (state === "flowing") return COLORS.flow;
  return COLORS.static;
}
