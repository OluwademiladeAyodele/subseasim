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

InstrumentType = Literal["pressure", "temperature", "flow", "differential_pressure"]
Status = Literal["GOOD", "OUT_OF_RANGE_HIGH", "OUT_OF_RANGE_LOW", "UNDETERMINED", "BAD"]

SI_UNIT: dict[str, str] = {
    "pressure": "Pa(a)",
    "differential_pressure": "Pa",
    "temperature": "K",
    "flow": "m3/s",
}


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

    @property
    def unit(self) -> str:
        return SI_UNIT[self.type]


@dataclass
class Reading:
    tag: str
    pv: float | None
    value: float | None
    status: Status


def measure(
    inst: Instrument,
    calc_ok: bool,
    node_pressure: dict[str, float | None],
    node_temperature: dict[str, float],
    q: float,
) -> Reading:
    if not calc_ok:
        return Reading(inst.tag, None, None, "BAD")
    pv: float | None
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
