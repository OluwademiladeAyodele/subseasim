import { describe, expect, it } from "vitest";

import {
  bargToPa,
  flowFromM3s,
  formatSimTime,
  instrumentDisplay,
  kToC,
  paToBara,
  paToBarg,
  piFieldToSi,
  piSiToField,
  pressureFromPa,
  pressureToPa,
} from "./units";

describe("pressure conversions", () => {
  it("keeps absolute and gauge explicit", () => {
    expect(paToBara(250e5)).toBeCloseTo(250);
    expect(paToBarg(101_325)).toBeCloseTo(0);
    expect(bargToPa(0)).toBeCloseTo(101_325);
    expect(paToBarg(100e5)).toBeCloseTo(100 - 1.01325, 10);
  });
  it("round-trips through either reference", () => {
    for (const ref of ["bara", "barg"] as const) {
      expect(pressureFromPa(pressureToPa(60, ref), ref)).toBeCloseTo(60, 10);
    }
  });
});

describe("other conversions (mirror backend app/core/units.py)", () => {
  it("temperature", () => expect(kToC(368.15)).toBeCloseTo(95));
  it("flow", () => {
    expect(flowFromM3s(1, "m3/d")).toBe(86_400);
    expect(flowFromM3s(1, "m3/h")).toBe(3600);
    expect(flowFromM3s(0.158987294928 / 86_400, "bbl/d")).toBeCloseTo(1, 10);
  });
  it("productivity index", () => {
    expect(piSiToField(piFieldToSi(20))).toBeCloseTo(20, 10);
    expect(piFieldToSi(20)).toBeCloseTo(20 / 86_400 / 1e5, 20);
  });
  it("sim time format", () => expect(formatSimTime(3725.9)).toBe("01:02:05"));
});

describe("instrumentDisplay", () => {
  const prefs = { pressureRef: "bara" as const, flowUnit: "m3/d" as const };
  it("converts by instrument type", () => {
    expect(instrumentDisplay("pressure", 60e5, prefs)).toMatchObject({ value: 60, unit: "bara" });
    expect(instrumentDisplay("differential_pressure", 5e5, prefs)).toMatchObject({ value: 5, unit: "bar" });
    expect(instrumentDisplay("temperature", 273.15, prefs).value).toBeCloseTo(0);
  });
  it("never invents a value for a missing measurement", () => {
    expect(instrumentDisplay("pressure", null, prefs).value).toBeNull();
  });
});
