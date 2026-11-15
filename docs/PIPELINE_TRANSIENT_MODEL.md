# Pipeline transient model

Implementation: `backend/app/simulation/dynamic/network.py`, `builder.py`.

## 1. Discretisation

The production path, the annulus and every chemical-injection circuit are reduced to one graph:

* **Pressure nodes** are control volumes that store fluid: every topology node, interior points of each pipe, tree cavities, and reservoir cells. Each pipe of length `L` is split into `N` segments (`hydraulic_segments`, or `ceil(L / segment_length_m)`, default 250 m). Each segment gives half its volume to each end node (vertex-centred finite volume), so transmitters sit exactly on nodes.
* **Flow links** carry fluid and dissipate pressure: pipe segments, valves, chokes, metering valves, check valves, reservoir Darcy links.
* **Fixed-pressure nodes** are boundary conditions: the reservoir drainage boundary `P_res`, the flowline arrival (manifold) `P_down`, the annulus service header, and the chemical supply points (pump discharge referred to the subsea distribution unit).

Junctions with no volume of their own get a minimum volume (`minimum_node_volume_m3`, default 2 L) so that a node isolated between two closed valves is still well defined.

## 2. Line-pack: node mass balance

For a control volume `V` filled with a liquid of linearised equation of state `ρ = ρ₀ [1 + c_f (P − P₀) − β (T − T₀)]` and a wall that expands elastically:

    d(ρV)/dt = Σ ṁ_in − Σ ṁ_out

    d(ρV)/dt = ρV [ (c_f + c_wall) dP/dt − β dT/dt ]

Dividing by ρ₀ (relative density changes are ~1e−2 over the operating range) gives the volumetric form used:

    C dP/dt = Σ Q_in − Σ Q_out + V β dT/dt                                 (1)

    C = V (c_f + c_wall)          hydraulic capacitance [m³/Pa]

| Term | Source |
|---|---|
| `c_f` | fluid compressibility per zone (production fluid `compressibility_1_bar`, default 7e−5 /bar; branch fluids in `subsystems.fluids`) |
| `c_wall` | thin-walled pipe (Korteweg): `D / (E e)`, with `e = wall_thickness_m` (default D/12) and `E = youngs_modulus_gpa` (default 207). The annulus uses an explicit `wall_compliance_1_bar` (casing, cement and gas-cushion compliance). Rigid cavities use `c_wall = 0`. |
| `V β dT/dt` | thermal expansion of the stored fluid, from the thermal model (one step lag) |

So **pressure build-up is not assumed**. Closing a valve changes nothing by itself; the pressure of each volume then follows its own mass balance. The result depends on the isolated volume, the connected sources, the compressibility, leakage and temperature change. Examples that come out of (1) without special code:

* a trapped tree cavity with a leaking master valve builds up at `dP/dt = Q_leak / C`;
* the same cavity cooling with no leak loses pressure at `β/(c_f) · dT/dt` (about 9 bar/K for the default oil in a rigid cavity), which is why integrity tests have a stabilisation period;
* a shut-in flowline cooling at the seabed draws fluid back from the manifold (thermal contraction flow).

## 3. Momentum balance of a link

    I dQ/dt = P_up − P_dn − G − R(Q)                                       (2)

| Link | I | G | R(Q) |
|---|---|---|---|
| pipe segment | `ρ Δx / A` | `ρ g Δz` | `f(Re, ε/D) (Δx/D) ρ v|v| / 2`, with Churchill f; laminar `32 μ Δx v / D²` for Re < 1 |
| valve / choke / metering valve | `ρ · 0.5 m / C_open` (bore fluid, small) | `ρ g Δz` | `ρ Q √(Q² + Q_ε²) / (2 C²)`, with `C = C_open·f(x)`, or the seat-leak capacity when closed, or blocked (`Q = 0`) if there is no leak |
| check valve | as above | `ρ g Δz + P_crack` when open | orifice; blocked when closed |
| reservoir cell link | 0 | 0 | `Q / T_i` (Darcy) |

`Q_ε = C √(2·100 Pa / ρ)` regularises the orifice law near zero flow (exact above ~1 kPa of differential).

## 4. Pressure propagation versus gradual build-up

Equations (1) and (2) together form an L-C-R ladder. Its two limits are the two effects the requirements distinguish:

* **Wave propagation** (inertia ↔ compliance): `∂²P/∂t² = a² ∂²P/∂x²` in the continuum limit, with `a = 1/√(ρ (c_f + c_wall))`. The base flowline gives a = 1296 m/s, an acoustic transit of 3.9 s over 5 km. Transmitters at different distances respond at different times.
* **Diffusive relaxation** (resistance ↔ compliance): time constants `RC`. Wellbore storage against the reservoir's resistance takes seconds to minutes; the reservoir pore volume against its permeability takes hours.

The solver does not add any delay; the timing of each transmitter follows from where it sits in the network.

**Limitation.** With the default 1 s step (much longer than `Δx/a ≈ 0.2 s`), implicit Euler damps the waves. Arrival-time differences survive approximately, but wave amplitudes (water hammer) are not resolved. With `SUBSEASIM_DYNAMIC_STEP_S=0.01` and fine segments, arrival timing matches `Δx/a` within ~10% (automated test). Peak pressures should still not be used, because there is no MOC and no column separation.

## 5. Reservoir transient

`dynamics.reservoir` replaces the algebraic linear IPR by radial single-phase diffusion. Nodes sit at `r_i = r_w (r_e/r_w)^(i/n)`, with control-volume faces at geometric means. Pore volume is `V_p = φ h π (r²_{i+½} − r²_{i−½})` and capacitance is `V_p c_t`. The link conductances are

    T_i = 2π k h / (μ ln(r_{i+1}/r_i))          (skin added to the first link)

so the series sum gives exactly `J = 2πkh / (μ (ln(r_e/r_w) + S))`. **kh is derived from the configured productivity index**, so the dynamic model's final steady state equals the quasi-steady linear IPR. Thickness, porosity, total compressibility and drainage radius control only *how fast* the reservoir responds (diffusivity `η = k/(φ μ c_t)`).

## 6. Time integration

Backward Euler for (1)–(2) at a fixed step `Δt`:

    (C/Δt)(P − P_old) = Σ Q_in − Σ Q_out + S
    (I/Δt)(Q − Q_old) = ΔP − G − R(Q*) − R'(Q*)(Q − Q*)

Eliminating Q link by link (`Q = b (ΔP + a)`, with `b = 1/(I/Δt + R')`) gives a symmetric positive-definite system in the node pressures, solved directly. It is iterated (Newton on R) until the flows converge. Fixed nodes are imposed rows. The steady state (initialisation) is the same system with `Δt → ∞` and a tiny storage term, which keeps isolated volumes at their pressure.

Default `Δt = 1 s` (`SUBSEASIM_DYNAMIC_STEP_S`). It never changes with simulation speed.

## 7. Configuration parameters (minimum additional data)

| Parameter | Where | Default |
|---|---|---|
| `fluid.compressibility_1_bar` | scenario | 7e−5 |
| `wall_thickness_m`, `youngs_modulus_gpa`, `wall_compliance_1_bar`, `flow_area_m2`, `hydraulic_segments` | pipe element | D/12, 207, —, πD²/4, auto |
| `volume_m3`, `heat_loss_ua_w_k`, `thermal_mass_j_k`, `initial_pressure_bara` | node | 0 |
| `actuation_delay_s`, `close_stroke_time_s`, `seat_leak_area_mm2`, `nominal_stroke_time_s` | valve / choke | 0, = open, 0, — |
| `dynamics.reservoir` (h, φ, c_t, r_w, r_e, skin, cells) | scenario | none (algebraic IPR link) |
| `dynamics.segment_length_m`, `transport_cells_per_segment` | scenario | 250 m, 5 |
