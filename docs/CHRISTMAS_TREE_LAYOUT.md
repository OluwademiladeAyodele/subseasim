# Christmas tree workstation – layout

The **Christmas tree workstation** (Christmas tree page → *Tree workstation*)
reproduces the **architecture** of the reference control-system page
"Production 230XP22B", supplied as a photograph. That means the arrangement,
connectivity and tag numbering of valves, transmitters, flowlines, chemical
injection lines and selector valves.

**Not reproduced from the photograph:** the numbers it displays. Every value
on the workstation is calculated by the simulator from the scenario's
engineering inputs:

- reservoir pressure, temperature and productivity;
- fluid properties;
- downstream (manifold) pressure;
- the current valve positions.

The values respond to valve operations through the dynamic model.

## 1. Files and separation of concerns

| What | File | Contains |
|---|---|---|
| Schematic layout | `backend/app/scenarios/layouts/xt_230xp22b.json` | Positions only: component id, type, x, y, w, h, rotation, ports, flow path, tap point, label offset, group. No physics. |
| Engineering configuration | `backend/app/scenarios/data/xt_230xp22b.json` | Nodes, elements, instruments, chemicals, control hydraulics, display-tag aliases. |
| Generator (source of both) | `backend/scripts/generate_xt_230xp22b.py` | Photo-pixel measurements and the topology changes relative to `subsea_dynamic_base`. |
| Schema | `backend/app/models/schematic.py` | `SchematicLayout` (validated on load). |
| Renderer | `frontend/src/schematic/XtSchematic.tsx` | Reusable SVG symbols; all state from the snapshot. |

**Links between layout and model.** The layout refers to the model only
through stable references:

- `element:<id>`
- `instrument:<engineering tag>`
- `chemical:<id>`
- `selector:<tag>`
- `header:<id>`
- `supply:<id>`
- `page:<route>`

**Moving a component changes nothing physical.** Moving a component or panel in
the layout does not change where it measures or what it is connected to. This
is verified by `test_layout_positions_do_not_affect_measurement_location`.

**Changing topology is explicit.** It is an engineering-configuration change
made in the generator.

## 2. Coordinate system

- **Measurement.** Components were measured in photo pixels on the 810 × 1080 px
  photograph.
- **Keystone correction.** Verticals were straightened; the measured shear was
  about 0.07 px/px.
- **Mapping to schematic units.** `X = (px − 20) × 2.6` and `Y = (py − 40) × 2.6`,
  on a viewBox of 1643 × 1071.
- **Scaling, zoom and pan.**
  - The SVG scales uniformly (`preserveAspectRatio="xMidYMid meet"`).
  - Zoom and pan change only the viewBox.
  - Nothing is repositioned for the available space.
- **Text panels.** Panels are slightly larger than on the reference, for
  legibility. Each keeps its anchor next to its tap point.

### Measured positions (photo px, straightened)

**Production bore (x = 233)**

| Item | Position |
|---|---|
| Tree cap | y 86 |
| Wing junction | y 145 |
| XOV entry | y 196 |
| PMV3004 | y 279 |
| SCSSV3003 | y 326 |
| PTT3002 / PTT3003 tap | y 350 |
| Downhole chemical entry | y 363 |

**Annulus bore (x = 202)**

| Item | Position |
|---|---|
| AWV branch | y 139 |
| PT3030 tap | y 222 |
| PT3031 tap | y 249 |
| AMV3030 | y 279 |

**Service line (y = 196)**

| Item | Position |
|---|---|
| SLV3035 | x 82 |
| PT3014 tap | x 124 |
| Junction with the AWV branch | x 144 |
| XOV3032 | x 171 |

**Production wing (y = 145)**

| Item | Position |
|---|---|
| PTT3004 tap | x 289 |
| PWV3005 | x 441 |
| PCV3006 (angle choke, outlet down) | x 481 |

**Choke outlet (x = 481)**

| Item | Position |
|---|---|
| XT3001 tap | y 184 |
| Inline device | y 200 |
| PTT3008 tap | y 227 |
| PTT3009 tap | y 260 |

**Chemical injection (CIV, then metering valve CCV, then connector at x 405)**

| Line | Valves | Joins the wing at |
|---|---|---|
| y 176 | CIV3027 at x 315, CCV3026 at x 375 | x 301 |
| y 203 | CIV3025 at x 316 | x 285 |
| y 232 | CIV3023 at x 317, CCV3022 at x 375 | x 277 |

**Methanol injection valves (header at x 350)**

| Valve | Line | Joins the wing at |
|---|---|---|
| MIV3015 | y 265 | x 425 (upstream of PWV) |
| MIV3016 | y 290 | x 455 (between PWV and the choke) |

**Downhole chemical line (y 356)**

- CCV3036 at x 97.
- CIV3021 at x 130.

**Selector valves (frame 385–535 × 296–446)**

| Item | Position |
|---|---|
| LP supply | y 346 |
| LP selector valves | (468, 326) and (468, 364) |
| HP supply | y 417 |
| HP selector valves | (468, 397) and (468, 433) |
| Header taps | x 500 |

`test_reference_positions_are_preserved` checks the main components against
this table to within 1.5 px.

## 3. Tags (display aliases)

**Engineering tags stay the stable identifiers.** Tags such as PMV-101 and
CHK-101 are what the model, the API, the tests and the training exercises use.

**Reference tags are display aliases.** The tag numbers on the reference page
are stored as aliases in `tag_aliases`. Each alias has a provenance status:

| Status | Meaning |
|---|---|
| verified | read confidently from the reference |
| uncertain | partly legible – verify against the P&ID (drawn with a dotted border) |
| placeholder | not tagged on the reference (selector valves) |
| addition | SubseaSim component not on the reference page (dashed border) |

**Verified tags**

- Valves: AWV3034, AMV3030, PMV3004, PWV3005, SCSSV3003, PCV3006, XOV3032,
  SLV3035.
- Transmitters: PT/TT3002, PT/TT3003, PT/TT3004, PT/TT3005, PT/TT3008,
  PT/TT3009, PT3014, PT3030, PD3014.

**Uncertain tags**

- Chemical injection valves: CIV3021, CIV3023, CIV3025, CIV3027, CCV3022,
  CCV3026, CCV3036.
- Methanol injection valves: MIV3015, MIV3016.
- Hydraulic pressure panels: LPHP1, HPHP1, LP3096, LP3097, HP3098, HP3099.
- PT3031, which may read PT3011 on the photograph.

**Placeholders.** SEL-LP-A/B and SEL-HP-A/B (the selector valves carry no tag on
the reference page).

**Not assigned.** PT3010, PT3011 and PT3013 could not be located on the
photograph.

**Where the aliases are accepted and shown**

- The API accepts either tag, for example `POST /valves/PWV3005`.
- The inspector shows the reference tag, the engineering tag and the alias
  status.
- The valves page, instrument table, key measurements and event log display
  the reference tags.

## 4. Topology changes relative to `subsea_dynamic_base`

These follow the reference page:

- **Crossover.** XOV3032 connects the service-line junction (downstream of AWV,
  upstream of SLV) to the tree cavity.
- **Chemical injection points.**
  - The corrosion-inhibitor and biocide lines inject into the production wing,
    upstream of PWV.
  - The downhole chemical line enters below the SCSSV.
- **Methanol.**
  - Two methanol injection valves (MIV3015 and MIV3016) are fed from one header
    and inject upstream and downstream of PWV.
  - They are modelled as additional *routes* of the methanol circuit, sharing
    its pump. Their chemical is transported and conserved exactly like the main
    injection point; see `ChemicalConfig.routes`.
  - The methanol route into the annulus service line is not on the reference
    page and is not part of this scenario. It remains in `subsea_dynamic_base`.
- **Additional transmitters**, placed at the reference positions:
  - TT3005: temperature of the tree cavity.
  - PTT3004: the wing, upstream of PWV.
  - PTT3003: downhole gauge B.
  - PTT3009: 30 m downstream of the choke.
  - PT3014: service-line junction.
  - PD3014: differential across SLV. The measurement points are assumed from
    the transmitter's position on the reference.

### Drawn position vs. measured location

- **PT3031** is drawn above AMV, as on the reference, but measures the
  A-annulus below AMV.
- **Transmitters on the same volume read the same.** PTT3004 and PTT3005 both
  sit on the tree cavity volume, so they read the same pressure. The model does
  not resolve friction inside the tree block.

## 5. Control hydraulics (selector valves)

**Path.** Supplies feed selector valves, which feed the SCM A/B headers, which
power the valve actuators. Implementation:
`backend/app/simulation/control/hydraulics.py`.

**Supply allocation**

| Supply | Pressure | Minimum operating | Powers |
|---|---|---|---|
| LP | 207 bara | 110 bara | Tree valves, choke, injection valves |
| HP | 517 bara | 300 bara | SCSSV |

These values are illustrative.

**Header pressure model.** Each header pressure follows a first-order lag,
solved exactly over each step:

`dp/dt = o (p_supply − p)/τ_charge − (1 − o) p/τ_bleed`

**A/B redundancy.** The highest header of a supply powers its actuators.

**Loss of a supply** (both selector valves closed, or an HPU trip):

- Fail-safe valves are commanded closed, on spring return.
- The choke and the metering valves fail as-is.
- An alarm event is logged.
- Opening commands are rejected while the supply is below its operating
  minimum.

**Not modelled:** actuator volumes, pilot valves, umbilical transients and SCM
communications. The SCM Reconnect button is therefore not reproduced.

## 6. Interaction

| Click | Opens |
|---|---|
| Valve, choke or metering valve | The valve inspector: commands, position, ΔP |
| Transmitter row | The transmitter inspector: live value, quality, response |
| Chemical line or its connector | That injection circuit's controls (pump, valves, routes) |
| Selector valve or hydraulic panel | The control-hydraulics inspector: selector commands, header pressures, HPU trip / restore |
| SCM Diagnostic | The Diagnostics page |

**State shown on the drawing**

- A line is drawn flowing (full colour, animated) only when one of its model
  elements is flowing.
- Isolated lines are faded.
- Chemical lines take the chemical's colour while it is injecting.
- The reference colour convention is used and shown in the legend:
  - valves: teal = open, red = closed;
  - lines: maroon = production, teal = annulus, blue = control hydraulics.

**XT3001**, the inline device on the choke outlet, is drawn and labelled *not
modelled*. It is reserved for the sand detector (Stage 5).

## 7. Verification

**Backend:** `backend/tests/test_xt_workstation.py`. It checks:

- every layout reference resolves;
- every valve and reference transmitter is drawn;
- reference positions are within tolerance;
- line ends are connected and components sit on their flow paths;
- the layout does not affect measurement location;
- the alias coverage;
- readings are model-calculated and follow inputs and valve operations;
- LP-loss fail-safe and HP trip behaviour;
- MIV routes conserve chemical volume.

**Frontend:** `frontend/src/xt.test.tsx`. It checks:

- components are rendered;
- positions are taken from the layout;
- selections are reported;
- the drawn state follows the model;
- the hydraulics panel works.

**End-to-end:** the *Christmas tree workstation* workflow in
`frontend/e2e/workflows.spec.ts`.
