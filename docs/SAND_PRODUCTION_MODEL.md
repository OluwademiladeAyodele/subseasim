# Sand production model

Source: `backend/app/simulation/sand/production.py`. Inputs:
`backend/app/models/sand.py`, edited in the app on the
**Sand & choke inputs** page.

## Principle: no made-up site data

Every site-specific input is optional. When an input is missing, the result
that depends on it reports **unavailable** and lists what is missing. It never
substitutes a value silently.

Some defaults are used but disclosed as *assumed*, and they lower the
confidence:

- Biot coefficient 1.0;
- Poisson ratio 0.25;
- stress-path coefficient 0.6;
- maximum horizontal stress equal to the minimum horizontal stress;
- initial reservoir pressure equal to the current pressure (no depletion
  effect).

The operator preset in `xt_230xp22b_multiphase` contains only the data the
operator supplied:

- completion: cased and perforated, with standalone sand screens;
- choke: plug and multi-hole cage, max Cv 161, minimum controllable Cv 1.61,
  165-step actuator.

A complete **illustrative** set ("Load illustrative example") exists for
training. It is labelled and is not field data.

## 1. Sanding onset: critical drawdown

The model treats perforation tunnels as cavities in a poro-elastic rock
(Willson, Moschovidis, Cameron and Palmer 2002, SPE 78168; Weingarten and
Perkins 1995).

**Failure condition.** The effective tangential stress at the tunnel wall,
with pore pressure equal to the flowing pressure P_w, is

    σ_t' = 3σ₁ − σ₃ − 2P_w − A (P_r − P_w),     A = α (1 − 2ν)/(1 − ν)

Failure occurs when σ_t' reaches the effective strength U. This gives:

    CBHFP = (3σ₁ − σ₃ − U − A P_r) / (2 − A)
    critical drawdown ΔP_c = P_r − CBHFP
    risk index r = (P_r − P_wf) / ΔP_c          (sanding when r > 1)

**Effective strength.**

- `U = 3.1 × TWC`, where TWC is the thick-walled-cylinder collapse strength
  (hollow cylinder, OD/ID = 3).
- The factor 3.1 scales the core test to perforation size (Willson et al.).
- If only UCS is available, `TWC = UCS × (site TWC/UCS ratio)`. Confidence is
  lower, and the ratio must come from the user, because no generic ratio is
  assumed.

**Stresses.**

- Overburden: `σ_v = gradient × TVD`.
- Minimum horizontal stress: `σ_h = gradient × TVD`.
- Depletion: `σ_h = σ_h,i − γ (P_r,i − P_r)`, where γ is the stress-path
  coefficient.
- The well is taken as vertical with horizontal perforations in the worst
  orientation: `σ₁ = max(σ_v, σ_h)` and `σ₃ = min(σ_v, σ_h)`.

**Water weakening.** `U × (1 − w × water cut)`. Water cut is used as a proxy
for near-wellbore water saturation; this is a documented simplification.

**Live inputs from the simulator.** P_r is the reservoir pressure,
P_wf is the bottomhole node pressure, and the water cut is taken from the
fluid entering the well.

**Expected responses (tested).** Stronger rock raises the critical drawdown.
Depletion and water both lower it.

## 2. Particle size

- The particle-size distribution is a log-normal fit to D50 and D10 and/or
  D90, in the cumulative **% finer** (passing) convention, which is stated in
  the UI.
- `σ = mean(ln(D90/D50), ln(D50/D10)) / 1.2816`.

## 3. Screens (cased and perforated with standalone screens)

**Retention.**

- Grains finer than `aperture / bridging_factor` pass the intact screen.
- The bridging factor is 1 for purely geometric retention; 2–3 when a stable
  sand bridge forms (default 2).
- Any damaged screen area passes the full distribution:

      passing fraction f = damage + (1 − damage) × F(aperture / bridging)

**Retained sand** is accumulated and reported.

**Not modelled:**

- screen plugging;
- hot-spot erosion of the screen;
- retention in a gravel pack (that completion type reports "unavailable").

## 4. Sand rate

**Measured / configured mode (preferred when data exist).** The entered value
is the sand produced at the wellhead, after the screens. Units, each with an
explicit basis:

| Unit | Basis |
|---|---|
| kg/h, kg/d, g/s | mass rate |
| pptb | lb of sand per 1000 bbl of liquid at standard conditions |
| ppm by mass of liquid | |
| ppm by mass of the total stream | |
| ppm by volume of liquid | standard conditions, using the grain density |

The 1-sigma uncertainty of the measurement is entered by the user.

**Predictive mode.** There is no universal equation for the sand rate after
onset. Observed rates vary by orders of magnitude with rock, completion and
history. The model therefore uses a **calibrated empirical** form:

    ṁ_formation = k · Q_liquid,reservoir · (r − 1)ⁿ   (r > 1; 0 below onset)
    ṁ_produced  = f · ṁ_formation

- k (kg/m³ at r = 2) must be calibrated from sand-trap, detector or well-test
  data.
- Without k the prediction is **unavailable**.
- The predicted rate carries a factor-5 uncertainty (90 % range) in the
  erosion forecast.

## 5. Limitations

- **Perforation model only.** The open-hole wellbore failure model, and
  orientation-specific perforation stresses, are not implemented.
- **No time-dependent behaviour.** Sand bursts, cumulative-damage hardening
  and softening, and rate-transient sanding are not represented.
- **Screens.** Retention is geometric plus bridging, with no particle
  mechanics.
- **Approximations.** Water weakening uses water cut as a saturation proxy.

## 6. Verification

`backend/tests/test_sand_choke.py` checks:

- the critical BHFP against a hand evaluation of the Willson et al. equation;
- the responses to strength, depletion and water;
- that missing and assumed inputs are reported;
- that the PSD quantiles are reproduced;
- screen retention, damage and no-screen cases;
- every measured-unit conversion against a hand calculation;
- a zero predicted rate below onset, and that the coefficient is required.

## References

- Willson, S.M., Moschovidis, Z.A., Cameron, J.R., Palmer, I.D. (2002) *New Model for Predicting the Rate of Sand Production*. SPE/ISRM 78168.
- Weingarten, J.S., Perkins, T.K. (1995) *Prediction of Sand Production in Gas Wells: Methods and Gulf of Mexico Case Studies*. JPT 47(7).
- Veeken, C.A.M. et al. (1991) *Sand Production Prediction Review: Developing an Integrated Approach*. SPE 22792.
- Bellarby, J. (2009) *Well Completion Design*, ch. 3 (sand control). Elsevier.
