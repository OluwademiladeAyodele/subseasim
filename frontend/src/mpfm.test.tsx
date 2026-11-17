import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { fmt } from "@/lib/units";
import { MPFMSummary } from "@/pages/MPFMPage";
import { XtSchematic } from "@/schematic/XtSchematic";
import type { SimulationState } from "@/types/simulation";

import mpFixture from "./test/fixtures/mp_state.json";

// Real three-phase snapshot (with the manifold MPFM) exported from the backend engine.
const base = () => structuredClone(mpFixture) as unknown as SimulationState;
const prefs = { pressureRef: "bara" as const, flowUnit: "m3/d" as const };
const actions = { mpfmFaults: vi.fn().mockResolvedValue(true), mpfmCalibrate: vi.fn().mockResolvedValue(true), fluidModel: vi.fn() };
let current = base();
vi.mock("@/app/context", () => ({ useWorkstation: () => ({ state: current, actions, prefs, sim: { samples: [] } }) }));
vi.mock("@/app/PageBody", () => ({ PageBody: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }));

describe("MPFM page", () => {
  it("shows measured next to true values with the meter's uncertainty", async () => {
    current = base();
    const { MPFMPage } = await import("@/pages/MPFMPage");
    render(<MPFMPage />);
    const m = current.mpfm!;
    expect(screen.getByTestId("mpfm-quality")).toHaveTextContent(m.quality);
    const oil = screen.getByTestId("mpfm-std-oil_sm3_d");
    expect(oil).toHaveTextContent(fmt(m.measured!.oil_sm3_d, 1));
    expect(oil).toHaveTextContent(fmt(m.true!.oil_sm3_d, 1));
    expect(oil).toHaveTextContent(`± ${fmt(m.uncertainty_pct!.oil_sm3_d, 1)} %`);
  });

  it("flags a PVT mismatch and sends calibration and fault commands", async () => {
    current = base();
    current.mpfm!.true_fluid!.water_salinity_wt_pct = 9.0;
    const { MPFMPage } = await import("@/pages/MPFMPage");
    render(<MPFMPage />);
    expect(screen.getByTestId("mpfm-pvt-mismatch")).toBeInTheDocument();
    await userEvent.click(screen.getByTestId("mpfm-calibrate"));
    expect(actions.mpfmCalibrate).toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Gamma detector failed inject" }));
    expect(actions.mpfmFaults).toHaveBeenCalledWith({ gamma_failed: true });
  });

  it("explains when the three-phase model is off", async () => {
    current = { ...base(), mpfm: { tag: "MPFM-201", quality: "NOT_MODELLED", reason: "needs the three-phase model." } };
    const { MPFMPage } = await import("@/pages/MPFMPage");
    render(<MPFMPage />);
    await userEvent.click(screen.getByRole("button", { name: "Switch to three-phase" }));
    expect(actions.fluidModel).toHaveBeenCalledWith("black_oil");
  });
});

describe("MPFM on the schematic and in the inspector", () => {
  it("draws the meter on the manifold line and selects it", async () => {
    const s = base();
    const onSelect = vi.fn();
    render(<XtSchematic state={s} schematic={s.schematic!} selection={null} onSelect={onSelect} onNavigate={() => {}} prefs={prefs} />);
    await userEvent.click(screen.getByTestId("mpfm-symbol"));
    expect(onSelect).toHaveBeenCalledWith({ type: "mpfm" });
  });

  it("summary shows the meter's phase rates and opens the page", async () => {
    const s = base();
    const onOpen = vi.fn();
    render(<MPFMSummary m={s.mpfm!} onOpen={onOpen} />);
    expect(screen.getByTestId("mpfm-summary")).toHaveTextContent(fmt(s.mpfm!.measured!.oil_sm3_d, 0));
    await userEvent.click(screen.getByRole("button", { name: "Open MPFM monitoring" }));
    expect(onOpen).toHaveBeenCalled();
  });
});
