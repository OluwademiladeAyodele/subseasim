# Chemical injection, transport and mixing model

Implementation: `backend/app/simulation/dynamic/transport.py` (grid, transport, thermal) and `model.py` (circuits, status, front, transit times).

## 1. Injection circuit topology

Each chemical (methanol, corrosion inhibitor, biocide, wax inhibitor) is an independent hydraulic branch of the dynamic network, configured in `subsystems` and `chemicals`:

```
SUP_x (pump discharge @ SDU, fixed P) ──CL-30x umbilical line (5 km)──► N_x_IN [PT-30x]
   ──CIV-30x isolation valve──► N_x_A ──CIMV-30x metering valve [FT-30x]──► N_x_B
   ──NRV-30x non-return valve (cracking P)──► injection node on the PRODUCTION path
```

| Chemical | Injection node (base scenario) | Downstream transmitters |
|---|---|---|
| Methanol | `N_PMV_PWV`, tree bore cavity | PT-102/103, AT-510 (downstream choke), AT-511 (2.5 km), AT-512 (arrival) |
| Corrosion inhibitor | `N_UC`, wing block upstream of the choke | AT-521, AT-522 |
| Biocide | `N_DC`, flowline inlet | FT-101 (includes the injected stream), AT-531, AT-532 |
| Wax inhibitor | `N_SCSSV_D`, downhole mandrel (via a 605 m downhole line) | upper tubing, tree, flowline; AT-541, AT-542 |

The **pump** is an ideal pressure source referred to the subsea distribution unit: `discharge_pressure_bara` while running, `static_pressure_bara` (the static head of the chemical column) when stopped. Both are adjustable from the Chemicals panel (`POST /api/sessions/{id}/chemicals/{chem}`).

## 2. Injection flow (calculated, not set)

The injection rate is whatever the coupled network gives:

    P_supply + ρ_chem g (z_SDU − z_inj) − ΔP_line(Q) − ΔP_CIV(Q) − ΔP_CIMV(Q, x) − P_crack = P_production(inj node)

The Chemicals panel reports the **available differential** `P_supply + head − P_inj − P_crack`. If it is negative the check valve stays closed and no chemical enters, and the circuit status is `insufficient_differential`. A small injection rate changes the production pressure only through the real hydraulics: about +1 bar at the tree for 2.8 vol% methanol in the base case, because the choke passes slightly more flow. Upstream measurements change only when the coupled model predicts it. In that case the tree back-pressure reduces reservoir inflow by ~2%, so the tubing cools by ~0.3 K.

Circuit status: `injecting` (isolation and metering open and flow > 3.6 mL/h), `isolated`, `metering_closed`, `pump_stopped`, `insufficient_differential`. A trapped line section that decompresses through the check valve after isolation is a real but tiny transient flow; it is not reported as injection.

## 3. Transport grid

The production path is divided into transport cells: each hydraulic pipe segment into `m` cells (`transport_cells_per_segment`, default 5; 50 m cells in the flowline), plus one cell for each production node with a cavity volume. Faces between cells carry the **calculated link flows** of the hydraulic model. Fluid moves only when the hydraulic model says it moves: no timer and no assumed velocity.

## 4. Concentration (volume fraction) balance

Conservative upwind finite volume for each chemical k:

    V_i dc_k,i/dt = F_w c_k,upwind(w) − F_e c_k,upwind(e) + Q_inj,k,i                  (1)

* The injection enters the cell containing the injection node (its cavity cell, or the first cell downstream of it in the current flow direction).
* Dilution of other chemicals is automatic: the extra volume carried by downstream faces includes `Q_inj`.
* The reservoir inflow carries `c = 0`. Reverse flow at the outlet carries `c = 0` from the manifold.
* Fully mixed concentration just downstream of an injection point is `Q_inj / (Q_prod + Q_inj)`. The model distinguishes the injection rate (FT-30x), the local concentration (the injection cell), the concentration at each analyser (its cell), and the pipeline inventory (`Σ V c`, shown as "In line").

Integration: explicit Euler with sub-cycling so that `Δt Σ F_in / V ≤ 0.8` in every cell (positivity preserving).

**Mass balance** is tracked: injected volume = in-line inventory + exported at the manifold + lost to the reservoir (reverse flow). Verified to 1e−10 relative.

## 5. Residence time and arrival

For plug flow through a uniform segment, `t = V / Q` with `V = (πD²/4) L`. The Chemicals panel shows, for each analyser, the plug-flow transit `Σ V_cell / F_face` at the **current** flows. The modelled 50% arrival at AT-511 (2.5 km) is 3920 s, against a plug-flow estimate of 3934 s (−0.4%).

* At lower production rates the transit is longer, at higher rates shorter (choke 20%: 6090 s; choke 60%: 2400 s).
* With zero production flow there is no advective transport. In the shut-in flowline the only movement is thermal-contraction back-flow from the manifold (tens of metres per hour, against kilometres per hour while flowing).
* When injection stops (isolation valve closed), the chemical already in the line keeps moving with the production flow, and the methanol-free front travels down the line at the same velocity.

Chemical transport (fluid velocity, ~1 m/s) and pressure propagation (wave speed, ~1300 m/s) are separate mechanisms in the model.

## 6. Mixing, dispersion and thermal effects

* **Dispersion.** The only axial mixing is the numerical dispersion of the upwind scheme. With N cells along a pipe the front spreads like an axial-dispersion model with Péclet number ~2N (N = 100 in the flowline: about ±10% of the transit time). There is no physical Taylor dispersion term, and a tail of ~1e−11 can appear ahead of the front.
* **Temperature.** The injected stream mixes enthalpy: `(ρc_p)_inj Q_inj (T_inj − T)`. Methanol at 4 °C injected at 2.8 vol% cools the stream downstream of the tree by ~2.6 K. Mixing at equal temperature produces no temperature change (automated test). The injection temperature is the configured `injection_temperature_c` (the line is assumed to have reached seabed temperature).
* **Fluid properties.** Mixture density and viscosity are not fed back into the hydraulic solver (fractions are small, documented limitation). The heat capacity of the injected chemical is used in the mixing term.

## 7. Display

* Schematic: coloured bands along production pipes show each chemical's local concentration relative to its current fully-mixed value. The analyser stacks show AT readings.
* Trends: injection flow (L/h), concentration (vol% and ppm charts), with event markers for injection start and stop.
