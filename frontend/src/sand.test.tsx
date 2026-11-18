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

describe("Cavitation screening on the choke health page", () => {
  it("shows the screening result from the backend, labelled as not CFD", async () => {
    current = base();
    const { ChokeHealthPage } = await import("@/pages/ChokeHealthPage");
    render(<ChokeHealthPage />);
    const c = current.sand_choke!.cavitation!;
    expect(screen.getByTestId("cavitation-risk")).toHaveTextContent(c.risk!);
    expect(screen.getByText(/not a CFD result/)).toBeInTheDocument();
    expect(screen.getByTestId("cavitation-sigma")).toHaveTextContent(fmt(c.water!.sigma, 2));
  });

  it("lists the missing valve data and links to the inputs", async () => {
    current = base();
    const c = current.sand_choke!.cavitation!;
    current.sand_choke = { ...current.sand_choke!, cavitation: { ...c, fl: null, vena_contracta_bara: null, risk: "Unavailable",
      missing: ["liquid pressure-recovery factor FL of the trim (manufacturer)"] } };
    const { ChokeHealthPage } = await import("@/pages/ChokeHealthPage");
    render(<ChokeHealthPage />);
    expect(screen.getByTestId("cavitation-missing")).toHaveTextContent("FL");
    await userEvent.click(screen.getByRole("button", { name: "Enter cavitation data" }));
    expect(go).toHaveBeenCalledWith("sandinputs");
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
  });
});

describe("Sand monitoring page", () => {
  it("shows the SDT-101 detector against the sand source", async () => {
    current = base();
    const { SandPage } = await import("@/pages/SandPage");
    render(<SandPage />);
    const r = current.sand_choke!;
    expect(screen.getByText(`Sand detector ${r.detector!.tag}`)).toBeInTheDocument();
    expect(r.detector!.tag).toBe("SDT-101");
    expect(screen.getByTestId("detector-status")).toHaveTextContent(r.detector!.alarm ? "ALARM" : r.detector!.status);
    expect(screen.getByTestId("detector-reading")).toHaveTextContent(fmt(r.detector!.reading_g_s, 3));
    expect(screen.getByTestId("sand-source")).toBeInTheDocument();
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

describe("SDT-101 on the schematic", () => {
  it("shows the live detector reading and opens sand monitoring", async () => {
    const s = base();
    const onNavigate = vi.fn();
    render(<XtSchematic state={s} schematic={s.schematic!} selection={null} onSelect={() => {}} onNavigate={onNavigate} prefs={prefs} />);
    const det = s.sand_choke!.detector!;
    expect(screen.getByTestId("panel-SDT-101")).toHaveTextContent(fmt(det.reading_g_s, 3));
    expect(screen.queryByTestId("panel-XT3001")).toBeNull();
    await userEvent.click(screen.getByTestId("sand-detector"));
    expect(onNavigate).toHaveBeenCalledWith("sand");
  });
});
