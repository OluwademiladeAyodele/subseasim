import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { fmt } from "@/lib/units";
import type { StudyResult } from "@/types/comparison";
import type { SimulationState } from "@/types/simulation";

import sandFixture from "./test/fixtures/sand_state.json";
import studyFixture from "./test/fixtures/study.json";

// Real study result computed by the backend (app/studies/comparison.py).
const study = studyFixture as unknown as StudyResult;
const job = (state: string, result: unknown = null) => ({ id: "job-1", session_id: "sid-1", kind: "scenario_comparison", label: "Scenario comparison: 3 cases over 365 days",
  params: {}, state, progress: state === "completed" ? 1 : 0.3, message: state, created_at: "", started_at: "", finished_at: null, result, error: null, wall_s: 3 });
const actions = {
  startJob: vi.fn().mockResolvedValue(job("running")),
  jobStatus: vi.fn().mockResolvedValue(job("completed", study)),
  cancelJob: vi.fn(),
};
const api = vi.hoisted(() => ({ saveRecord: vi.fn() }));
vi.mock("@/services/api", () => ({ api }));
vi.mock("@/app/context", () => ({
  useWorkstation: () => ({ state: sandFixture as unknown as SimulationState, actions, sim: { sessionId: "sid-1" } }),
}));
vi.mock("@/app/PageBody", () => ({ PageBody: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }));

describe("Scenario comparison page", () => {
  it("runs the study as a background job and shows every case with its difference from the base", async () => {
    const { ComparisonPage } = await import("@/pages/ComparisonPage");
    render(<ComparisonPage />);
    // edit the second case: water cut entered in %, sent as a fraction
    await userEvent.type(screen.getByLabelText("case 2 Water cut"), "50");
    await userEvent.click(screen.getByTestId("run-comparison"));
    expect(actions.startJob).toHaveBeenCalledWith("scenario_comparison", {
      variants: [{ label: "Choke 45 %", choke_pct: 45 }, { label: "Choke 60 %", choke_pct: 60, water_cut: 0.5 }], horizon_days: 365,
    });
    const table = await screen.findByTestId("comparison-results");
    const [base, , c60] = study.cases;
    expect(within(table).getByText("Choke 60 %")).toBeInTheDocument();
    expect(screen.getByTestId(`cell-${c60.id}-Oil Sm³/d`)).toHaveTextContent(fmt(c60.now.oil_sm3_d, 0));
    expect(screen.getByTestId(`cell-${base.id}-Oil Sm³/d`)).toHaveTextContent(fmt(base.now.oil_sm3_d, 0));
    // the difference from the base is shown (more oil = better = green)
    const diff = c60.now.oil_sm3_d! - base.now.oil_sm3_d!;
    expect(screen.getByTestId(`cell-${c60.id}-Oil Sm³/d`)).toHaveTextContent(`+${fmt(diff, 0)}`);
    expect(screen.getByTestId(`cell-${c60.id}-Health after horizon`)).toHaveTextContent(c60.after_horizon.health!);
    expect(screen.getByText(study.limitations[0])).toBeInTheDocument();
  });

  it("saves the comparison with a record and links the report", async () => {
    api.saveRecord.mockResolvedValue({ id: "rec-9", label: "Choke options" });
    const { ComparisonPage } = await import("@/pages/ComparisonPage");
    render(<ComparisonPage />);
    await userEvent.click(screen.getByTestId("run-comparison"));
    await screen.findByTestId("comparison-results");
    await userEvent.type(screen.getByLabelText("Comparison record label"), "Choke options");
    await userEvent.click(screen.getByTestId("save-comparison"));
    expect(api.saveRecord).toHaveBeenCalledWith("sid-1", "Choke options", null, "job-1");
    await waitFor(() => expect(screen.getByTestId("comparison-report-link")).toHaveAttribute("href", "/api/records/rec-9/report"));
  });

  it("removing a case keeps the other cases' values in their rows", async () => {
    const { ComparisonPage } = await import("@/pages/ComparisonPage");
    render(<ComparisonPage />);
    await userEvent.click(screen.getByRole("button", { name: "remove case 1" }));
    expect(screen.getByLabelText("case 1 label")).toHaveValue("Choke 60 %");
    expect(screen.getByLabelText("case 1 Choke")).toHaveValue("60");
  });

  it("shows why a study was rejected", async () => {
    actions.startJob.mockResolvedValueOnce("variants.0.trim_material: unknown trim material 'cheese'");
    const { ComparisonPage } = await import("@/pages/ComparisonPage");
    render(<ComparisonPage />);
    await userEvent.click(screen.getByTestId("run-comparison"));
    expect(await screen.findByTestId("comparison-error")).toHaveTextContent("unknown trim material");
  });
});
