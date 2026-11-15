# Instrument response model

Implementation: `backend/app/simulation/dynamic/model.py` (`_pv`, `_update_instruments`, `readings`) and `instruments/instruments.py`.

## 1. Process value versus measurement

Every transmitter has two values:

* **PV (process value)**: the model's state at the instrument location, taken from the dynamic simulation state. It already evolves in time, because the process is dynamically modelled.
* **Measurement**: what the transmitter reports, after sensor dynamics, update interval, resolution and range limits.

Sensor dynamics are applied **on top of** the process dynamics, never instead of them. An instantaneous engineering calculation cannot be disguised as a slow sensor, because the hydraulic, thermal and transport models are themselves time-dependent.

## 2. Where each PV comes from

| Type | Location | PV |
|---|---|---|
| pressure | node | node pressure of the hydraulic network |
| pressure | pipe + distance | linear interpolation between the two neighbouring hydraulic nodes |
| differential_pressure | two nodes | `P_high − P_low` |
| temperature | production node | transport-grid temperature on the upwind side, plus throttling of any restriction crossed before the node |
| temperature | pipe + distance | temperature of the transport cell at that distance |
| temperature | annulus node | lumped annulus temperature |
| flow | node on the production path | flow of the link **leaving** the node along the path; downstream of an injection point this includes the injected stream |
| flow | element | flow through that valve / metering valve / pipe segment (e.g. FT-30x on the metering valve) |
| concentration | node / pipe + distance | volume fraction of the chemical in the corresponding transport cell (mixed value at an injection node without its own cavity) |

Different transmitters therefore never share a value unless they share a location.

## 3. Sensor response

Configured per instrument (`response`) or per type (`dynamics.default_response`):

| Parameter | Effect |
|---|---|
| `time_constant_s` τ | first-order lag: `y ← y + (1 − e^(−Δt/τ))(PV − y)` every solver step |
| `update_interval_s` | sample-and-hold: the output changes only at these intervals (analysers) |
| `resolution` | the output is rounded to this increment, in the instrument's engineering unit |
| `range_min/max` | outside range the output clamps and the status is `OUT_OF_RANGE_HIGH/LOW` |

Defaults in `subsea_dynamic_base` (illustrative):

| Type | τ | Update | Resolution |
|---|---|---|---|
| pressure / ΔP | 0.5 s | every step | 0.01 bar |
| temperature | 15 s (thermowell) | every step | 0.05 K |
| flow | 2 s | every step | 0.1 m³/d |
| concentration analyser | 20 s | 30 s | 0.01 vol% / 0.1 ppm |

## 4. Status

`GOOD`, `OUT_OF_RANGE_HIGH/LOW`, `UNDETERMINED` (no value can be determined), `BAD` (model invalid: any error diagnostic, or a dynamic solver failure), `NOT_MODELLED` (the transmitter is on a subsystem that the active model does not represent, e.g. annulus transmitters in steady mode). No substitute value is ever shown.

## 5. Display

* The schematic bubble shows the measurement, a ▲/▼ arrow from the calculated dP/dt at the node, and (dynamic mode, production pressures) `→ xxx ss`: the steady-state value that pressure is relaxing toward, when it differs by more than 0.5 bar.
* The component panel shows the measurement, the model PV and the response settings side by side, so the two can be compared.
* Trends record measurements (`inst:TAG`) and, for production pressure and flow, the steady-state reference (`ref:TAG`, dashed).
