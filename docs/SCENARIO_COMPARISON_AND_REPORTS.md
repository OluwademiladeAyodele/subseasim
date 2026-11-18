# Scenario comparison and engineering reports

Code: `backend/app/studies/comparison.py` (study), `backend/app/reports/report.py`
(report), job kind `scenario_comparison` (`app/job_kinds.py`). UI: the
**Scenario comparison** page, and report links on **Simulation records**.

## Scenario comparison

**Purpose.** Compare operating options before acting: different choke
openings, reservoir or manifold pressures, water cut, GOR, sand rates, grain
sizes and trim materials. Every case is calculated with the same models as
the live session, so the differences come from physics, not from different
assumptions.

### Method: steady twins

1. **Base twin.** A separate engine in the steady model receives the
   session's current state:
   - every valve and choke position;
   - the boundary conditions;
   - the black-oil fluid;
   - the sand and choke inputs;
   - the trim's accumulated wear (hole growth, plug and wall loss, service
     time, cumulative sand and production, wear log).
2. **Each case.** The case starts from a copy of the base twin and its
   changes are applied:
   - the choke goes to the requested opening, on the actuator's step grid;
   - a sand rate is imposed as a measured value;
   - a D50 scales D10 and D90 by the same ratio, keeping the spread;
   - a trim material means **a new trim of that material**, so wear starts
     from zero. Every other case starts from the current wear.
3. **Steady operating point.** One steady solve gives the operating point:
   the multiphase flow (Beggs & Brill, Sachdeva choke), the sanding onset and
   rate, the erosion rates, and the cavitation and API 14E screening.
4. **Wear over the horizon.** Wear is integrated quasi-steadily over the
   horizon (0–3650 days) at that operating point, using the same fast-forward
   as the live session.
5. **Results.** For each case the study reports:
   - production (oil, gas, water);
   - choke ΔP, drawdown and the sanding risk index;
   - sand at the choke and jet velocity;
   - hole-wear rate;
   - health, governing allowance used and P10/P50/P90 remaining life after
     the horizon;
   - first limit, cavitation and API 14E ratio.

   The page shows each value with its difference from the base. Green means
   better, red means worse, for quantities with a clear direction.

**The live session is never touched.** A test checks that its time,
positions, wear, model and event log are unchanged.

**Why steady, not dynamic.** After an operating change, the dynamic model
approaches steady state over hours of simulated time. Two hours take about
40 s of computing per case, and the result is still drifting. Comparing
settled steady operating points is the standard way to compare options. The
transient between them is studied in the live session.

**Check.** The steady twin matches the settled dynamic session to within 1 %
on oil rate (observed 0.07 %).

**Performance.** About 1 s to build the twin, then about 1 s plus the wear
integration per case. Five cases over 365 days take about 9 s, run as a
background job (see `BACKGROUND_JOBS.md`). The longest single step, the twin
build, holds the event loop for about 1 s.

### Limitations

- Steady operating points only; transients between settings are not
  included.
- Conditions are constant over the horizon: no depletion, no water-cut trend,
  no sand-rate trend.
- **Chemical-injection variants are not offered.** Injection is modelled in
  the dynamic model only.
- Every model limitation of the live session applies.

## Engineering reports

`GET /api/records/{id}/report` returns a self-contained HTML document built
**only from the stored record**. The same record always gives the same
report. Print it to PDF from the browser; `?download=true` saves the HTML
file.

**Sections**

1. Simulation configuration
2. Reservoir fluid properties
3. Production conditions
4. Valve and choke states
5. Pressure, temperature and flow readings
6. Multiphase flow meter (indicated vs true, uncertainty)
7. Sand production (onset, rates, PSD, detector, measured history)
8. Choke erosion and remaining life
9. Cavitation and flashing screening, with API RP 14E
10. Component health and maintenance assessment (why, actions, confidence)
11. Operating history and inspections
12. Scenario comparison (when attached)
13. Data provenance
14. Methods and model versions
15. Uncertainty
16. Model assumptions and limitations

**Validation status.** The report opens with the validation status and the
data classification, for example "Verified models, not field-validated" and
"ILLUSTRATIVE – not field data", so a printed report cannot be mistaken for
a validated assessment.

**Escaping.** All text is HTML-escaped. This includes labels, notes and
variant names; a label such as `<script>` is shown as text.

**Attaching a comparison.** Save a record with
`comparison_job_id` set to a completed `scenario_comparison` job of the same
session. Only a completed comparison of that session can be attached.

**Records schema 2.** Version 2 adds a `has_comparison` column. Version-1
databases are migrated in place when first opened, and their records are
kept.

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/sessions/{sid}/jobs` `{kind: "scenario_comparison", params: {variants, horizon_days, base_label?}}` | Run a study (202; 409 with the reason if invalid) |
| POST | `/api/sessions/{sid}/records` `{label, notes?, comparison_job_id?}` | Save a record, optionally with the comparison |
| GET | `/api/records/{id}/report[?download=true]` | Engineering report (HTML) |

## Verification

`backend/tests/test_comparison_report.py` checks:

- the twin carries every part of the session state, and matches the settled
  dynamic session;
- the live session is unchanged by a study;
- the physical direction of each change (choke opening, water cut);
- wear carry-over versus a new trim;
- the actuator step grid;
- invalid studies are rejected before they run;
- every report section is present, and text is escaped;
- the v1 database migration;
- the full API: job, attachment and report.

`frontend/src/comparison.test.tsx` uses a real study result. The end-to-end
test runs a study, saves it and opens the report.
