"""Scenario configuration schema (file format).

Scenario files are written in engineering units with the unit in every field
name (``_bara``, ``_c``, ``_m`` ...) so that no value is ambiguous. The engine
converts them to SI on load (see ``app.simulation.build``).
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

Positive = Annotated[float, Field(gt=0)]
NonNeg = Annotated[float, Field(ge=0)]
Percent = Annotated[float, Field(ge=0, le=100)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FluidConfig(_Strict):
    model: Literal["constant_property_liquid"] = "constant_property_liquid"
    name: str
    density_kg_m3: Annotated[float, Field(gt=100, lt=2000)]
    viscosity_cp: Annotated[float, Field(gt=0.01, lt=10_000)]
    specific_heat_j_kgk: Annotated[float, Field(gt=100, lt=10_000)]
    #: Volumetric thermal-expansion coefficient used ONLY in the
    #: throttling-temperature relation (density is held constant).
    thermal_expansion_1_k: Annotated[float, Field(ge=0, lt=0.01)] = 0.0
    #: Validity limit of the single-phase assumption. Below this pressure gas
    #: would come out of solution; the model then flags the result invalid.
    bubble_point_pressure_bara: NonNeg = 0.0
    #: Isothermal liquid compressibility c_f = (1/rho) d(rho)/dP [1/bar].
    #: Used ONLY by the dynamic model (line-pack, pressure build-up, wave
    #: speed). The quasi-steady model treats the liquid as incompressible.
    compressibility_1_bar: Annotated[float, Field(gt=0, lt=1e-2)] = 7.0e-5


class ReservoirConfig(_Strict):
    pressure_bara: Annotated[float, Field(gt=1, lt=2000)]
    temperature_c: Annotated[float, Field(gt=-10, lt=250)]
    productivity_index_m3d_per_bar: Annotated[float, Field(gt=0, lt=10_000)]


class BoundaryConfig(_Strict):
    node: str
    pressure_bara: Annotated[float, Field(gt=0, lt=2000)]
    #: Temperature of fluid entering from the boundary if flow ever reverses.
    fluid_temperature_c: Annotated[float, Field(gt=-10, lt=250)]


class NodeConfig(_Strict):
    id: str
    name: str
    #: Elevation relative to mean sea level, positive up [m].
    elevation_m: float
    #: Dynamic model only: lumped cavity volume at this node (tree bore,
    #: valve body, manifold header) in addition to the half-volumes of the
    #: connected pipe segments [m3].
    volume_m3: NonNeg = 0.0
    #: Dynamic model only: initial pressure used for a node that is not
    #: hydraulically connected to any boundary at start-up (trapped) [bara].
    initial_pressure_bara: Positive | None = None
    #: Dynamic model only: heat-loss conductance of the cavity fluid to the
    #: surroundings [W/K] (tree-body / insulation path; steel heat capacity
    #: is not modelled) and the surrounding temperature [degC].
    heat_loss_ua_w_k: NonNeg = 0.0
    #: Heat capacity of solid material in thermal contact with the cavity
    #: fluid (tree body steel) [J/K]; slows the cavity temperature response.
    thermal_mass_j_k: NonNeg = 0.0
    ambient_temperature_c: float = 4.0


class _ElementBase(_Strict):
    id: str
    name: str
    from_node: str = Field(alias="from")
    to_node: str = Field(alias="to")
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class InflowElementConfig(_ElementBase):
    type: Literal["inflow"]


class PipeElementConfig(_ElementBase):
    type: Literal["pipe"]
    role: Literal["tubing", "flowline", "jumper", "annulus", "injection_line", "service_line"] = "flowline"
    length_m: Positive
    inner_diameter_m: Annotated[float, Field(gt=0.002, lt=2.0)]
    roughness_m: NonNeg = 4.5e-5
    #: Overall heat-transfer coefficient referred to the INNER surface.
    overall_htc_w_m2k: NonNeg = 0.0
    ambient_temperature_inlet_c: float = 4.0
    ambient_temperature_outlet_c: float = 4.0
    thermal_cells: Annotated[int, Field(ge=1, le=200)] = 20
    # ---- dynamic model only -------------------------------------------
    #: Wall thickness for the Korteweg wall-compliance term D/(E e) [m].
    #: Default: D/12 (typical heavy-wall subsea line pipe ratio).
    wall_thickness_m: Positive | None = None
    youngs_modulus_gpa: Annotated[float, Field(gt=1, lt=1000)] = 207.0
    #: Explicit effective wall/structure compliance [1/bar]; overrides the
    #: Korteweg term (used for annuli, where casing/formation stiffness
    #: rather than a thin wall governs the volume change).
    wall_compliance_1_bar: NonNeg | None = None
    #: Flow area override [m2] (annulus: area between tubing and casing; the
    #: inner diameter is then the hydraulic diameter used for friction).
    flow_area_m2: Positive | None = None
    #: Number of lumped hydraulic segments (pressure nodes). Default from
    #: the dynamics ``segment_length_m`` setting.
    hydraulic_segments: Annotated[int, Field(ge=1, le=60)] | None = None
    #: Transport/thermal cells per hydraulic segment (production path only).
    transport_cells_per_segment: Annotated[int, Field(ge=1, le=40)] | None = None


class ValveElementConfig(_ElementBase):
    type: Literal["valve"]
    tag: str
    valve_type: Literal[
        "scssv", "master", "wing", "swab", "isolation", "annulus_master", "annulus_wing", "crossover",
        "service_line", "injection_isolation",
    ]
    bore_diameter_m: Annotated[float, Field(gt=0.005, lt=2.0)]
    #: Resistance coefficient when fully open (dP = K rho v^2/2, v in bore).
    loss_coefficient_open: Positive
    #: Generic area-vs-travel characteristic used while stroking.
    characteristic: Literal["linear", "quick_opening", "equal_percentage"] = "linear"
    rangeability: Annotated[float, Field(gt=1, le=1000)] = 30.0
    supports_intermediate: bool = False
    full_stroke_time_s: Positive
    initial_position_pct: Percent
    available: bool = True
    #: Separate closing stroke time (default = full_stroke_time_s) [s].
    close_stroke_time_s: Positive | None = None
    #: Dead time between command and start of travel (control-system and
    #: hydraulic-signal latency) [s].
    actuation_delay_s: NonNeg = 0.0
    #: Specified (datasheet) stroke time used as the stroke-test reference [s].
    nominal_stroke_time_s: Positive | None = None
    #: Seat-leakage path when closed, as effective Cd*A [mm2] (0 = tight).
    #: Dynamic model only; the quasi-steady model treats closed as sealed.
    seat_leak_area_mm2: NonNeg = 0.0


class ChokeElementConfig(_ElementBase):
    type: Literal["choke"]
    tag: str
    #: Flow coefficient at 100 % opening [US gpm / psi^0.5].
    cv_max: Positive
    characteristic: Literal["linear", "quick_opening", "equal_percentage"] = "equal_percentage"
    rangeability: Annotated[float, Field(gt=1, le=1000)] = 30.0
    supports_intermediate: bool = True
    full_stroke_time_s: Positive
    initial_position_pct: Percent
    available: bool = True
    close_stroke_time_s: Positive | None = None
    actuation_delay_s: NonNeg = 0.0
    nominal_stroke_time_s: Positive | None = None
    seat_leak_area_mm2: NonNeg = 0.0
    #: "production" choke or "metering" (chemical-injection control) valve.
    service: Literal["production", "metering"] = "production"


class CheckValveConfig(_ElementBase):
    """Non-return valve (dynamic model only): passes flow from -> to once the
    differential exceeds the cracking pressure, blocks reverse flow."""

    type: Literal["check_valve"]
    tag: str
    cracking_pressure_bar: NonNeg = 0.5
    #: Flow coefficient when open [US gpm / psi^0.5].
    cv: Positive = 1.0


ElementConfig = Annotated[
    Union[InflowElementConfig, PipeElementConfig, ValveElementConfig, ChokeElementConfig],
    Field(discriminator="type"),
]
BranchElementConfig = Annotated[
    Union[PipeElementConfig, ValveElementConfig, ChokeElementConfig, CheckValveConfig],
    Field(discriminator="type"),
]


class InstrumentResponseConfig(_Strict):
    """Transmitter dynamics (dynamic model only). Applied ON TOP of the
    modelled process dynamics - never a substitute for them."""

    #: First-order sensor time constant [s] (0 = instantaneous).
    time_constant_s: NonNeg = 0.0
    #: Output update (sample-and-hold) interval [s] (0 = every solver step).
    update_interval_s: NonNeg = 0.0
    #: Output resolution in the instrument's engineering unit (0 = none).
    resolution: NonNeg = 0.0


class InstrumentConfig(_Strict):
    tag: str
    type: Literal["pressure", "temperature", "flow", "differential_pressure", "concentration"]
    description: str
    #: Node measured (pressure / temperature / flow / concentration).
    node: str | None = None
    #: Alternative location: a pipe element (+ distance from its inlet for
    #: pressure / temperature / concentration). Dynamic model only.
    element: str | None = None
    distance_m: NonNeg | None = None
    #: High / low nodes for a differential measurement.
    high_node: str | None = None
    low_node: str | None = None
    #: Concentration analysers: chemical id (see ``chemicals``).
    chemical: str | None = None
    #: Calibrated range in the instrument's engineering unit:
    #: bara (pressure), bar (differential), degC (temperature), m3/d (flow),
    #: ``unit`` (concentration: "ppm" or "vol%").
    range_min: float
    range_max: float
    unit: Literal["ppm", "vol%"] | None = None
    response: InstrumentResponseConfig | None = None

    @model_validator(mode="after")
    def _check(self) -> "InstrumentConfig":
        if self.range_max <= self.range_min:
            raise ValueError(f"{self.tag}: range_max must exceed range_min")
        if self.type == "differential_pressure":
            if not (self.high_node and self.low_node):
                raise ValueError(f"{self.tag}: differential instrument needs high_node and low_node")
        elif not self.node and not self.element:
            raise ValueError(f"{self.tag}: instrument needs a node (or an element)")
        if self.element and self.type != "flow" and self.distance_m is None:
            raise ValueError(f"{self.tag}: element-located instrument needs distance_m")
        if self.type == "concentration" and not self.chemical:
            raise ValueError(f"{self.tag}: concentration analyser needs a chemical")
        return self


class TrainingRulesConfig(_Strict):
    """Training rules (NOT real interlocks). Violations produce warnings."""

    #: Warn when an isolation valve is commanded open with a differential
    #: across it larger than this [bar]. Teaches pressure equalisation.
    max_opening_differential_bar: Positive | None = None


class LayoutPoint(_Strict):
    x: float
    y: float


class LayoutConfig(_Strict):
    """Schematic layout (presentation only, no engineering meaning)."""

    width: Positive = 1000
    height: Positive = 640
    nodes: dict[str, LayoutPoint]
    #: Optional intermediate polyline points per element.
    waypoints: dict[str, list[LayoutPoint]] = Field(default_factory=dict)
    instruments: dict[str, LayoutPoint] = Field(default_factory=dict)
    annotations: list[dict] = Field(default_factory=list)
    #: Where along its drawn line a valve / choke symbol sits (0..1, default
    #: 0.5). Presentation only.
    symbol_fraction: dict[str, Annotated[float, Field(ge=0, le=1)]] = Field(default_factory=dict)


class ReservoirTransientConfig(_Strict):
    """Radial single-phase reservoir diffusion (dynamic model only).

    Permeability-thickness is NOT an independent input: it is derived from
    the configured productivity index so that the dynamic model's steady
    state reproduces the quasi-steady linear IPR exactly:
        kh = J mu (ln(re/rw) + S) / (2 pi).
    """

    net_thickness_m: Positive = 20.0
    porosity: Annotated[float, Field(gt=0.01, lt=0.5)] = 0.2
    #: Total (rock + fluid) compressibility [1/bar].
    total_compressibility_1_bar: Annotated[float, Field(gt=1e-7, lt=1e-2)] = 1.5e-4
    wellbore_radius_m: Annotated[float, Field(gt=0.02, lt=1.0)] = 0.108
    #: Radius of the constant-pressure outer boundary [m].
    drainage_radius_m: Annotated[float, Field(gt=5, lt=20_000)] = 300.0
    skin: Annotated[float, Field(ge=0, lt=50)] = 0.0
    radial_cells: Annotated[int, Field(ge=3, le=40)] = 14


class FluidZoneConfig(_Strict):
    """Constant-property liquid occupying a branch subsystem (annulus brine,
    chemical in an injection line)."""

    name: str
    density_kg_m3: Annotated[float, Field(gt=100, lt=2000)]
    viscosity_cp: Annotated[float, Field(gt=0.01, lt=10_000)]
    specific_heat_j_kgk: Annotated[float, Field(gt=100, lt=10_000)] = 2500.0
    thermal_expansion_1_k: Annotated[float, Field(ge=0, lt=0.01)] = 0.0
    compressibility_1_bar: Annotated[float, Field(gt=0, lt=1e-2)] = 5.0e-5


class BranchBoundaryConfig(_Strict):
    node: str
    pressure_bara: Annotated[float, Field(gt=0, lt=2000)]
    description: str = ""


class BranchNodeConfig(NodeConfig):
    #: Fluid zone occupying the node ("production" or a ``fluids`` key).
    zone: str = "production"


class SubsystemsConfig(_Strict):
    """Branches attached to the production path (dynamic model only):
    annulus, chemical-injection circuits, crossover, service lines."""

    fluids: dict[str, FluidZoneConfig] = Field(default_factory=dict)
    nodes: list[BranchNodeConfig] = Field(default_factory=list)
    elements: list[BranchElementConfig] = Field(default_factory=list)
    boundaries: list[BranchBoundaryConfig] = Field(default_factory=list)
    #: Additional instruments (branches, mid-line, analysers).
    instruments: list[InstrumentConfig] = Field(default_factory=list)


class PumpConfig(_Strict):
    """Chemical-injection pressure source, referred to the subsea
    distribution point (pump discharge minus umbilical losses plus static
    head): modelled as an ideal pressure source while running."""

    discharge_pressure_bara: Annotated[float, Field(gt=1, lt=2000)]
    #: Pressure at the supply point with the pump stopped (static head of
    #: the chemical column in the umbilical) [bara].
    static_pressure_bara: Annotated[float, Field(gt=0, lt=2000)]
    running: bool = True
    max_discharge_pressure_bara: Annotated[float, Field(gt=1, lt=2000)] = 690.0


class ChemicalConfig(_Strict):
    id: str
    name: str
    #: Fluid zone of the injection line (a ``subsystems.fluids`` key).
    fluid: str
    supply_node: str
    injection_node: str
    isolation_valve: str
    control_valve: str
    check_valve: str | None = None
    pressure_transmitter: str | None = None
    flow_transmitter: str | None = None
    #: Optional second route from the same pump into the ANNULUS service line
    #: (methanol for service-line flushing / annulus bullheading): its own
    #: supply node, isolation valve, non-return valve and flow transmitter.
    annulus_supply_node: str | None = None
    annulus_valve: str | None = None
    annulus_check_valve: str | None = None
    annulus_flow_transmitter: str | None = None
    pump: PumpConfig
    #: Temperature of the chemical as it enters the production stream.
    injection_temperature_c: float = 4.0
    #: Preferred display unit for concentrations of this chemical.
    display_unit: Literal["ppm", "vol%"] = "ppm"
    #: Training dosage band (illustrative) in display unit.
    target_min: float | None = None
    target_max: float | None = None
    color: str = "#e879f9"


class AnnulusThermalConfig(_Strict):
    """Lumped annulus-fluid temperature:
        dT_ann/dt = (w T_tubing + (1 - w) T_geothermal - T_ann) / tau"""

    #: Annulus pipe elements whose fluid follows this lumped temperature.
    elements: list[str]
    time_constant_s: Positive = 21_600.0
    tubing_weight: Annotated[float, Field(ge=0, le=1)] = 0.8
    tubing_elements: list[str] = Field(default_factory=list)
    geothermal_mean_c: float = 50.0


class IntegrityTestPreset(_Strict):
    id: str
    name: str
    type: Literal["pressure_hold", "inflow", "stroke"]
    description: str = ""
    test_node: str | None = None
    pressure_transmitter: str | None = None
    valve: str | None = None
    stabilisation_s: NonNeg = 300.0
    duration_s: Positive = 900.0
    #: Acceptance: max pressure change during the hold [bar] (pressure tests)
    #: or max deviation from the nominal stroke time [%] (stroke test).
    max_change_bar: Positive = 2.0
    stroke_tolerance_pct: Positive = 20.0


class DynamicsConfig(_Strict):
    #: Default simulation mode for this scenario.
    mode: Literal["dynamic", "steady"] = "dynamic"
    #: Target hydraulic segment length when a pipe gives no explicit count [m].
    segment_length_m: Positive = 250.0
    #: Transport/thermal cells per hydraulic segment (default).
    transport_cells_per_segment: Annotated[int, Field(ge=1, le=40)] = 5
    #: Minimum lumped volume of any pressure node (regularises zero-volume
    #: junctions between two valves) [m3].
    minimum_node_volume_m3: Positive = 0.002
    reservoir: ReservoirTransientConfig | None = None
    annulus_thermal: AnnulusThermalConfig | None = None
    #: Time of day at simulation time zero (display only) [s after midnight].
    clock_start_s: NonNeg = 8 * 3600.0
    #: Default instrument response per instrument type.
    default_response: dict[str, InstrumentResponseConfig] = Field(default_factory=dict)


class ScenarioConfig(_Strict):
    id: str
    name: str
    description: str
    data_classification: str = "ILLUSTRATIVE - not field data"
    fluid: FluidConfig
    reservoir: ReservoirConfig
    boundary: BoundaryConfig
    reservoir_node: str
    nodes: list[NodeConfig]
    elements: list[ElementConfig]
    instruments: list[InstrumentConfig]
    training_rules: TrainingRulesConfig = Field(default_factory=TrainingRulesConfig)
    layout: LayoutConfig
    #: Release 1 scenarios that do not configure dynamics run quasi-steady.
    dynamics: DynamicsConfig = Field(default_factory=lambda: DynamicsConfig(mode="steady"))
    subsystems: SubsystemsConfig = Field(default_factory=SubsystemsConfig)
    chemicals: list[ChemicalConfig] = Field(default_factory=list)
    integrity_tests: list[IntegrityTestPreset] = Field(default_factory=list)
    #: Briefing notes shown to the intern (operation to try, what to
    #: watch). Text only; every response is calculated by the model.
    briefing: list[str] = Field(default_factory=list)
