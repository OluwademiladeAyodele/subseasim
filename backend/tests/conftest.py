from __future__ import annotations

import pytest

from app.scenarios.loader import get_scenario
from app.simulation.components.elements import (
    ChokeElement,
    InflowElement,
    PipeElement,
    ValveElement,
)
from app.simulation.engine import SimulationEngine
from app.simulation.flowline.pipe import PipeGeometry
from app.simulation.inflow.ipr import LinearIPR
from app.simulation.topology.topology import Node, SeriesTopology
from app.simulation.valves.actuator import Actuator


@pytest.fixture
def engine() -> SimulationEngine:
    return SimulationEngine(get_scenario("base_single_phase"))


def make_topology(ipr: LinearIPR, *, pipe: PipeGeometry | None = None, valve_k: float | None = None,
                  choke_cv: float | None = None, choke_pos: float = 100.0, valve_pos: float = 100.0,
                  z_out: float = 0.0):
    """Minimal programmatic topology for analytical reference tests."""
    nodes = [Node("RES", "res", 0.0), Node("A", "a", 0.0)]
    elements = [InflowElement("IPR", "ipr", "RES", "A", ipr=ipr)]
    last = "A"
    k = 0
    if pipe is not None:
        k += 1
        nid = f"P{k}"
        nodes.append(Node(nid, nid, z_out))
        elements.append(PipeElement("PIPE", "pipe", last, nid, geometry=pipe, overall_htc=0.0, thermal_cells=10))
        last = nid
    if valve_k is not None:
        k += 1
        nid = f"V{k}"
        nodes.append(Node(nid, nid, z_out))
        elements.append(ValveElement("VALVE", "valve", last, nid, tag="XV-1", actuator=Actuator(valve_pos, valve_pos, 10.0),
                                     bore_diameter=0.1, loss_coefficient_open=valve_k))
        last = nid
    if choke_cv is not None:
        k += 1
        nid = f"C{k}"
        nodes.append(Node(nid, nid, z_out))
        elements.append(ChokeElement("CHOKE", "choke", last, nid, tag="CHK-1", actuator=Actuator(choke_pos, choke_pos, 10.0),
                                     characteristic="linear", supports_intermediate=True, cv_max=choke_cv))
        last = nid
    return SeriesTopology.build(nodes, elements, "RES", last)
