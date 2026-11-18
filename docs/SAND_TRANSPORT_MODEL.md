# Sand transport model

**What is transported.** Sand is carried as a mass fraction (kg of sand per
kg of produced fluid). It is a fourth channel of the production-path
composition transport grid; see `docs/MULTIPHASE_FLOW_MODEL.md` §5.3. Source:
`backend/app/simulation/multiphase/dynamic.py` (`SAND_CH`) and
`backend/app/simulation/sand/system.py`.

## Model

**Inlet.** Each step (or every 10 s of simulated time) the sand-production
model sets the inlet fraction to `ṁ_produced / W_in`. Sand that passes the
screens enters the flow at the sandface.

**Transport.** Concentration moves only with the face flows of the hydraulic
network:

- conservative upwind scheme;
- mass-tracked cells.

Consequences:

- sand reaches the tree, the choke and the manifold with the fluid transit
  time;
- **it stops when the flow stops**;
- it reverses with reverse flow.

**Branches.** Chemical injection points dilute the concentration because they
add fluid mass. The production path has no splitting branches.

**Sand at a location** = transported fraction × local mass flow:

- at the choke inlet, used for erosion.

**Steady model.** The sand at the choke equals the produced sand.

## Assumptions and limitations

- **Particles follow the fluid.** There is no slip between particles and
  liquid, and no particle-size classes in transport (the produced D50 is
  reported).
- **Dilute flow.** Sand mass and volume are neglected in the hydraulics
  (< 0.1 vol % at the rates of interest).
- **Deposition is NOT simulated.** Settling, bed formation and re-entrainment
  are absent. A screening check flags each flowline segment where the
  superficial liquid velocity is below a Durand-type transport velocity:

      V_c = F_L √(2 g D (ρ_s/ρ_l − 1)),   F_L = 0.6

  The check uses the fine-sand, low-concentration value; it is shown in
  the Sand source panel of the Choke health page. A flagged segment means "may deposit", not "has deposited".
- **Numerical dispersion.** Upwind discretisation spreads a sand front, as
  for chemicals.

## Verification

`backend/tests/test_sand_choke.py` (integration):

- after sanding starts, sand at the choke is lower than the produced sand at
  first (transit time);
- they converge within 5 % once the path is filled.

The mass conservation of the shared transport grid is covered in
`backend/tests/test_multiphase.py`.
