import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { BlackOilPanel } from "@/controls/BlackOilPanel";
import { KeyMeasurements } from "@/instrumentation/KeyMeasurements";
import { fmt } from "@/lib/units";
import type { SimulationState } from "@/types/simulation";

import mpFixture from "./test/fixtures/mp_state.json";

// Real three-phase snapshot exported from the backend engine.
const base = () => structuredClone(mpFixture) as unknown as SimulationState;
const prefs = { pressureRef: "bara" as const, flowUnit: "m3/d" as const };

const actions = { blackOil: vi.fn().mockResolvedValue(true), fluidModel: vi.fn().mockResolvedValue(true) };
let current = base();
vi.mock("@/app/context", () => ({ useWorkstation: () => ({ state: current, actions, prefs }) }));
vi.mock("@/app/PageBody", () => ({ PageBody: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }));

describe("Multiphase page", () => {
  it("shows standard-condition phase rates, the node table, flow patterns and the mass balance from the model", async () => {
    current = base();
    const { MultiphasePage } = await import("@/pages/MultiphasePage");
    render(<MultiphasePage />);
    const mp = current.multiphase!;
    expect(screen.getByTestId("multiphase-page")).toBeInTheDocument();
    expect(screen.getByTestId("mp-oil-Arriving at the manifold")).toHaveTextContent(fmt(mp.rates_arrival.oil_sm3_d, 0));
    expect(screen.getByTestId("mp-oil-Entering the well (sandface)")).toHaveTextContent(fmt(mp.rates_reservoir.oil_sm3_d, 0));
    const rows = screen.getByTestId("mp-node-table").querySelectorAll("tbody tr");
    expect(rows.length).toBe(mp.nodes.length);
    expect(screen.getByTestId("pattern-strip")).toBeInTheDocument();
    expect(screen.getByTestId("mp-balance")).toHaveTextContent("Surface gas");
  });

  it("offers the fluid-model switch when the three-phase model is off", async () => {
    current = { ...base(), multiphase: null, fluid_model: "single_phase" };
    const { MultiphasePage } = await import("@/pages/MultiphasePage");
    render(<MultiphasePage />);
    await userEvent.click(screen.getByTestId("fluid-model-black_oil"));
    expect(actions.fluidModel).toHaveBeenCalledWith("black_oil");
  });
});

describe("BlackOilPanel", () => {
  it("sends validated black-oil inputs (water cut in % -> fraction)", async () => {
    const s = base();
    const onBlackOil = vi.fn().mockResolvedValue(true);
    render(<BlackOilPanel state={s} onBlackOil={onBlackOil} onFluidModel={vi.fn()} />);
    const wc = screen.getByLabelText("Water cut");
    await userEvent.clear(wc);
    await userEvent.type(wc, "45");
    await userEvent.click(screen.getByRole("button", { name: "Apply fluid" }));
    expect(onBlackOil).toHaveBeenCalledWith(expect.objectContaining({ water_cut: 0.45, producing_gor_sm3_sm3: 120 }));
    await userEvent.clear(wc);
    await userEvent.type(wc, "150");
    expect(screen.getByRole("button", { name: "Apply fluid" })).toBeDisabled();
    await userEvent.click(screen.getByTestId("correlation-no_slip"));
    expect(onBlackOil).toHaveBeenLastCalledWith({ correlation: "no_slip" });
  });
});

describe("KeyMeasurements (three-phase)", () => {
  it("shows oil / gas / water at standard conditions", () => {
    const s = base();
    render(<KeyMeasurements state={s} prefs={prefs} />);
    expect(screen.getByTestId("kpi-phases")).toHaveTextContent("Sm³/d oil");
    expect(screen.getByTestId("kpi-flow")).toHaveTextContent("reservoir volume");
  });
});
