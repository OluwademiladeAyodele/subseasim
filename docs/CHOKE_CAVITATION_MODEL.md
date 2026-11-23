# Choke cavitation and flashing screening

Code: `backend/app/simulation/choke/cavitation.py`. Inputs:
`CavitationInputs` in `backend/app/models/sand.py` (Sand & choke inputs
page, panel "Choke cavitation data"). Results: the Cavitation & flashing
panel on the Choke health page.

**Model status: correlation-based screening.** It is not a CFD prediction
and not an experimental result. It says whether gas release, cavitation or
flashing is indicated at the current operating point, and where damage
would occur. It does not compute bubble dynamics, collapse locations or a
damage rate.

## Operating point

Every value comes from the running simulation at CHK-101:

- P1 and T1, at the choke inlet node;
- P2, at the choke outlet node;
- the opening;
- the GOR and water cut arriving at the choke.

Black-oil properties at P1 and T1 give the free-gas fraction at the inlet.
The screening needs the three-phase (black-oil) fluid model.

## Three questions

**1. Is there free gas at the inlet?** The inlet is two-phase when
P1 < Pb or the GVF is above zero. In that case:

- liquid cavitation criteria do not strictly apply, because gas cushions
  bubble collapse;
- the water-phase result is reported as indicative;
- the damage mechanism is erosion by the two-phase jet (see
  `CHOKE_EROSION_MODEL.md`).

**2. Live oil: does the pressure fall below the bubble point?**

| Condition | Regime |
|---|---|
| P2 < Pb | Outgassing / flashing: gas comes out of solution and stays out |
| P2 ≥ Pb, P_vc < Pb | Gaseous cavitation: gas released at the vena contracta, redissolving slowly |
| P_vc ≥ Pb | No gas release |

Gaseous cavitation is much less violent than vapour-bubble collapse.

**3. Water phase: vapour cavitation or flashing?**

| Condition | Regime |
|---|---|
| P2 < Pv,w | Flashing |
| P2 ≥ Pv,w, P_vc < Pv,w | Vapour cavitation |
| otherwise | None by the mean vena-contracta pressure |

The valve-specific σ limits then classify the water phase. They are
empirical and include local pressure minima in jets and vortices, so they
can indicate cavitation while the mean vena-contracta pressure stays above
Pv. The panel says so when that happens.

## Equations

IEC 60534-2-1 (liquid sizing):

    P_vc       = P1 − (P1 − P2) / FL²
    ΔP_choked  = FL² (P1 − FF·Pv)
    FF         = 0.96 − 0.28 √(Pv / Pc),   Pc (water) = 220.64 bar

The vena-contracta relation is applied only down to FF·Pv. Below that the
liquid flow is choked, and the panel reports it.

Cavitation index, in the ISA-RP75.23 form:

    σ = (P1 − Pv) / (P1 − P2)

Water vapour pressure uses the IAPWS-IF97 region-4 saturation equation for
pure water. Dissolved salt lowers it slightly, so the pure-water value is
conservative.

The bubble point comes from the PVT-report entry when given. Otherwise it
comes from the Standing correlation, the same as the black-oil model.

## Inputs (all from the manufacturer or a PVT report)

| Input | Meaning | If missing |
|---|---|---|
| FL, or an FL vs opening table | Liquid pressure-recovery factor of the trim | No vena-contracta pressure or choked ΔP; only the outlet-pressure checks run |
| σ incipient, σ constant, σ damage | Valve-specific cavitation limits; must decrease | No σ classification ("Unavailable") |
| Bubble point | From the PVT report | Standing correlation, with the sensitivity band marked ASSUMED |
| Sensitivity band | ± % on the bubble point | Default 10 % |

**No universal FL or σ values are built in.** The example input set
(training) carries illustrative values. Each one is labelled
"ILLUSTRATIVE - replace with the manufacturer's data".

## Outputs

- regime for the oil and the water phase, and the governing regime;
- risk:
  - the σ level, marked indicative when there is free gas at the inlet;
  - "Gas release - erosion-driven" for outgassing or a two-phase inlet;
  - "Not indicated";
  - "Unavailable";
- P_vc, choked ΔP, σ and the limits entered;
- the bubble point and its source;
- likely damage locations:
  - cage-hole exits and the plug nose / seat for cavitation;
  - cage-hole exit edges and the outlet bore for flashing;
- a sensitivity flag when the outgassing conclusion changes within the
  bubble-point band;
- missing inputs, assumptions and limitations.

## Verification

`backend/tests/test_cavitation.py`:

- IAPWS-IF97 saturation pressure at 300, 500 and 600 K equals the IF97
  verification values to within 1e-8;
- FF, P_vc, ΔP_choked and σ match hand calculation;
- the FL table interpolates correctly;
- every regime appears at the pressures that should produce it;
- without FL only the physics checks run, and FL is listed as missing;
- σ limits classify correctly, are never assumed, and must be ordered;
- the PVT bubble point overrides the correlation, and the sensitivity flag
  works;
- with free gas the result is marked indicative;
- older saved inputs without a cavitation block still load;
- in the engine, the screening follows the simulated choke: opening the
  choke lowers ΔP and raises σ.

## Limitations

- This is screening, not CFD. Collapse location and damage rate are not
  computed.
- FL and the σ limits depend on the trim and the opening, so the
  manufacturer's data are needed.
- The liquid criteria are single-phase. With free gas they are indicative
  only.
- Live-oil gas release is treated as outgassing or gaseous cavitation.
  Hydrocarbon vapour cavitation of the oil phase is not modelled separately.
