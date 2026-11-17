import type { ExerciseSummary, ScenarioInfo, SessionPayload, SimMode, ValveCommand } from "@/types/simulation";

/** Scenario a brand-new session starts with (dynamic model, full system). */
export const DEFAULT_SCENARIO = "xt_230xp22b_multiphase";

export interface IntegrityTestRequest {
  type: "pressure_hold" | "inflow" | "stroke";
  name?: string;
  test_node?: string | null;
  transmitter?: string | null;
  valve?: string | null;
  stabilisation_s?: number;
  duration_s?: number;
  max_change_bar?: number;
  stroke_tolerance_pct?: number;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

function detailMessage(body: unknown): string {
  if (body && typeof body === "object" && "detail" in body) {
    const d = (body as { detail: unknown }).detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d)) {
      return d
        .map((e) => {
          const loc = Array.isArray(e?.loc) ? e.loc.filter((x: unknown) => x !== "body").join(".") : "";
          return `${loc ? loc + ": " : ""}${e?.msg ?? "invalid value"}`;
        })
        .join("; ");
    }
  }
  return "request failed";
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  const json = text ? JSON.parse(text) : null;
  if (!res.ok) throw new ApiError(res.status, detailMessage(json));
  return json as T;
}

export const api = {
  scenarios: () => request<ScenarioInfo[]>("GET", "/api/scenarios"),
  exercises: () => request<ExerciseSummary[]>("GET", "/api/training/exercises"),
  createSession: (scenario_id = DEFAULT_SCENARIO) => request<SessionPayload>("POST", "/api/sessions", { scenario_id }),
  getSession: (sid: string) => request<SessionPayload>("GET", `/api/sessions/${sid}`),
  lifecycle: (sid: string, action: "start" | "pause" | "resume" | "reset") =>
    request<SessionPayload>("POST", `/api/sessions/${sid}/lifecycle`, { action }),
  speed: (sid: string, time_scale: number) => request<SessionPayload>("POST", `/api/sessions/${sid}/speed`, { time_scale }),
  mode: (sid: string, mode: SimMode) => request<SessionPayload>("POST", `/api/sessions/${sid}/mode`, { mode }),
  loadScenario: (sid: string, scenario_id: string) =>
    request<SessionPayload>("POST", `/api/sessions/${sid}/scenario`, { scenario_id }),
  valve: (sid: string, tag: string, command: ValveCommand, position_pct?: number) =>
    request<SessionPayload>("POST", `/api/sessions/${sid}/valves/${encodeURIComponent(tag)}`, {
      command,
      ...(position_pct !== undefined ? { position_pct } : {}),
    }),
  selector: (sid: string, tag: string, command: "open" | "close") =>
    request<SessionPayload>("POST", `/api/sessions/${sid}/hydraulics/selectors/${encodeURIComponent(tag)}`, { command }),
  supply: (sid: string, id: string, available: boolean) =>
    request<SessionPayload>("POST", `/api/sessions/${sid}/hydraulics/supplies/${encodeURIComponent(id)}`, { available }),
  blackOil: (sid: string, body: Record<string, number | string>) => request<SessionPayload>("PUT", `/api/sessions/${sid}/black-oil`, body),
  fluidModel: (sid: string, model: "single_phase" | "black_oil") => request<SessionPayload>("POST", `/api/sessions/${sid}/fluid-model`, { model }),
  pump: (sid: string, chem: string, body: { running?: boolean; discharge_pressure_pa?: number }) =>
    request<SessionPayload>("POST", `/api/sessions/${sid}/chemicals/${encodeURIComponent(chem)}`, body),
  integrityStart: (sid: string, body: IntegrityTestRequest) => request<SessionPayload>("POST", `/api/sessions/${sid}/integrity/tests`, body),
  integrityAbort: (sid: string, id: number) => request<SessionPayload>("POST", `/api/sessions/${sid}/integrity/tests/${id}/abort`),
  boundary: (sid: string, body: Record<string, number>) => request<SessionPayload>("PUT", `/api/sessions/${sid}/boundary`, body),
  fluid: (sid: string, body: Record<string, number>) => request<SessionPayload>("PUT", `/api/sessions/${sid}/fluid`, body),
  trainingStart: (sid: string, exercise_id: string) =>
    request<SessionPayload>("POST", `/api/sessions/${sid}/training/start`, { exercise_id }),
  trainingAnswer: (sid: string, step_id: string, choice: string) =>
    request<SessionPayload>("POST", `/api/sessions/${sid}/training/answer`, { step_id, choice }),
  trainingAdvance: (sid: string) => request<SessionPayload>("POST", `/api/sessions/${sid}/training/advance`),
  trainingStop: (sid: string) => request<SessionPayload>("POST", `/api/sessions/${sid}/training/stop`),
};

export type Api = typeof api;
