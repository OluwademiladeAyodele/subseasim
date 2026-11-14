/**
 * Display-unit conversions. Mirrors backend app/core/units.py (tested on both
 * sides). Internal values are SI; pressure is ABSOLUTE Pa.
 */

export const P_ATM_PA = 101_325; // standard atmosphere: gauge reference
export const PA_PER_BAR = 1e5;
export const K_OFFSET = 273.15;
export const S_PER_DAY = 86_400;
export const M3_PER_BBL = 0.158987294928;

export type PressureRef = "bara" | "barg";
export type FlowUnit = "m3/d" | "m3/h" | "bbl/d";

export const paToBara = (p: number) => p / PA_PER_BAR;
export const baraToPa = (p: number) => p * PA_PER_BAR;
export const paToBarg = (p: number) => (p - P_ATM_PA) / PA_PER_BAR;
export const bargToPa = (p: number) => p * PA_PER_BAR + P_ATM_PA;
export const paToBarDelta = (dp: number) => dp / PA_PER_BAR;

export function pressureFromPa(p: number, ref: PressureRef): number {
  return ref === "bara" ? paToBara(p) : paToBarg(p);
}
export function pressureToPa(v: number, ref: PressureRef): number {
  return ref === "bara" ? baraToPa(v) : bargToPa(v);
}

export const kToC = (t: number) => t - K_OFFSET;
export const cToK = (t: number) => t + K_OFFSET;

export const FLOW_LABEL: Record<FlowUnit, string> = { "m3/d": "m³/d", "m3/h": "m³/h", "bbl/d": "bbl/d" };

export function flowFromM3s(q: number, unit: FlowUnit): number {
  switch (unit) {
    case "m3/d":
      return q * S_PER_DAY;
    case "m3/h":
      return q * 3600;
    case "bbl/d":
      return (q * S_PER_DAY) / M3_PER_BBL;
  }
}

/** Productivity index: (m3/s)/Pa <-> (m3/d)/bar */
export const piSiToField = (j: number) => j * S_PER_DAY * PA_PER_BAR;
export const piFieldToSi = (j: number) => j / S_PER_DAY / PA_PER_BAR;

export const pasToCp = (mu: number) => mu * 1000;
export const cpToPas = (mu: number) => mu / 1000;

export function fmt(v: number | null | undefined, digits = 1): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  return v.toFixed(digits);
}

export function formatSimTime(s: number): string {
  const total = Math.floor(s);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const sec = total % 60;
  const pad = (n: number) => n.toString().padStart(2, "0");
  return `${pad(h)}:${pad(m)}:${pad(sec)}`;
}

/** Convert an instrument's SI value to its display unit. */
export interface DisplayPrefs {
  pressureRef: PressureRef;
  flowUnit: FlowUnit;
}

export function instrumentDisplay(
  type: string,
  valueSi: number | null,
  prefs: DisplayPrefs,
): { value: number | null; unit: string; digits: number } {
  if (valueSi === null) {
    const unit = unitLabel(type, prefs);
    return { value: null, unit, digits: 1 };
  }
  switch (type) {
    case "pressure":
      return { value: pressureFromPa(valueSi, prefs.pressureRef), unit: prefs.pressureRef, digits: 1 };
    case "differential_pressure":
      return { value: paToBarDelta(valueSi), unit: "bar", digits: 2 };
    case "temperature":
      return { value: kToC(valueSi), unit: "°C", digits: 1 };
    case "flow":
      return { value: flowFromM3s(valueSi, prefs.flowUnit), unit: FLOW_LABEL[prefs.flowUnit], digits: 0 };
    default:
      return { value: valueSi, unit: "", digits: 2 };
  }
}

export function unitLabel(type: string, prefs: DisplayPrefs): string {
  return (
    { pressure: prefs.pressureRef, differential_pressure: "bar", temperature: "°C", flow: FLOW_LABEL[prefs.flowUnit] }[type] ?? ""
  );
}
