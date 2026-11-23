# Intern training curriculum

Nine guided exercises teach interns to operate the subsea Christmas tree
workstation. Each exercise:

- loads its own scenario, on the tree workstation;
- judges every task from the **simulation state**, not from button clicks;
- resolves every prediction from what the intern's **own run** did;
- writes every review from the readings recorded in that run.

Nothing numerical is pre-written.

Code: `backend/app/training/exercises/` (`common.py` holds the shared
helpers) and `registry.py`. UI: **Training** page.

## The exercises

| # | Exercise | Scenario | What the intern does and sees |
|---|---|---|---|
| 1 | Workstation familiarisation | `xt_230xp22b` | A tour of the tree: bore, wing, choke, annulus, chemical lines and hydraulics. Tags and transmitters (PTT panels, 0xx–4xx numbering), live values, valve colours and the speed control. Opens the swab valve: PT-105 equalises with the cavity, then stays trapped after SV-101 closes |
| 2 | Well start-up from shut-in | `training_startup` (all closed) | SCSSV → PMV → PWV. The cavity equalises with the bore; the closed choke holds the full differential (PDT-101). Methanol for a cold start. Cracks the choke 10 / 20 / 30 %: flow starts, wellhead pressure falls, drawdown rises, the tree warms from about 5 °C |
| 3 | Choke operation | `ex03_choke_operation` (quasi-steady, choke 20 %) | Choke 20 → 40 → 80 %. Flow is not proportional to opening; the pressure budget explains why |
| 4 | Shut-in and pressure build-up | `xt_230xp22b` | Choke → PWV → PMV → SCSSV. Wellhead pressure rises, downstream falls to the flowline, the cavity is trapped, bottom-hole pressure builds up over an hour |
| 5 | Chemical injection | `xt_230xp22b` | Methanol via CIV-301 (FT-301). The front reaches AT-511, 2.5 km away, only after the transit time. Metering valve and lower tree pressure each raise the injection rate |
| 6 | Annulus monitoring and bleed-off | `xt_230xp22b` | Reads PT-401, opens AMV (PT-402 equalises), bleeds through AWV to the service-line pressure, isolates, watches 2 h (thermal effect versus leak); sustained casing pressure |
| 7 | Integrated production, sand and choke health | `training_integrated` (three-phase) | MPFM, sanding onset, transport, SDT-101, erosion, wear and remaining life, maintenance recommendation |
| 8 | Leak test of the production master valve | `training_leaking_pmv` | Stops flow, closes PMV, bleeds and traps the cavity, runs an inflow test from the Integrity tests page. The PMV fails (seat leak); the intern interprets leak rate and thermal correction, and decides the next step |
| 9 | Control hydraulics and loss of supply | `xt_230xp22b` | HSV-101 closed: SCM B keeps the valves open (redundancy). LP trip: PMV and PWV fail closed, the choke fails as-is, the SCSSV (HP) stays open. Restores LP and brings the well back |

## Teaching notes

**Exercise speed.** Exercises 1, 2 and 4–6 and 8–9 run on the single-phase
workstation: about 3.5 s of computing per simulated hour, so 60–300× is
responsive. Exercise 7 uses the three-phase model.

**Choke steps.** The choke moves on its actuator step grid (165 steps), so
10 % becomes 10.3 %. Tasks accept the position the actuator actually goes
to.

**Trapped pressures.** A closed cavity keeps whatever pressure it had. In
Exercise 2 the trapped cavity may be above or below the bore pressure; the
prediction asks for *equalisation*, which is what always happens.

**Column separation in Exercise 4.** Between the closed SCSSV and PMV, the
tubing cools and its liquid contracts. Its pressure falls to the bubble
point (gas comes out of solution) and stays there with a
`COLUMN_SEPARATION` warning, until the valves are reopened and the void
refills. See `DYNAMIC_SIMULATION_MODEL.md`.

**Acceptance limits.** Integrity-test limits and health thresholds are
illustrative training values, not a standard.

## Verification

`backend/tests/test_curriculum.py` plays every new exercise to the end, the
way an intern operates the workstation. It checks:

- every task completes;
- every prediction and question resolves;
- every review renders with real values;
- the physics each exercise teaches, for example:
  - the start-up equalisation and differentials;
  - the shut-in build-up and trapped cavity;
  - the chemical transport delay and rate dependence;
  - the annulus bleed to the service line;
  - the leaking PMV failing, and a tight PMV passing, the same test;
  - the hydraulic fail-safe and redundancy.

`test_training_integrated.py` covers Exercise 7, and `test_api_and_training.py`
covers Exercise 3. The end-to-end test drives Exercise 2 through the real UI.
