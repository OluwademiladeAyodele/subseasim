"""Instrumentation model.

The *process variable* (PV) is the model's calculated value at the
instrument location. The *measurement* is what the transmitter reports.
They are kept separate so that calibration error, noise, drift, frozen
output, etc. can be introduced in Release 2 without touching the physics.

Release 1 transmitters are IDEAL within their calibrated range:
    measurement = PV                       status GOOD
    PV outside range -> clamped to limit  status OUT_OF_RANGE_HIGH / _LOW
    PV undetermined (trapped, no history) status UNDETERMINED, no value
    calculation failed                    status BAD, no value
No value is ever substituted when the calculation is unavailable.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

InstrumentType = Literal["pressure", "temperature", "flow", "differential_pressure", "concentration"]
#: NOT_MODELLED: the instrument sits on a subsystem that the active model
#: does not represent (branch subsystems in quasi-steady mode).
Status = Literal["GOOD", "OUT_OF_RANGE_HIGH", "OUT_OF_RANGE_LOW", "UNDETERMINED", "BAD", "NOT_MODELLED"]

SI_UNIT: dict[str, str] = {
    "pressure": "Pa(a)",
    "differential_pressure": "Pa",
    "temperature": "K",
    "flow": "m3/s",
    "concentration": "m3/m3",
}


@dataclass
class InstrumentResponse:
    """Transmitter dynamics, applied to the PV in the dynamic model only."""

    time_constant_s: float = 0.0
    update_interval_s: float = 0.0
    resolution_si: float = 0.0


@dataclass
class Instrument:
    tag: str
    type: InstrumentType
    description: str
    node: str | None
    high_node: str | None
    low_node: str | None
    range_min: float  # SI
    range_max: float  # SI
    element: str | None = None
    distance_m: float | None = None
    chemical: str | None = None
    display_unit: str | None = None
    response: InstrumentResponse | None = None

    @property
    def unit(self) -> str:
        return SI_UNIT[self.type]


@dataclass
class Reading:
    tag: str
    pv: float | None
    value: float | None
    status: Status


def classify(inst: Instrument, pv: float | None) -> Reading:
    """Range / validity status for an already-determined measurement value."""
    if pv is None:
        return Reading(inst.tag, None, None, "UNDETERMINED")
    if not math.isfinite(pv):
        return Reading(inst.tag, None, None, "BAD")
    if pv > inst.range_max:
        return Reading(inst.tag, pv, inst.range_max, "OUT_OF_RANGE_HIGH")
    if pv < inst.range_min:
        return Reading(inst.tag, pv, inst.range_min, "OUT_OF_RANGE_LOW")
    return Reading(inst.tag, pv, pv, "GOOD")


def measure(
    inst: Instrument,
    calc_ok: bool,
    node_pressure: dict[str, float | None],
    node_temperature: dict[str, float],
    q: float,
) -> Reading:
    if not calc_ok:
        return Reading(inst.tag, None, None, "BAD")
    if inst.type == "concentration" or inst.element is not None:
        return Reading(inst.tag, None, None, "NOT_MODELLED")
    pv: float | None
    if inst.node is not None and inst.node not in node_pressure:
        return Reading(inst.tag, None, None, "NOT_MODELLED")
    if inst.type == "pressure":
        pv = node_pressure.get(inst.node)  # type: ignore[arg-type]
    elif inst.type == "temperature":
        pv = node_temperature.get(inst.node)  # type: ignore[arg-type]
    elif inst.type == "flow":
        pv = q
    else:
        hi, lo = node_pressure.get(inst.high_node), node_pressure.get(inst.low_node)  # type: ignore[arg-type]
        pv = None if hi is None or lo is None else hi - lo
    if pv is None:
        return Reading(inst.tag, None, None, "UNDETERMINED")
    if not math.isfinite(pv):
        return Reading(inst.tag, None, None, "BAD")
    if pv > inst.range_max:
        return Reading(inst.tag, pv, inst.range_max, "OUT_OF_RANGE_HIGH")
    if pv < inst.range_min:
        return Reading(inst.tag, pv, inst.range_min, "OUT_OF_RANGE_LOW")
    return Reading(inst.tag, pv, pv, "GOOD")
