# Background jobs

Code: `backend/app/jobs.py` (runner) and `backend/app/job_kinds.py` (job
types). UI: `frontend/src/components/JobProgress.tsx`, used for the
fast-forward on the Choke health page.

## Why

Some calculations are long. A 10-year choke-wear fast-forward takes about
11 s of computing. Run inside a request, it would stall the whole server:
every session, every WebSocket and the simulation loop. As a background job
it runs in small slices, so the workstation stays live and the job can be
cancelled.

## How it runs

The server runs every session on **one asyncio event loop without locks**
(`app/sessions.py`). Jobs keep that model and are cooperative:

- A job is a generator. Each `next()` does one small step of work (one
  simulated day of the fast-forward) and yields `(progress, message)`.
- The runner executes steps for at most 30 ms of wall time, then yields to
  the event loop. The simulation loop, the API and other jobs run in
  between.
- Jobs never run at the same time as the simulation. They need no locks,
  and they cannot see a half-updated engine.
- The fast-forward freezes its operating point at the start. Running in
  slices beside the live simulation therefore gives exactly the same wear as
  the synchronous fast-forward (tested to 1e-12).

## States

    pending → running → completed | failed | cancelled

- **Progress and message** are updated at every step. The session state is
  pushed to the browser every 0.5 s while the job runs, and once at the end.
- **Cancelled.** The work function reports what is kept. For the
  fast-forward, the days already integrated are kept, and the event log
  states it: "fast-forward STOPPED after 30 of 100 days (the days done are
  kept)".
- **Failed.** Any error, including a change of the sand / choke inputs during
  a fast-forward, ends the job with the reason. The server keeps running.
- **One active job per session.** A second job is rejected (409) until the
  first finishes or is cancelled.
- **Session ended.** A job whose session is removed is cancelled.
- The last 20 finished jobs of each session are kept for inspection.

## Job kinds

| Kind | Params | Result |
|---|---|---|
| `sand_fast_forward` | `days` (0, 3650] | service days before and after, choke health |

Add a kind with `jobs.register(kind, factory)`. The factory validates the
request (raising `JobRejected`) before anything is queued, and returns
`(label, generator)`.

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/sessions/{sid}/jobs` | `{kind, params}`: 202 with the job, or 409 with the reason |
| GET | `/api/sessions/{sid}/jobs` | Jobs of the session, newest first |
| GET | `/api/jobs/{id}` | One job (state, progress, message, result, error, wall time) |
| POST | `/api/jobs/{id}/cancel` | Request cancellation |

The synchronous `POST /api/sessions/{sid}/sand-choke/fast-forward` remains
for compatibility. The workstation uses the job.

## Verification

`backend/tests/test_jobs.py` checks:

- completion, progress, and that the event loop keeps running between
  slices;
- cancellation closes the work, and failure is reported;
- one job per session, independent sessions, and an unknown kind;
- a job stops when its session ends;
- the fast-forward job equals the synchronous fast-forward;
- cancelling keeps and logs the days done;
- changing the inputs mid-job stops it;
- requests are validated before they are queued;
- the full API.

The end-to-end test runs a 10-year job while the workstation stays live,
then cancels it.
