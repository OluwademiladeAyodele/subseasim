# Choke maintenance decision support

Source: `backend/app/simulation/sand/system.py` (`_health`, `_confidence`,
`_recommendation`, `_cv_report`). Display: **Choke health** page.

## Health categories (configurable; not universal safety limits)

The governing criterion is the one with the largest fraction of its allowance
consumed. Default thresholds, editable on the inputs page:

| Category | Condition |
|---|---|
| Normal | < 25 % consumed, no elevated indicators |
| Elevated erosion risk | < 25 % consumed **and** (cage-hole growth rate > 1 mm/yr **or** drawdown above the critical sanding drawdown) |
| Increased wear | ≥ 25 % |
| Inspection recommended | ≥ 50 % |
| Changeout assessment required | ≥ 75 % |
| Critical condition | ≥ 90 % |
| Unavailable | no criterion can be evaluated: the missing inputs are listed |

Category changes are written to the event log as alarms (warning or error).

## Recommendation

Each recommendation contains:

- **Title**, from the category.
- **Text.** It states why: the governing criterion and its consumption, the
  sanding state, the jet velocity and sand at the choke, the first limit and
  its P10–P90 life at the current conditions, and the Cv-tracking result.
- **Suggested actions.** For example: confirm the sand rate, reduce drawdown or
  differential, plan an inspection, record the inspection to calibrate, or
  prepare a changeout.
- **Disclaimer.** It is decision support, not an automatic changeout
  instruction: review vendor limits and inspection evidence.

## Measured Cv tracking (independent wear indicator)

**Effective capacity from measurements** (MPFM mass flow and the choke
upstream and downstream pressure transmitters):

    ratio = W_measured / W_expected(new-trim C_dA at the same step, Sachdeva, measured p₁, p₂)

**Sampling.** Once per 10 simulated minutes, only when the process is quasi-
steady (|dP/dt| < 200 Pa/s), because the MPFM is at the manifold.

**Uncertainty (k = 2).** The MPFM mass-flow uncertainty combined with a 2 %
allowance for PVT and transmitter error.

**Interpretation.** A sustained deviation beyond the uncertainty is
significant.

| Ratio | Candidate causes |
|---|---|
| > 1 | trim erosion; MPFM over-reading; position / LVDT error; fluid change |
| < 1 | partial plugging (sand, scale, hydrate, wax); MPFM under-reading; position error |

**Not every deviation is erosion.** The page lists the alternatives first.

## Fast-forward and operating history

**Operating history.** Entered history periods (monthly averages) pre-load
the wear from installation to "now". Inspections inside that history
calibrate the model.

**Fast-forward N days.** Integrates wear and cumulative sand and production at
the current operating point. It is quasi-steady and logged as such. It lets a
training session explore months of service.

## Limitations

- The thresholds are site practice. Defaults are illustrative.
- Remaining-life figures assume today's conditions continue. The sand-based
  and liquid-based remaining amounts remove that time assumption.
- Cv tracking needs a GOOD MPFM reading and steady operation. It cannot
  separate several simultaneous causes without further evidence (well test,
  inspection).

## Verification

`backend/tests/test_sand_choke.py`:

- categories progress in order to "Critical condition" with configurable
  thresholds, with recommendation, reasons and disclaimer, and alarm events;
- Cv tracking detects feedback-raised Cv as significant, and erosion is listed
  among the causes.

`frontend/src/sand.test.tsx`: rendering of the health page, the recommendation,
the criteria, confidence, fast-forward and the unavailable-inputs case.
