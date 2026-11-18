import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { HydraulicsPanel } from "@/controls/HydraulicsPanel";
import { XtSchematic, XT } from "@/schematic/XtSchematic";
import type { RestrictionSnapshot, SimulationState } from "@/types/simulation";

import xtFixture from "./test/fixtures/xt_state.json";

// Real snapshot of the xt_230xp22b scenario exported from the backend engine.
const base = () => structuredClone(xtFixture) as unknown as SimulationState;
const prefs = { pressureRef: "bara" as const, flowUnit: "m3/d" as const };

function renderXt(s: SimulationState, onSelect = vi.fn(), onNavigate = vi.fn()) {
  render(<XtSchematic state={s} schematic={s.schematic!} selection={null} onSelect={onSelect} onNavigate={onNavigate} prefs={prefs} />);
  return { onSelect, onNavigate };
}

describe("XtSchematic (Christmas tree workstation)", () => {
  it("draws every valve, check valve and reference panel as its own interactive component", () => {
    const s = base();
    renderXt(s);
    for (const e of s.elements) {
      if (e.kind === "valve" || e.kind === "choke") expect(screen.getByTestId(`valve-${(e as RestrictionSnapshot).tag}`)).toBeInTheDocument();
      if (e.kind === "check_valve") expect(screen.getByTestId(`check-${(e as { tag: string }).tag}`)).toBeInTheDocument();
    }
    for (const id of ["PTT-104", "PTT-107", "PT-404", "PDT-401", "PT-402", "PT-401", "PTT-001", "PTT-002", "PTT-103", "PTT-106", "SDT-101", "CHK-101-panel"])
      expect(screen.getByTestId(`panel-${id}`)).toBeInTheDocument();
    for (const t of ["HSV-101", "HSV-102", "HSV-103", "HSV-104"]) expect(screen.getByTestId(`selector-${t}`)).toBeInTheDocument();
    expect(screen.getByTestId("xt-legend")).toBeInTheDocument();
  });

  it("uses component positions from the layout file, not from available space", () => {
    const s = base();
    renderXt(s);
    const pmv = s.schematic!.components.find((c) => c.id === "PMV")!;
    const g = screen.getByTestId("valve-PMV-101").querySelector("g[transform]")!;
    expect(g.getAttribute("transform")).toContain(`translate(${pmv.x} ${pmv.y})`);
    const svg = screen.getByTestId("xt-schematic");
    expect(svg.getAttribute("viewBox")).toBe(`0 0 ${s.schematic!.width} ${s.schematic!.height}`);
  });

  it("shows plain engineering tags and reports selections", async () => {
    const s = base();
    const { onSelect, onNavigate } = renderXt(s);
    expect(screen.getAllByText("PMV-101").length).toBeGreaterThan(0);
    expect(screen.getAllByText("CHK-101").length).toBeGreaterThan(0);
    expect(screen.queryByText(/^[A-Z]+30\d\d$/)).toBeNull();
    await userEvent.click(screen.getByTestId("valve-PWV-101"));
    expect(onSelect).toHaveBeenLastCalledWith({ type: "element", id: "PWV" });
    await userEvent.click(screen.getByTestId("inst-PT-104"));
    expect(onSelect).toHaveBeenLastCalledWith({ type: "instrument", tag: "PT-104" });
    await userEvent.click(screen.getByTestId("selector-HSV-103"));
    expect(onSelect).toHaveBeenLastCalledWith({ type: "selector", tag: "HSV-103" });
    await userEvent.click(screen.getByTestId("connector-con-meoh"));
    expect(onSelect).toHaveBeenLastCalledWith({ type: "chemical", id: "methanol" });
    await userEvent.click(screen.getByTestId("btn-btn-scm-diagnostic"));
    expect(onNavigate).toHaveBeenCalledWith("diagnostics");
  });

  it("reflects the simulated state: closed valve colour, isolated flow path, live readings", () => {
    const s = base();
    const pwv = s.elements.find((e) => e.id === "PWV") as RestrictionSnapshot;
    Object.assign(pwv, { position_pct: 0, commanded_pct: 0, moving: false, state: "closed" });
    for (const id of ["CHOKE", "FL-101", "PMV", "TBG-UPPER", "TBG-LOWER"]) Object.assign(s.elements.find((e) => e.id === id)!, { state: "no_flow" });
    const pt = s.instruments.find((i) => i.tag === "PT-104")!;
    pt.value_si = 123.45e5;
    renderXt(s);
    const poly = screen.getByTestId("valve-PWV-101").querySelector("polygon")!;
    expect(poly.getAttribute("stroke")).toBe(XT.closed);
    expect(screen.getByTestId("line-wing").getAttribute("data-flowing")).toBe("false");
    expect(screen.getByTestId("inst-PT-104").textContent).toContain("123.5");
  });

  it("marks control-hydraulic lines unpowered below the operating minimum", () => {
    const s = base();
    const h = s.control_hydraulics!;
    h.headers.find((x) => x.id === "LP-A")!.pressure_pa = 50e5;
    renderXt(s);
    expect(screen.getByTestId("line-hyd-lp-a").getAttribute("data-flowing")).toBe("false");
    expect(screen.getByTestId("line-hyd-lp-b").getAttribute("data-flowing")).toBe("true");
  });
});

describe("HydraulicsPanel", () => {
  it("operates selector valves and the HPU supply", async () => {
    const s = base();
    const onSelector = vi.fn().mockResolvedValue(true);
    const onSupply = vi.fn().mockResolvedValue(true);
    render(<HydraulicsPanel state={s} prefs={prefs} focus="HSV-101" onSelector={onSelector} onSupply={onSupply} onSelect={() => {}} />);
    await userEvent.click(screen.getByRole("button", { name: "HSV-101 close" }));
    expect(onSelector).toHaveBeenCalledWith("HSV-101", "close");
    await userEvent.click(screen.getByRole("button", { name: "LP supply trip" }));
    expect(onSupply).toHaveBeenCalledWith("LP", false);
    expect(screen.getByTestId("supply-HP")).toHaveTextContent("SCSSV-101");
  });
});
