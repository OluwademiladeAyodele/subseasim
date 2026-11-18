import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
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

describe("API RP 14E screening on the choke health page", () => {
  it("lists Ve against the simulated mixture velocity per location and warns when sand is present", async () => {
    current = base();
    const { ChokeHealthPage } = await import("@/pages/ChokeHealthPage");
    render(<ChokeHealthPage />);
    const ev = current.sand_choke!.erosional_velocity!;
    const outlet = ev.locations!.find((r) => r.key === "outlet")!;
    expect(screen.getByTestId("api14e-outlet")).toHaveTextContent(fmt(outlet.ve_m_s, 2));
    expect(screen.getByTestId("api14e-status")).toHaveTextContent(ev.any_exceeded ? "Above Ve" : "Below Ve");
    expect(ev.sand_present).toBe(true);
    expect(screen.getByText(/C must be reduced/)).toBeInTheDocument();
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

  it("trends the measured sand history and flags the abnormal increase from the backend", async () => {
    current = base();
    const { SandPage } = await import("@/pages/SandPage");
    render(<SandPage />);
    const h = current.sand_choke!.measured_history!;
    expect(h.count).toBe(5);
    expect(screen.getByTestId("abnormal-status")).toHaveTextContent("ABNORMAL INCREASE");
    expect(screen.getByTestId("abnormal-text")).toHaveTextContent(h.abnormal.text);
    expect(screen.getByRole("img", { name: "Measured sand rate history" })).toBeInTheDocument();
    expect(screen.getByText(/Predictive mode: history trended and checked/)).toBeInTheDocument();
  });
});

describe("Measured sand history inputs", () => {
  it("exports the records as CSV that the backend importer accepts", async () => {
    const { toCsv } = await import("@/pages/MeasuredSandPanel");
    const rows = base().sand_choke_inputs!.sand.measurements;
    const csv = toCsv(rows);
    expect(csv.split("\n")[0]).toBe("timestamp,value,unit,method,uncertainty_pct,liquid_rate_sm3_d,water_cut,d10_um,d50_um,d90_um,note");
    expect(csv.trim().split("\n").length).toBe(rows.length + 1);
    expect(csv).toContain("acoustic_detector");
  });

  it("imports a CSV file and edits a record in the draft", async () => {
    current = base();
    const sandCsv = vi.fn().mockResolvedValue(true);
    Object.assign(actions, { sandCsv });
    const { SandInputsPage } = await import("@/pages/SandInputsPage");
    render(<SandInputsPage />);
    expect(screen.getByTestId("measurement-table").querySelectorAll("tbody tr").length).toBe(5);
    const file = new File(["timestamp,value,unit\n2025-06-01,3,kg/d\n"], "sand.csv", { type: "text/csv" });
    await userEvent.upload(screen.getByTestId("sand-csv-file"), file);
    await waitFor(() => expect(sandCsv).toHaveBeenCalledWith("timestamp,value,unit\n2025-06-01,3,kg/d\n", false));
    const v = screen.getByLabelText("measurement 1 value");
    await userEvent.clear(v);
    await userEvent.type(v, "2.5");
    expect(screen.getByTestId("sand-csv-import")).toBeDisabled(); // unsaved draft: import blocked
    // removing a row shifts the next record's value into the cell
    const second = current.sand_choke_inputs!.sand.measurements[1].value;
    await userEvent.click(screen.getByRole("button", { name: "remove measurement 2" }));
    expect(screen.getByLabelText("measurement 2 value")).toHaveValue(String(current.sand_choke_inputs!.sand.measurements[2].value));
    expect(second).not.toBe(current.sand_choke_inputs!.sand.measurements[2].value);
    await userEvent.click(screen.getByTestId("sand-inputs-save"));
    expect(actions.sandInputs.mock.calls.at(-1)![0].sand.measurements[0].value).toBe(2.5);
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
