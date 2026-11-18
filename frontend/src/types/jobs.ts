/** Background job (backend app/jobs.py). */
export type JobState = "pending" | "running" | "completed" | "failed" | "cancelled";

export interface Job {
  id: string;
  session_id: string;
  kind: string;
  label: string;
  params: Record<string, unknown>;
  state: JobState;
  progress: number;
  message: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  result: Record<string, unknown> | null;
  error: string | null;
  wall_s: number;
}

export const jobActive = (j: Job | null | undefined) => !!j && (j.state === "pending" || j.state === "running");
