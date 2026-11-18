import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { fmt } from "@/lib/units";
import { XtSchematic } from "@/schematic/XtSchematic";
import type { SimulationState } from "@/types/simulation";

import sandFixture from "./test/fixtures/sand_state.json";

// Real snapshot (illustrative inputs, well producing sand, 60 days of trim wear) from the backend.
const base = () => structuredClone(sandFixture) as unknown as SimulationState;
const prefs = { pressureRef: "bara" as const, flowUnit: "m3/d" as const };
const actions = { sandInputs: vi.fn().mockResolvedValue(true), sandExample: vi.fn().mockResolvedValue(true), sandFastForward: vi.fn().mockResolvedValue(true) };
const go = vi.fn();
let current = base();
vi.mock("@/app/context", () => ({ useWorkstation: () => ({ state: current, actions, prefs, go, sim: { samples: [] } }) }));
vi.mock("@/app/PageBody", () => ({ PageBody: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }));

describe("Choke health page", () => {
  it("shows the health category, reasoned recommendation, wear criteria with life ranges and confidence", async () => {
    current = base();
    const { ChokeHealthPage } = await import("@/pages/ChokeHealthPage");
    render(<ChokeHealthPage />);
    const r = current.sand_choke!;
    expect(screen.getByTestId("health-category")).toHaveTextContent(r.health!.category);
    expect(screen.getByTestId("recommendation")).toHaveTextContent(r.recommendation!.title);
    expect(screen.getByTestId("confidence")).toHaveTextContent(r.confidence!.category);
    const hole = r.criteria!.find((c) => c.key === "hole")!;
    expect(screen.getByTestId("criterion-hole")).toHaveTextContent(fmt(hole.used, 3));
    expect(screen.getByTestId("criterion-hole")).toHaveTextContent("P50");
  });

  it("fast-forwards operating time and links to the inputs", async () => {
    current = base();
    const { ChokeHealthPage } = await import("@/pages/ChokeHealthPage");
    render(<ChokeHealthPage />);
    await userEvent.click(screen.getByTestId("fast-forward"));
    expect(actions.sandFastForward).toHaveBeenCalledWith(90);
    await userEvent.click(screen.getByRole("button", { name: "Edit inputs / inspections" }));
    expect(go).toHaveBeenCalledWith("sandinputs");
  });

  it("lists the missing inputs instead of predicting when data are absent", async () => {
    current = base();
    current.sand_choke = { ...current.sand_choke!, health: { category: "Unavailable", consumed_fraction: null, reasons: [], note: "" },
      inputs_status: { choke: { complete: false, missing: ["trim material"] } } };
    const { ChokeHealthPage } = await import("@/pages/ChokeHealthPage");
    render(<ChokeHealthPage />);
    expect(screen.getByTestId("unavailable")).toHaveTextContent("trim material");
  });
});

describe("Sand source on the choke health page", () => {
  it("shows the onset and the sand rates from the formation to the choke", async () => {
    current = base();
    const { ChokeHealthPage } = await import("@/pages/ChokeHealthPage");
    render(<ChokeHealthPage />);
    const s = current.sand_choke!.sand!;
    expect(screen.getByTestId("sand-source")).toBeInTheDocument();
    expect(screen.getByTestId("risk-index")).toHaveTextContent(fmt(s.onset!.risk_index, 2));
    expect(screen.getByTestId("sand-produced")).toHaveTextContent(fmt(s.produced_kg_d, 2));
    expect(screen.getByTestId("sand-choke")).toHaveTextContent(fmt(s.at_choke_kg_d, 2));
    expect(screen.queryByText(/detector/i)).toBeNull();
  });
});

describe("Sand & choke inputs page", () => {
  it("edits a value and saves the full input set", async () => {
    current = base();
    const { SandInputsPage } = await import("@/pages/SandInputsPage");
    render(<SandInputsPage />);
    const f = screen.getByTestId("in-max-hole");
    await userEvent.clear(f);
    await userEvent.type(f, "0.9");
    await userEvent.click(screen.getByTestId("sand-inputs-save"));
    const sent = actions.sandInputs.mock.calls.at(-1)![0];
    expect(sent.acceptance.max_hole_diameter_increase_mm).toBe(0.9);
    expect(sent.choke.hole_rows.length).toBe(current.sand_choke_inputs!.choke.hole_rows.length);
    await userEvent.click(screen.getByTestId("sand-load-example"));
    expect(actions.sandExample).toHaveBeenCalled();
  });
});

describe("Tree workstation without a sand detector", () => {
  it("draws no sand detector on the schematic", () => {
    const s = base();
    render(<XtSchematic state={s} schematic={s.schematic!} selection={null} onSelect={() => {}} onNavigate={() => {}} prefs={prefs} />);
    expect(screen.queryByTestId("sand-detector")).toBeNull();
    expect(screen.queryByTestId("panel-XT3001")).toBeNull();
  });
});
