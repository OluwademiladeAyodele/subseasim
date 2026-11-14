import { describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ComponentPanel } from "@/controls/ComponentPanel";
import { ConditionsPanel } from "@/controls/ConditionsPanel";
import { EventLog } from "@/dashboard/EventLog";
import { InstrumentTable } from "@/instrumentation/InstrumentTable";
import { KeyMeasurements } from "@/instrumentation/KeyMeasurements";
import { TreeSchematic } from "@/schematic/TreeSchematic";
import { TrainingPanel } from "@/training/TrainingPanel";
import type { SimulationState, TrainingState } from "@/types/simulation";

import stateFixture from "./test/fixtures/state.json";
import trainingFixture from "./test/fixtures/training_prediction.json";

// Fixtures are real snapshots exported from the backend engine.
const base = () => structuredClone(stateFixture) as unknown as SimulationState;
const prefs = { pressureRef: "bara" as const, flowUnit: "m3/d" as const };

describe("TreeSchematic", () => {
  it("renders every configured valve and instrument and reports selection", async () => {
    const s = base();
    const onSelect = vi.fn();
    render(<TreeSchematic state={s} layout={s.layout!} selection={null} onSelect={onSelect} prefs={prefs} />);
    for (const tag of ["SCSSV-101", "PMV-101", "PWV-101", "CHK-101"]) expect(screen.getByTestId(`valve-${tag}`)).toBeInTheDocument();
    for (const i of s.instruments) expect(screen.getByTestId(`inst-${i.tag}`)).toBeInTheDocument();
    await userEvent.click(screen.getByTestId("valve-CHK-101"));
    expect(onSelect).toHaveBeenCalledWith({ type: "element", id: "CHOKE" });
    expect(screen.getByText(/SIMULATED VALUES/)).toBeInTheDocument();
  });

  it("shows closed state from the model, not from local UI state", () => {
    const s = base();
    const pwv = s.elements.find((e) => e.id === "PWV")!;
    Object.assign(pwv, { position_pct: 0, commanded_pct: 0, moving: false });
    render(<TreeSchematic state={s} layout={s.layout!} selection={null} onSelect={() => {}} prefs={prefs} />);
    expect(within(screen.getByTestId("valve-PWV-101")).getByText("CLOSED")).toBeInTheDocument();
  });
});

describe("ComponentPanel", () => {
  it("choke offers position control and sends set_position", async () => {
    const onCommand = vi.fn().mockResolvedValue(true);
    render(<ComponentPanel state={base()} selection={{ type: "element", id: "CHOKE" }} prefs={prefs} onCommand={onCommand} />);
    const input = screen.getByLabelText(/Set position/);
    await userEvent.clear(input);
    await userEvent.type(input, "45");
    await userEvent.click(screen.getByRole("button", { name: "Apply" }));
    expect(onCommand).toHaveBeenCalledWith("CHK-101", "set_position", 45);
  });

  it("isolation valve offers only open/close", async () => {
    const onCommand = vi.fn().mockResolvedValue(true);
    render(<ComponentPanel state={base()} selection={{ type: "element", id: "PMV" }} prefs={prefs} onCommand={onCommand} />);
    expect(screen.queryByLabelText(/Set position/)).toBeNull();
    expect(screen.getByText(/OPEN \/ CLOSE only/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(onCommand).toHaveBeenCalledWith("PMV-101", "close", undefined);
  });

  it("disables apply for an invalid position", async () => {
    render(<ComponentPanel state={base()} selection={{ type: "element", id: "CHOKE" }} prefs={prefs} onCommand={vi.fn()} />);
    const input = screen.getByLabelText(/Set position/);
    await userEvent.clear(input);
    await userEvent.type(input, "150");
    expect(screen.getByRole("button", { name: "Apply" })).toBeDisabled();
  });
});

describe("Measurement displays", () => {
  it("instrument table shows measured values with explicit pressure reference", () => {
    render(<InstrumentTable state={base()} prefs={prefs} />);
    const row = screen.getByTestId("row-PT-201");
    expect(within(row).getByText("60.0")).toBeInTheDocument();
    expect(within(row).getByText("bara")).toBeInTheDocument();
  });

  it("gauge preference converts with the 1.01325 bar offset", () => {
    render(<InstrumentTable state={base()} prefs={{ ...prefs, pressureRef: "barg" }} />);
    expect(within(screen.getByTestId("row-PT-201")).getByText("59.0")).toBeInTheDocument();
  });

  it("BAD readings show no number", () => {
    const s = base();
    const pt = s.instruments.find((i) => i.tag === "PT-101")!;
    Object.assign(pt, { value_si: null, pv_si: null, status: "BAD" });
    render(<InstrumentTable state={s} prefs={prefs} />);
    const row = screen.getByTestId("row-PT-101");
    expect(within(row).getByText("—")).toBeInTheDocument();
    expect(within(row).getByText("BAD")).toBeInTheDocument();
  });

  it("key measurements flag an invalid operating point instead of showing numbers", () => {
    const s = base();
    s.diagnostics = [{ severity: "error", code: "NEGATIVE_ABSOLUTE_PRESSURE", message: "x", location: null }];
    render(<KeyMeasurements state={s} prefs={prefs} />);
    expect(within(screen.getByTestId("kpi-flow")).getByText("INVALID")).toBeInTheDocument();
  });
});

describe("ConditionsPanel", () => {
  it("submits SI values converted from engineering units", async () => {
    const onBoundary = vi.fn().mockResolvedValue(true);
    render(<ConditionsPanel state={base()} prefs={prefs} onBoundary={onBoundary} onFluid={vi.fn()} />);
    const p = screen.getByLabelText("Reservoir pressure");
    await userEvent.clear(p);
    await userEvent.type(p, "400");
    await userEvent.click(screen.getByRole("button", { name: "Apply conditions" }));
    const body = onBoundary.mock.calls[0][0];
    expect(body.reservoir_pressure_pa).toBeCloseTo(400e5);
    expect(body.downstream_pressure_pa).toBeCloseTo(60e5);
  });

  it("blocks non-numeric input", async () => {
    render(<ConditionsPanel state={base()} prefs={prefs} onBoundary={vi.fn()} onFluid={vi.fn()} />);
    const p = screen.getByLabelText("Downstream (arrival) pressure");
    await userEvent.clear(p);
    expect(screen.getByRole("button", { name: "Apply conditions" })).toBeDisabled();
  });
});

describe("TrainingPanel", () => {
  it("records a prediction before allowing continue", async () => {
    const onAnswer = vi.fn();
    render(
      <TrainingPanel training={trainingFixture as unknown as TrainingState} exercises={[]} onStart={vi.fn()} onAnswer={onAnswer} onAdvance={vi.fn()} onStop={vi.fn()} />,
    );
    expect(screen.getByTestId("training-step-title")).toHaveTextContent("Predict");
    expect(screen.getByRole("button", { name: "Continue" })).toBeDisabled();
    await userEvent.click(screen.getByRole("radio", { name: /less than 1.8x/ }));
    await userEvent.click(screen.getByRole("button", { name: "Lock in prediction" }));
    expect(onAnswer).toHaveBeenCalledWith("p1", "b");
  });
});

describe("EventLog", () => {
  it("lists newest first", () => {
    render(
      <EventLog
        events={[
          { id: 1, sim_time_s: 0, wall_time: 0, category: "lifecycle", message: "first", component: null, severity: "info", detail: null },
          { id: 2, sim_time_s: 5, wall_time: 0, category: "operation", message: "second", component: "CHK-101", severity: "info", detail: null },
        ]}
      />,
    );
    const items = screen.getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("second");
  });
});
