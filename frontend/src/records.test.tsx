import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { RecordSummary, SimulationRecord } from "@/types/records";
import type { SimulationState } from "@/types/simulation";

import recordFixture from "./test/fixtures/record.json";
import sandFixture from "./test/fixtures/sand_state.json";

// Real record built and stored by the backend (app/storage).
const summary = recordFixture.summary as unknown as RecordSummary;
const record = recordFixture.record as unknown as SimulationRecord;

const api = vi.hoisted(() => ({
  listRecords: vi.fn(),
  getRecord: vi.fn(),
  saveRecord: vi.fn(),
  deleteRecord: vi.fn(),
}));
vi.mock("@/services/api", () => ({ api }));
vi.mock("@/app/context", () => ({
  useWorkstation: () => ({ state: sandFixture as unknown as SimulationState, sim: { sessionId: "sid-1" } }),
}));
vi.mock("@/app/PageBody", () => ({ PageBody: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }));

describe("Simulation records page", () => {
  it("lists saved records and shows provenance, methods and validation of the selected one", async () => {
    api.listRecords.mockResolvedValue([summary]);
    api.getRecord.mockResolvedValue(record);
    const { RecordsPage } = await import("@/pages/RecordsPage");
    render(<RecordsPage />);
    await userEvent.click(await screen.findByRole("button", { name: summary.label }));
    expect(api.getRecord).toHaveBeenCalledWith(summary.id);
    expect(await screen.findByTestId("record-validation")).toHaveTextContent(record.validation.overall);
    const prov = screen.getByTestId("record-provenance");
    expect(prov).toHaveTextContent("illustrative (not field data)");
    expect(prov).toHaveTextContent("simulated (model-calculated transmitter readings)");
    expect(screen.getByText(/choke erosion/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: `export ${summary.label}` })).toHaveAttribute("href", `/api/records/${summary.id}/export`);
  });

  it("saves the current assessment with a label and deletes a record", async () => {
    api.listRecords.mockResolvedValueOnce([]).mockResolvedValue([summary]);
    api.saveRecord.mockResolvedValue(summary);
    api.getRecord.mockResolvedValue(record);
    api.deleteRecord.mockResolvedValue(null);
    const { RecordsPage } = await import("@/pages/RecordsPage");
    render(<RecordsPage />);
    expect(await screen.findByTestId("records-empty")).toBeInTheDocument();
    expect(screen.getByTestId("record-save")).toBeDisabled(); // a label is required
    await userEvent.type(screen.getByLabelText("Record label"), "Baseline 30 %");
    await userEvent.type(screen.getByLabelText("Record notes"), "choke at 30 %");
    await userEvent.click(screen.getByTestId("record-save"));
    expect(api.saveRecord).toHaveBeenCalledWith("sid-1", "Baseline 30 %", "choke at 30 %");
    expect(await screen.findByTestId("record-detail")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: `delete ${summary.label}` }));
    await waitFor(() => expect(api.deleteRecord).toHaveBeenCalledWith(summary.id));
  });
});
