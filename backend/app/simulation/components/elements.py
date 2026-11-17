"""Runtime component definitions for the flow path.

Each element connects two nodes and provides its signed pressure drop in the
flow direction, ``dp(q, fluid)`` [Pa]. Elements are created from the scenario
configuration by ``app.simulation.build``; nothing here is hard-coded to a
particular tree arrangement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np

from app.core.units import cv_to_capacity, loss_coefficient_to_capacity
from app.simulation.choke.choke import choke_capacity
from app.simulation.flowline.pipe import PipeGeometry, pipe_pressure_drop
from app.simulation.hydraulics.properties import FlowProperties
from app.simulation.hydraulics.restriction import restriction_pressure_drop
from app.simulation.inflow.ipr import LinearIPR
from app.simulation.valves.actuator import Actuator
from app.simulation.valves.characteristics import Characteristic, relative_capacity

ElementKind = Literal["inflow", "pipe", "valve", "choke", "check_valve"]
Command = Literal["open", "close", "set_position"]


@dataclass
class Element:
    id: str
    name: str
    from_node: str
    to_node: str

    kind: ElementKind = field(init=False)
    #: True if the element has no fluid volume (valves, chokes, inflow).
    zero_volume: bool = field(init=False, default=True)

    def is_closed(self) -> bool:
        return False

    def dp(self, q: float, props: FlowProperties) -> float:  # pragma: no cover - abstract
        raise NotImplementedError

    def static_dp(self, props: FlowProperties) -> float:
        """Pressure drop at zero flow (hydrostatic only)."""
        return 0.0


@dataclass
class InflowElement(Element):
    ipr: LinearIPR = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.kind = "inflow"

    def dp(self, q: float, props: FlowProperties) -> float:
        return self.ipr.drawdown(q)


@dataclass
class PipeElement(Element):
    geometry: PipeGeometry = None  # type: ignore[assignment]
    role: str = "flowline"
    overall_htc: float = 0.0  # W/(m2 K), inner-surface referred
    ambient_in: float = 277.15  # K
    ambient_out: float = 277.15  # K
    thermal_cells: int = 20

    def __post_init__(self) -> None:
        self.kind = "pipe"
        self.zero_volume = False

    def dp(self, q: float, props: FlowProperties) -> float:
        return pipe_pressure_drop(q, props.rho, props.mu, self.geometry)

    def static_dp(self, props: FlowProperties) -> float:
        return pipe_pressure_drop(0.0, props.rho, props.mu, self.geometry)


@dataclass
class RestrictionElement(Element):
    """Common behaviour for valves and chokes: actuator + capacity."""

    tag: str = ""
    actuator: Actuator = None  # type: ignore[assignment]
    characteristic: Characteristic = "linear"
    rangeability: float = 30.0
    supports_intermediate: bool = False
    available: bool = True
    subtype: str = ""
    #: Seat-leakage capacity Cd*A when closed [m2] (dynamic model only).
    seat_leak_capacity: float = 0.0
    #: Datasheet stroke time for stroke testing [s] (None = full stroke time).
    nominal_stroke_time_s: float | None = None

    def capacity_at(self, position_pct: float) -> float:  # pragma: no cover - abstract
        raise NotImplementedError

    @property
    def capacity(self) -> float:
        return self.capacity_at(self.actuator.position_pct)

    def is_closed(self) -> bool:
        return self.capacity <= 0.0

    def dp(self, q: float, props: FlowProperties) -> float:
        return restriction_pressure_drop(q, props.rho, self.capacity)

    def supported_commands(self) -> list[Command]:
        if not self.available:
            return []
        cmds: list[Command] = ["open", "close"]
        if self.supports_intermediate:
            cmds.append("set_position")
        return cmds

    def validate_command(self, command: str, position_pct: float | None) -> float:
        """Return the target position or raise ``CommandRejected``."""
        if not self.available:
            raise CommandRejected(f"{self.tag} is unavailable (faulted) and cannot be operated")
        if command == "open":
            return 100.0
        if command == "close":
            return 0.0
        if command == "set_position":
            if not self.supports_intermediate:
                raise CommandRejected(
                    f"{self.tag} is a discrete isolation valve: only OPEN / CLOSE are supported"
                )
            if position_pct is None:
                raise CommandRejected("set_position requires position_pct")
            if not 0.0 <= position_pct <= 100.0:
                raise CommandRejected("position_pct must be between 0 and 100 %")
            return float(position_pct)
        raise CommandRejected(f"unknown command {command!r}")


@dataclass
class ValveElement(RestrictionElement):
    bore_diameter: float = 0.1
    loss_coefficient_open: float = 0.2

    def __post_init__(self) -> None:
        self.kind = "valve"
        self._c_open = loss_coefficient_to_capacity(self.loss_coefficient_open, self.bore_diameter)

    def capacity_at(self, position_pct: float) -> float:
        return self._c_open * relative_capacity(self.characteristic, position_pct / 100.0, self.rangeability)


@dataclass
class ChokeElement(RestrictionElement):
    cv_max: float = 100.0
    service: str = "production"
    #: Vendor Cv vs opening table [(position %, Cv), ...] for the NEW trim;
    #: replaces the generic characteristic when given.
    cv_table: list[tuple[float, float]] | None = None
    #: Stepping actuator: number of steps for full travel (positions are
    #: quantised to whole steps); None = continuous.
    steps: int | None = None
    #: Trim wear: capacity multiplier as a function of position (eroded /
    #: new open flow area), set by the choke-erosion model. None = new trim.
    wear_factor: object | None = None

    def __post_init__(self) -> None:
        self.kind = "choke"
        self.subtype = "choke" if self.service == "production" else "metering"

    def nominal_cv_at(self, position_pct: float) -> float:
        if self.cv_table:
            xs = [p for p, _ in self.cv_table]
            ys = [c for _, c in self.cv_table]
            if position_pct <= 0.0:
                return 0.0
            return float(np.interp(position_pct, xs, ys))
        return self.cv_max * relative_capacity(self.characteristic, position_pct / 100.0, self.rangeability)

    def capacity_at(self, position_pct: float) -> float:
        if self.cv_table:
            c = cv_to_capacity(self.nominal_cv_at(position_pct))
        else:
            c = choke_capacity(self.cv_max, position_pct, self.characteristic, self.rangeability)
        if self.wear_factor is not None and c > 0:
            c *= float(self.wear_factor(position_pct))  # type: ignore[operator]
        return c

    def validate_command(self, command: str, position_pct: float | None) -> float:
        target = super().validate_command(command, position_pct)
        if self.steps:
            target = round(target / 100.0 * self.steps) / self.steps * 100.0
        return target


@dataclass
class CheckValveElement(Element):
    """Non-return valve. Not operable; state follows the differential.
    Only the dynamic network model represents it (branch subsystems)."""

    tag: str = ""
    cracking_pressure: float = 0.5e5  # Pa
    capacity_open: float = 1e-5  # m2

    def __post_init__(self) -> None:
        self.kind = "check_valve"


class CommandRejected(ValueError):
    """A component command that is invalid for the configured component."""
