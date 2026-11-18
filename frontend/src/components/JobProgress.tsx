/**
 * Progress of a background job: state, progress bar, message, cancel.
 * Polls the backend until the job is finished, then calls ``onFinished``.
 */
import { useEffect, useRef, useState } from "react";

import { useWorkstation } from "@/app/context";
import { Badge, Button } from "@/components/ui/primitives";
import { type Job, jobActive } from "@/types/jobs";

const TONE: Record<Job["state"], "info" | "ok" | "warn" | "bad" | "neutral"> = {
  pending: "neutral", running: "info", completed: "ok", cancelled: "warn", failed: "bad",
};

export function JobProgress({ job: initial, onFinished, pollMs = 400 }: { job: Job; onFinished?: (j: Job) => void; pollMs?: number }) {
  const { actions } = useWorkstation();
  const [job, setJob] = useState(initial);
  const done = useRef(false);
  useEffect(() => {
    setJob(initial);
    done.current = false;
  }, [initial]);
  useEffect(() => {
    if (!jobActive(job)) {
      if (!done.current) {
        done.current = true;
        onFinished?.(job);
      }
      return;
    }
    const t = setTimeout(() => {
      actions.jobStatus(job.id).then(setJob).catch(() => undefined);
    }, pollMs);
    return () => clearTimeout(t);
  }, [job, actions, pollMs, onFinished]);

  const pct = Math.round(job.progress * 100);
  return (
    <div className="mt-2 rounded-lg border border-line bg-panel-2 px-3 py-2 text-[12.5px]" data-testid="job-progress" data-state={job.state}>
      <div className="flex items-center gap-2">
        <Badge tone={TONE[job.state]} data-testid="job-state">{job.state}</Badge>
        <span className="min-w-0 flex-1 truncate font-medium">{job.label}</span>
        {jobActive(job) && (
          <Button size="xs" onClick={() => actions.cancelJob(job.id).then(setJob).catch(() => undefined)} data-testid="job-cancel">Cancel</Button>
        )}
      </div>
      <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-line" role="progressbar" aria-label={job.label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct}>
        <div className="h-full bg-accent transition-[width]" style={{ width: `${pct}%` }} />
      </div>
      <p className="mt-1 text-muted" data-testid="job-message">{job.error ?? job.message}{job.state !== "pending" && job.wall_s > 0 ? ` · ${job.wall_s.toFixed(1)} s` : ""}</p>
    </div>
  );
}
