"""Engineering-workstation schematic layout (positions only - no physics).

A schematic layout is stored separately from the scenario's engineering
configuration (``app/scenarios/layouts/<id>.json``) and is linked to it only
through stable model references:

    element:<element id>         valve / choke / check valve / pipe
    instrument:<engineering tag>
    chemical:<chemical id>       injection circuit (opens its controls)
    selector:<selector tag>      control-hydraulics selector valve
    header:<header id>           control-hydraulics SCM header
    supply:<supply id>           control-hydraulics supply
    page:<route id>              navigation button

Moving a component in the layout never changes where it measures or what it
is connected to in the model; changing the physical topology is a scenario
(engineering) configuration change. See docs/CHRISTMAS_TREE_LAYOUT.md.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Point = tuple[float, float]

ComponentType = Literal[
    "gate_valve", "master_valve", "wing_valve", "swab_valve", "annulus_valve", "crossover_valve", "service_line_valve",
    "scssv", "choke", "injection_valve", "metering_valve", "check_valve", "selector_valve",
    "tag_panel", "choke_panel", "header_panel", "inline_device", "junction", "button", "mpfm",
]

LineClass = Literal["production", "annulus", "service", "chemical", "methanol", "downhole_chemical", "hydraulic"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SchLabel(_Strict):
    dx: float = 0.0
    dy: float = 0.0
    anchor: Literal["start", "middle", "end"] = "middle"


class SchComponent(_Strict):
    id: str
    type: ComponentType
    #: Primary model reference (see module docstring).
    model: str | None = None
    #: Further references (e.g. the P and T transmitters of a PTT panel).
    models: list[str] = Field(default_factory=list)
    x: float
    y: float
    w: float = 0.0
    h: float = 0.0
    #: Degrees, clockwise; 0 = flow left-to-right.
    rotation: float = 0.0
    #: Connection points in schematic coordinates, e.g. {"a": [x, y], "b": [x, y]}.
    ports: dict[str, Point] = Field(default_factory=dict)
    #: Flow path the component sits on (a SchLine id).
    flow_path: str | None = None
    #: Instrument tap point on the flow line (tag panels).
    tap: Point | None = None
    label: SchLabel | None = None
    group: str | None = None
    #: Free text shown in the inspector / tooltip (e.g. reference notes).
    note: str = ""


class SchLine(_Strict):
    id: str
    cls: LineClass
    points: list[Point]
    #: Model elements whose flow state colours the line (flowing if any of
    #: them flows). Empty = drawn static.
    elements: list[str] = Field(default_factory=list)
    #: Chemical carried (chemical lines): clicking opens its controls.
    chemical: str | None = None
    #: Non-process state source, e.g. "header:LP-A" / "supply:LP" for
    #: control-hydraulic lines (pressurised above the operating minimum).
    model: str | None = None
    #: Connection references "<component id>.<port>" (verification only).
    from_ref: str | None = None
    to_ref: str | None = None


class SchConnector(_Strict):
    id: str
    x: float
    y: float
    direction: Literal["left", "right", "up", "down"]
    label: str
    model: str | None = None
    #: Side of the label for up/down connectors (default left).
    label_side: Literal["left", "right"] = "left"


class SchGroup(_Strict):
    id: str
    label: str
    x: float
    y: float
    w: float
    h: float
    #: Draw a frame (the reference shows a frame only for the selector valves).
    frame: bool = False


class SchReference(_Strict):
    """Provenance of the layout: how coordinates were obtained."""

    source: str
    method: str
    #: Affine map photo pixel -> schematic unit: X = (px - x0) * scale, Y = (py - y0) * scale.
    photo_origin_px: Point
    scale: float
    notes: list[str] = Field(default_factory=list)


class SchematicLayout(_Strict):
    id: str
    title: str
    subtitle: str = ""
    width: float
    height: float
    reference: SchReference
    groups: list[SchGroup] = Field(default_factory=list)
    lines: list[SchLine]
    components: list[SchComponent]
    connectors: list[SchConnector] = Field(default_factory=list)
    #: Free annotations: {"type": "text"|"rect"|"bar", ...}
    annotations: list[dict] = Field(default_factory=list)
