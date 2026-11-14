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


class TrainingStartRequest(_Req):
    exercise_id: str


class TrainingAnswerRequest(_Req):
    step_id: str
    choice: str
