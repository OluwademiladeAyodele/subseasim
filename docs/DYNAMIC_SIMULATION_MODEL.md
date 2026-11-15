# Dynamic simulation model (Release 2)

SubseaSim has two simulation models behind one engine, one API and one user interface:

| Mode | What it is | When to use |
|---|---|---|
| `steady` | Release 1 quasi-steady model, unchanged: the algebraic operating point of the series production path is recalculated instantly; temperatures are transient. Branch subsystems (annulus, chemical injection) are **not modelled** and their transmitters report `NOT_MODELLED`. | Pressure-budget teaching (Exercise 3), comparing with hand calculations. |
| `dynamic` | Time-dependent model of the whole system: compressible line-pack and wellbore storage, a radial reservoir transient, annulus and chemical-injection branches, chemical transport and mixing, transient thermal model, valve dead time and seat leakage, transmitter dynamics. | Default for `subsea_dynamic_base` and the `dyn_*` training scenarios. |

The mode is a scenario setting (`dynamics.mode`) and can be switched in the top bar (`POST /api/sessions/{id}/mode`). Switching rebuilds the model and restarts from the scenario's initial conditions. Release 1 scenarios (`base_single_phase`, `ex03_choke_operation`) still default to `steady`, so every Release 1 behaviour and test is preserved.

## 1. What was there before (audit summary)

| Question | Release 1 finding |
|---|---|
| Instant steady-state recalculation? | **Yes.** Hydraulics were solved algebraically (Brent) every time an actuator moved. |
| Fixed pressure offsets? | No. |
| Arbitrary delays / frontend timers? | No. Time already advanced only in the backend (`advance(dt)`), independent of rendering. |
| Existing transient model? | Thermal only (implicit-Euler cells). Valves had rate-limited travel (kinematics only). |
| Simulation time? | Yes, with speeds 1–300×. |
| Annulus, chemical injection, integrity testing? | **Not present.** The topology validator rejected branches. They were built new in Release 2. |

## 2. Architecture

```
app/simulation/
  hydraulics/network.py        steady-state series solver (Release 1, unchanged)
  dynamic/
    builder.py                 scenario -> graph of pressure nodes and flow links
    network.py                 dynamic hydraulic solver (implicit Euler + Newton)
    transport.py               chemical transport/mixing + thermal model (finite volume)
    model.py                   DynamicModel: couples network, transport, annulus
                               temperature, injection circuits, instrument response
    integrity.py               stroke / pressure-hold / inflow tests
  valves/actuator.py           commanded vs actual position, dead time, open/close rates
  engine.py                    lifecycle, fixed-step clock, commands, events, snapshots
```

Separation of concerns (requirement 13):

| Concern | Where |
|---|---|
| Steady-state hydraulic solver | `hydraulics/network.py` (still runs in dynamic mode as the **steady-state reference**) |
| Dynamic hydraulic solver | `dynamic/network.py` |
| Pipeline transport model | `dynamic/transport.py` (`TransportGrid.step`, concentration) |
| Chemical mixing model | `dynamic/transport.py` (sources at injection cells) + `model.py` (circuits) |
| Thermal model | `dynamic/transport.py` (energy equation on the same grid) + lumped annulus temperature in `model.py` |
| Valve actuation model | `valves/actuator.py` |
| Instrument response model | `model.py` (`_update_instruments`) |
| Simulation clock | `engine.py` (`_advance_dynamic`, fixed global step grid) + `sessions.py` (wall-clock loop) |
| Simulation state manager | `engine.py` / `sessions.py` (authoritative backend state, WebSocket deltas) |

## 3. Governing equations

Full derivations are in [PIPELINE_TRANSIENT_MODEL.md](PIPELINE_TRANSIENT_MODEL.md), [CHEMICAL_TRANSPORT_MODEL.md](CHEMICAL_TRANSPORT_MODEL.md) and [INSTRUMENT_RESPONSE_MODEL.md](INSTRUMENT_RESPONSE_MODEL.md). In summary:

**Node mass balance** (every control volume: pipe half-segments, tree cavities, reservoir cells)

    C_i dP_i/dt = Σ Q_in − Σ Q_out + V_i β dT_i/dt,        C_i = Σ V (c_f + c_wall)

**Link momentum balance** (pipe segments, valves, chokes, check valves, reservoir Darcy links)

    I dQ/dt = P_up − P_dn − ρ g Δz − R(Q),                  I = ρ L / A

**Transport and energy** (production path, finite volume, upwind)

    V dc/dt = F_w c_w − F_e c_e + Q_inj                    (per chemical)
    ρc_p V dT/dt = Σ ρc_p F_in (T_in − T) + (ρc_p)_inj Q_inj (T_inj − T) − U π D Δx (T − T_amb)

The dynamic state is initialised from the steady operating point of the scenario, so a simulation that is started and left alone stays exactly where it is (verified: zero drift).

## 4. Physical effects represented

| Effect | Represented by |
|---|---|
| Fluid compressibility, pipe-wall elasticity | Capacitance `C = V (c_f + D/(E e))` per node |
| Pipeline length / diameter / volume | Number of segments, segment volume, inertance and friction per segment |
| Line-pack and pressure build-up | Node mass balance (no assumed ramp) |
| Pressure-wave propagation | Inertance–capacitance ladder (approximate, see limitations) |
| Wellbore storage + reservoir transient | Wellbore compliance + radial diffusion grid |
| Flow resistance, restrictions | Churchill friction; orifice law with valve characteristic |
| Thermal expansion of trapped liquid | Source `V β dT/dt` in the node balance |
| Chemical injection into the production line | Injection-circuit network discharging through a check valve into a production node |
| Chemical transport and mixing | Finite-volume advection by the calculated flows |
| Thermal mixing, heat loss, throttling | Energy equation on the transport grid |
| Annulus pressure behaviour | Annulus network + lumped annulus temperature (thermal APB) |
| Valve dead time, travel, seat leakage | Actuator model + leak capacity when closed |
| Instrument lag / update interval / resolution | Instrument response model (after the process dynamics) |

## 5. Valve movement versus process response

Each operation produces separate, time-stamped events:

1. `operation`: command recorded (with dead time and estimated travel time);
2. `valve`: end of travel (`PWV-101 reached 0.0 %`);
3. `outcome`: process values **at that moment** plus the steady-state reference the system is heading toward;
4. `process`: "process response … has SETTLED", logged when every pressure node changes by less than 0.003 bar/min for 120 s.

Example (base dynamic scenario, closing PWV-101): the valve finishes at T+32 s. The tree pressure is then 130–140 bara, still rising toward the steady-state 171 bara, and the settled event comes hours later because of the reservoir transient.

## 6. Numerical method and stability

* Backward (implicit) Euler for the coupled node–link system: A-stable, so the fixed step is stable for any segment length and any speed.
* Newton iteration on the friction / orifice non-linearity: typically 1–2 iterations per step, at most 40. Convergence is `|ΔQ| ≤ 1e-11 + 1e-8 |Q|`. Non-convergence is reported as a diagnostic warning (`DYNAMIC_NOT_CONVERGED`). A non-finite or singular solution raises `DynamicSolverError`: the engine keeps the last valid state, **pauses** the simulation and logs an error event (no physically meaningless numbers are shown).
* Orifice law regularised below 100 Pa of differential (exact above ~1 kPa) so the Jacobian stays finite at zero flow.
* Check valves: active-set iteration (open if forward differential > cracking pressure, closed if the flow tries to reverse).
* Transport and thermal: explicit upwind with sub-cycling at Courant number ≤ 0.8 (positivity-preserving, conservative for concentration).
* **Determinism**: the dynamic model integrates on a fixed global step grid (`time = n × dt`). Any partitioning of `advance()` calls, and any simulation speed, produces bit-identical results (tested with `np.array_equal`).

Performance: about 0.8 ms per 1 s step for the full system (96 pressure nodes, 95 links, 157 transport cells). At 600× that is roughly 50% of one CPU core per session. The top bar shows the speed actually achieved, so a lagging session is visible.

## 7. Limitations (read before using results)

* **Single-phase liquid everywhere**: no gas, no flashing, no column separation. Absolute pressure ≤ 0 is flagged as an error, below bubble point as a warning.
* **Pressure waves** are resolved only when the step is small compared with the acoustic transit time of a segment (`L_seg / a ≈ 0.2 s`). At the default 1 s step, waves are smeared (implicit Euler damping). Water-hammer peak pressures are **not** predicted. MOC is not implemented. The lumped ladder reproduces wave arrival timing within ~10% at a fine step (see Verification).
* Constant fluid properties per zone. Mixture density and viscosity are not fed back into the hydraulics (chemical fractions are small); mixture heat capacity is used only in the injection enthalpy term.
* Production pipe-wall heat capacity is neglected (cool-down is faster than reality). Tree cavities may carry an explicit solid thermal mass.
* The annulus temperature is lumped (single value, first-order lag to a weighted tubing/geothermal temperature).
* The reservoir has a constant-pressure outer boundary (steady-state drainage). There is no depletion and no gas.
* Numerical dispersion is the only axial mixing in the transport model (no Taylor dispersion term).
* All data are illustrative. Acceptance limits for integrity tests are training values, not a standard.

## 8. Verification summary

All checks are automated in `backend/tests/test_dynamic.py` and `test_api_dynamic.py`. Measured values (Release 2 build):

| Check | Reference | Result |
|---|---|---|
| Lumped volume charging through a resistance | `P(t) = P1 + (P0 − P1) e^(−t/RC)` | max error 0.09 bar on a 100 bar step (dt = τ/200) |
| Time constant ∝ volume and ∝ compliance | 2× V or 2× c → 2× τ | within 2% |
| Pressure-wave arrival lag (1 km vs 3 km from a closed valve, 4 km pipe, 40 segments, dt = 0.01 s) | 2000 m / a = 1.54 s (a = 1296 m/s) | 1.41 s (−8%) |
| Chemical 50% arrival at 2.5 km | plug-flow V/Q = 3934 s | 3920 s (−0.4%) |
| Higher flow → earlier arrival | choke 20% vs 60% | 6090 s vs 2400 s |
| Steady flowline outlet temperature | `T_amb + (T_in − T_amb) e^(−UπDL/ṁc_p)` | 56.95 °C vs 56.91 °C exact |
| Chemical mass balance | injected = in line + exported + to reservoir | relative error 1.3e−10 |
| Steady initial state | no drift | exact over 60 s |
| Determinism | 600 s in 1 call vs 2400 calls of 0.25 s, 1× vs 600× | bit-identical |

Scenario A shut-in build-up (calculated, not programmed), PT-101 [bara]:

| t after closing PWV | 0 | 5 min | 15 min | 30 min | 45 min | 60 min | 120 min | steady state |
|---|---|---|---|---|---|---|---|---|
| PT-101 | 98.2 | 190.3 | 199.6 | 205.1 | 208.3 | 210.5 | 215.7 | 221.2 |

The shape is the physically expected one for a liquid-filled well: a rapid wellbore-storage rise, followed by a logarithmic reservoir-controlled build-up. An approximately linear one-hour rise (as in the illustrative table in the requirements) would need much larger wellbore storage, for example a gas cap, which the single-phase model does not have and therefore does not fake.
