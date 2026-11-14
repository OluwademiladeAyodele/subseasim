"""Model-validity and engineering diagnostics.

Diagnostics never alter results. They report when the operating point lies
outside the assumptions of the Release 1 model so that the trainee (and the
UI) can see that a number should not be trusted.

severity:
    error    result is physically invalid or unavailable -> readings flagged
    warning  model assumption violated; numbers shown but not trustworthy
    info     noteworthy model behaviour (e.g. trapped pressure retained)
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

from app.core.units import pa_to_bara
from app.simulation.components.elements import PipeElement
from app.simulation.flowline.pipe import pipe_reynolds
from app.simulation.fluid_properties.base import FluidModel
from app.simulation.hydraulics.friction import RE_LAMINAR_LIMIT, RE_TURBULENT_LIMIT
from app.simulation.hydraulics.network import HydraulicResult
from app.simulation.hydraulics.properties import FlowProperties
from app.simulation.topology.topology import SeriesTopology

Severity = Literal["error", "warning", "info"]


@dataclass
class Diagnostic:
    severity: Severity
    code: str
    message: str
    location: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def run_diagnostics(
    topology: SeriesTopology,
    hyd: HydraulicResult,
    fluid: FluidModel,
    props: FlowProperties,
    node_temperature: dict[str, float],
) -> list[Diagnostic]:
    out: list[Diagnostic] = []
    if not hyd.ok:
        out.append(Diagnostic("error", "SOLVER_FAILED", f"No valid operating point: {hyd.message}"))
        return out

    for nid, p in hyd.node_pressure.items():
        if p is None:
            continue
        name = topology.nodes[nid].name
        if p <= 0.0:
            out.append(Diagnostic(
                "error", "NEGATIVE_ABSOLUTE_PRESSURE",
                f"Calculated absolute pressure at {name} is {pa_to_bara(p):.2f} bara (<= 0). "
                "A liquid cannot sustain this; the operating point is not physically valid for this model "
                "(e.g. the static liquid column cannot reach this point).",
                nid,
            ))
            continue
        t = node_temperature.get(nid)
        p_bub = fluid.bubble_point_pressure(t if t is not None else 0.0)
        if p < p_bub:
            out.append(Diagnostic(
                "warning", "BELOW_BUBBLE_POINT",
                f"Pressure at {name} ({pa_to_bara(p):.1f} bara) is below the configured bubble point "
                f"({pa_to_bara(p_bub):.1f} bara). Gas would come out of solution; the single-phase "
                "liquid model is not valid here.",
                nid,
            ))

    if hyd.q < 0:
        out.append(Diagnostic(
            "warning", "REVERSE_FLOW",
            "Flow is reversed (downstream fluid flowing into the well): the downstream pressure plus "
            "hydrostatic head exceeds reservoir pressure. Release 1 assumes the same fluid and "
            "injectivity equal to productivity; real cross-flow behaviour is not represented.",
        ))

    if hyd.q != 0:
        for e in topology.path:
            if isinstance(e, PipeElement):
                re = pipe_reynolds(hyd.q, props.rho, props.mu, e.geometry)
                if RE_LAMINAR_LIMIT < re < RE_TURBULENT_LIMIT:
                    out.append(Diagnostic(
                        "info", "TRANSITIONAL_FLOW",
                        f"{e.name}: Reynolds number {re:.0f} is in the laminar-turbulent transition; "
                        "friction factor is uncertain.",
                        e.id,
                    ))

    for note in hyd.notes:
        out.append(Diagnostic("info", "TRAPPED_SECTION", note))
    return out
