"""API request schemas. All physical quantities are SI with explicit names
(``_pa`` = absolute pascal, ``_k`` = kelvin, ``_si`` = (m3/s)/Pa)."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Req(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateSessionRequest(_Req):
    scenario_id: str = "base_single_phase"


class LifecycleRequest(_Req):
    action: Literal["start", "pause", "resume", "reset"]


class SpeedRequest(_Req):
    time_scale: float


class LoadScenarioRequest(_Req):
    scenario_id: str


class ValveCommandRequest(_Req):
    command: Literal["open", "close", "set_position"]
    position_pct: Annotated[float, Field(ge=0, le=100)] | None = None


class BoundaryUpdate(_Req):
    # 1 bara .. 2000 bara
    reservoir_pressure_pa: Annotated[float, Field(gt=1.0e5, le=2.0e8)] | None = None
    # 0.01 .. 10 000 (m3/d)/bar expressed in (m3/s)/Pa
    productivity_index_si: Annotated[float, Field(gt=1.157e-12, le=1.158e-6)] | None = None
    # -10 .. 250 degC
    reservoir_temperature_k: Annotated[float, Field(gt=263.15, lt=523.15)] | None = None
    downstream_pressure_pa: Annotated[float, Field(gt=0.0, le=2.0e8)] | None = None


class FluidUpdate(_Req):
    density_kg_m3: Annotated[float, Field(gt=100, lt=2000)] | None = None
    viscosity_pas: Annotated[float, Field(gt=1e-5, lt=10)] | None = None
    specific_heat_j_kgk: Annotated[float, Field(gt=100, lt=10_000)] | None = None
    thermal_expansion_1_k: Annotated[float, Field(ge=0, lt=0.01)] | None = None
    bubble_point_pressure_pa: Annotated[float, Field(ge=0, le=2.0e8)] | None = None


class BlackOilUpdate(_Req):
    producing_gor_sm3_sm3: Annotated[float, Field(ge=0, le=2000)] | None = None
    water_cut: Annotated[float, Field(ge=0, le=0.98)] | None = None
    oil_api: Annotated[float, Field(ge=10, le=70)] | None = None
    gas_specific_gravity: Annotated[float, Field(ge=0.55, le=1.5)] | None = None
    water_salinity_wt_pct: Annotated[float, Field(ge=0, le=26)] | None = None
    correlation: Literal["beggs_brill", "no_slip"] | None = None


class MPFMFaultRequest(_Req):
    dp_offset_bar: Annotated[float, Field(ge=-1, le=1)] | None = None
    dp_stuck: bool | None = None
    gamma_failed: bool | None = None
    pt_failed: bool | None = None


class JobRequest(_Req):
    kind: Annotated[str, Field(min_length=1, max_length=64)]
    params: dict = Field(default_factory=dict)


class SurrogatePredictRequest(_Req):
    inputs: dict[str, float]


class SurrogateImportRequest(_Req):
    name: Annotated[str, Field(min_length=1, max_length=80)]
    method: Literal["gp", "poly"] = "gp"
    inputs: Annotated[list[str], Field(min_length=1, max_length=7)]
    outputs: Annotated[list[str], Field(min_length=1, max_length=9)]
    csv: str = Field(max_length=2_000_000)


class RecordRequest(_Req):
    label: Annotated[str, Field(min_length=1, max_length=120)]
    notes: Annotated[str, Field(max_length=2000)] | None = None
    #: Attach the result of a completed scenario-comparison job of this session.
    comparison_job_id: Annotated[str, Field(max_length=64)] | None = None


class SandCsvRequest(_Req):
    csv: str = Field(max_length=2_000_000)
    replace: bool = False


class FastForwardRequest(_Req):
    days: Annotated[float, Field(gt=0, le=3650)]


class FluidModelRequest(_Req):
    model: Literal["single_phase", "black_oil"]


class ModeRequest(_Req):
    mode: Literal["steady", "dynamic"]


class PumpRequest(_Req):
    running: bool | None = None
    # 1 .. 2000 bara
    discharge_pressure_pa: Annotated[float, Field(gt=1.0e5, le=2.0e8)] | None = None


class IntegrityTestRequest(_Req):
    type: Literal["pressure_hold", "inflow", "stroke"]
    name: str | None = None
    test_node: str | None = None
    transmitter: str | None = None
    valve: str | None = None
    stabilisation_s: Annotated[float, Field(ge=0, le=86_400)] = 300.0
    duration_s: Annotated[float, Field(gt=0, le=86_400)] = 900.0
    max_change_bar: Annotated[float, Field(gt=0, le=1000)] = 2.0
    stroke_tolerance_pct: Annotated[float, Field(gt=0, le=200)] = 20.0


class TrainingStartRequest(_Req):
    exercise_id: str


class TrainingAnswerRequest(_Req):
    step_id: str
    choice: str


class SelectorCommandRequest(_Req):
    command: Literal["open", "close"]


class SupplyRequest(_Req):
    available: bool
