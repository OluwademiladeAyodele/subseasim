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
    role: Literal["tubing", "flowline", "jumper"] = "flowline"
    length_m: Positive
    inner_diameter_m: Annotated[float, Field(gt=0.005, lt=2.0)]
    roughness_m: NonNeg = 4.5e-5
    #: Overall heat-transfer coefficient referred to the INNER surface.
    overall_htc_w_m2k: NonNeg
    ambient_temperature_inlet_c: float
    ambient_temperature_outlet_c: float
    thermal_cells: Annotated[int, Field(ge=1, le=200)] = 20


class ValveElementConfig(_ElementBase):
    type: Literal["valve"]
    tag: str
    valve_type: Literal["scssv", "master", "wing", "isolation"]
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


ElementConfig = Annotated[
    Union[InflowElementConfig, PipeElementConfig, ValveElementConfig, ChokeElementConfig],
    Field(discriminator="type"),
]


class InstrumentConfig(_Strict):
    tag: str
    type: Literal["pressure", "temperature", "flow", "differential_pressure"]
    description: str
    #: Node measured (pressure / temperature / flow).
    node: str | None = None
    #: High / low nodes for a differential measurement.
    high_node: str | None = None
    low_node: str | None = None
    #: Calibrated range in the instrument's engineering unit:
    #: bara (pressure), bar (differential), degC (temperature), m3/d (flow).
    range_min: float
    range_max: float

    @model_validator(mode="after")
    def _check(self) -> "InstrumentConfig":
        if self.range_max <= self.range_min:
            raise ValueError(f"{self.tag}: range_max must exceed range_min")
        if self.type == "differential_pressure":
            if not (self.high_node and self.low_node):
                raise ValueError(f"{self.tag}: differential instrument needs high_node and low_node")
        elif not self.node:
            raise ValueError(f"{self.tag}: instrument needs a node")
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
