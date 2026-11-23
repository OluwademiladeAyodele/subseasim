import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { fmt } from "@/lib/units";
import type { Prediction, SurrogateCard, SurrogateSummary } from "@/types/surrogates";
import type { SimulationState } from "@/types/simulation";

import sandFixture from "./test/fixtures/sand_state.json";
import fx from "./test/fixtures/surrogate.json";

// Real surrogate trained by the backend on simulator cases (app/surrogates).
const summary = fx.summary as unknown as SurrogateSummary;
const card = fx.card as unknown as SurrogateCard;
const inside = fx.inside as unknown as Prediction;
const outside = fx.outside as unknown as Prediction;

const api = vi.hoisted(() => ({
  listSurrogates: vi.fn(), getSurrogate: vi.fn(), predictSurrogate: vi.fn(), checkSurrogate: vi.fn(),
  importSurrogate: vi.fn(), deleteSurrogate: vi.fn(),
}));
vi.mock("@/services/api", () => ({ api }));
const job = (state: string, result: unknown = null) => ({ id: "j1", session_id: "s", kind: "surrogate_build", label: "Train surrogate", params: {}, state,
  progress: state === "completed" ? 1 : 0.4, message: state, created_at: "", started_at: "", finished_at: null, result, error: null, wall_s: 1 });
const actions = { startJob: vi.fn(), jobStatus: vi.fn(), cancelJob: vi.fn() };
vi.mock("@/app/context", () => ({
  useWorkstation: () => ({ state: sandFixture as unknown as SimulationState, actions, sim: { sessionId: "sid-1" } }),
}));
vi.mock("@/app/PageBody", () => ({ PageBody: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }));

describe("Surrogate models page", () => {
  it("shows the model card with its status, cross-validation and envelope, and predicts with an interval", async () => {
    api.listSurrogates.mockResolvedValue([summary]);
    api.getSurrogate.mockResolvedValue(card);
    api.predictSurrogate.mockResolvedValue(inside);
    const { SurrogatesPage } = await import("@/pages/SurrogatesPage");
    render(<SurrogatesPage />);
    await userEvent.click(await screen.findByRole("button", { name: summary.name }));
    expect(await screen.findByTestId("surrogate-status")).toHaveTextContent("trained on simulator data (SubseaSim steady twins), not CFD or field data");
    expect(screen.getByTestId("surrogate-validation")).toHaveTextContent(fmt(card.validation.oil_sm3_d.loo_r2!, 3));
    expect(screen.getByRole("img", { name: "Leave-one-out parity plot" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId("surrogate-envelope")).toHaveTextContent("Inside the validated envelope"));
    const o = inside.outputs.oil_sm3_d;
    expect(screen.getByTestId("surrogate-prediction")).toHaveTextContent(`${fmt(o.p2_5, 3)} – ${fmt(o.p97_5, 3)}`);
  });

  it("flags a point outside the envelope and checks it against the simulator", async () => {
    api.listSurrogates.mockResolvedValue([summary]);
    api.getSurrogate.mockResolvedValue(card);
    api.predictSurrogate.mockResolvedValueOnce(inside).mockResolvedValue(outside);
    api.checkSurrogate.mockResolvedValue({ inputs: outside.inputs, envelope: outside.envelope, simulator: "SubseaSim steady twin",
      outputs: { oil_sm3_d: { surrogate: outside.outputs.oil_sm3_d.mean, std: 1, simulator: 1234.5, difference: 1, within_95: false },
                 jet_velocity_m_s: { surrogate: 1, std: 1, simulator: 2, difference: -1, within_95: true } } });
    const { SurrogatesPage } = await import("@/pages/SurrogatesPage");
    render(<SurrogatesPage />);
    await userEvent.click(await screen.findByRole("button", { name: summary.name }));
    const choke = await screen.findByLabelText("predict Choke opening");
    await userEvent.clear(choke);
    await userEvent.type(choke, "90");
    await userEvent.click(screen.getByTestId("surrogate-predict"));
    expect(api.predictSurrogate).toHaveBeenLastCalledWith(card.id, expect.objectContaining({ choke_pct: 90 }));
    await waitFor(() => expect(screen.getByTestId("surrogate-envelope")).toHaveTextContent("Outside the training range"));
    await userEvent.click(screen.getByTestId("surrogate-check"));
    expect(api.checkSurrogate).toHaveBeenCalledWith("sid-1", card.id, expect.objectContaining({ choke_pct: 90 }));
    expect(await screen.findByTestId("check-oil_sm3_d")).toHaveTextContent(fmt(1234.5, 3));
  });

  it("trains on simulator cases as a background job (water cut range entered in %, sent as a fraction)", async () => {
    api.listSurrogates.mockResolvedValue([]);
    api.getSurrogate.mockResolvedValue(card);
    api.predictSurrogate.mockResolvedValue(inside);
    actions.startJob.mockResolvedValue(job("running"));
    actions.jobStatus.mockResolvedValue(job("completed", { id: card.id }));
    const { SurrogatesPage } = await import("@/pages/SurrogatesPage");
    render(<SurrogatesPage />);
    expect(await screen.findByTestId("surrogates-empty")).toBeInTheDocument();
    await userEvent.click(screen.getByTestId("train-surrogate"));
    expect(actions.startJob).toHaveBeenCalledWith("surrogate_build", {
      name: "Choke response", method: "gp", bounds: { choke_pct: [20, 70], water_cut: [0.2, 0.5] },
      outputs: ["oil_sm3_d", "choke_dp_bar", "jet_velocity_m_s", "hole_rate_mm_y"], n_samples: 30,
    });
    await waitFor(() => expect(api.getSurrogate).toHaveBeenCalledWith(card.id)); // opens the new model when the job completes
  });
});
