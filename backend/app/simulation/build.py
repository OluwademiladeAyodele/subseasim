"""Build runtime simulation objects (SI units) from a scenario configuration."""

from __future__ import annotations

from dataclasses import dataclass

from app.core import units as u
from app.models.scenario import (
    ChokeElementConfig,
    FluidConfig,
    InflowElementConfig,
    InstrumentConfig,
    PipeElementConfig,
    ScenarioConfig,
    ValveElementConfig,
)
from app.simulation.components.elements import ChokeElement, Element, InflowElement, PipeElement, ValveElement
from app.simulation.flowline.pipe import PipeGeometry
from app.simulation.fluid_properties.constant_liquid import ConstantPropertyLiquid
from app.simulation.inflow.ipr import LinearIPR
from app.simulation.instruments.instruments import Instrument
from app.simulation.topology.topology import Node, SeriesTopology, TopologyError
from app.simulation.valves.actuator import Actuator


@dataclass
class BuiltSystem:
    topology: SeriesTopology
    fluid: ConstantPropertyLiquid
    ipr: LinearIPR
    p_boundary: float
    t_boundary_fluid: float
    instruments: list[Instrument]


def build_fluid(cfg: FluidConfig) -> ConstantPropertyLiquid:
    return ConstantPropertyLiquid(
        name=cfg.name,
        rho=cfg.density_kg_m3,
        mu=u.cp_to_pas(cfg.viscosity_cp),
        cp=cfg.specific_heat_j_kgk,
        beta=cfg.thermal_expansion_1_k,
        p_bubble=u.bara_to_pa(cfg.bubble_point_pressure_bara) if cfg.bubble_point_pressure_bara > 0 else 0.0,
    )


def _instrument_range_si(cfg: InstrumentConfig) -> tuple[float, float]:
    conv = {
        "pressure": u.bara_to_pa,
        "differential_pressure": u.bar_to_pa_delta,
        "temperature": u.c_to_k,
        "flow": u.m3d_to_m3s,
    }[cfg.type]
    return conv(cfg.range_min), conv(cfg.range_max)


def build_system(cfg: ScenarioConfig) -> BuiltSystem:
    nodes = [Node(n.id, n.name, n.elevation_m) for n in cfg.nodes]
    node_elev = {n.id: n.elevation for n in nodes}
    ipr = LinearIPR(
        p_res=u.bara_to_pa(cfg.reservoir.pressure_bara),
        j=u.pi_m3d_per_bar_to_si(cfg.reservoir.productivity_index_m3d_per_bar),
        t_res=u.c_to_k(cfg.reservoir.temperature_c),
    )
    elements: list[Element] = []
    for ec in cfg.elements:
        base = dict(id=ec.id, name=ec.name, from_node=ec.from_node, to_node=ec.to_node)
        if isinstance(ec, InflowElementConfig):
            elements.append(InflowElement(**base, ipr=ipr))
        elif isinstance(ec, PipeElementConfig):
            for nid in (ec.from_node, ec.to_node):
                if nid not in node_elev:
                    raise TopologyError(f"element {ec.id!r} references unknown node {nid!r}")
            geom = PipeGeometry(
                length=ec.length_m,
                diameter=ec.inner_diameter_m,
                roughness=ec.roughness_m,
                dz=node_elev[ec.to_node] - node_elev[ec.from_node],
            )
            elements.append(PipeElement(
                **base, geometry=geom, role=ec.role, overall_htc=ec.overall_htc_w_m2k,
                ambient_in=u.c_to_k(ec.ambient_temperature_inlet_c),
                ambient_out=u.c_to_k(ec.ambient_temperature_outlet_c),
                thermal_cells=ec.thermal_cells,
            ))
        elif isinstance(ec, ValveElementConfig):
            pos = ec.initial_position_pct
            if not ec.supports_intermediate and pos not in (0.0, 100.0):
                raise ValueError(f"{ec.tag}: discrete valve initial position must be 0 or 100 %")
            elements.append(ValveElement(
                **base, tag=ec.tag, subtype=ec.valve_type,
                actuator=Actuator(pos, pos, ec.full_stroke_time_s),
                characteristic=ec.characteristic, rangeability=ec.rangeability,
                supports_intermediate=ec.supports_intermediate, available=ec.available,
                bore_diameter=ec.bore_diameter_m, loss_coefficient_open=ec.loss_coefficient_open,
            ))
        elif isinstance(ec, ChokeElementConfig):
            pos = ec.initial_position_pct
            elements.append(ChokeElement(
                **base, tag=ec.tag,
                actuator=Actuator(pos, pos, ec.full_stroke_time_s),
                characteristic=ec.characteristic, rangeability=ec.rangeability,
                supports_intermediate=ec.supports_intermediate, available=ec.available,
                cv_max=ec.cv_max,
            ))
    topology = SeriesTopology.build(nodes, elements, cfg.reservoir_node, cfg.boundary.node)

    tags = [e.tag for e in elements if hasattr(e, "tag")] + [i.tag for i in cfg.instruments]
    if len(tags) != len(set(tags)):
        raise ValueError("component and instrument tags must be unique")

    instruments = []
    for ic in cfg.instruments:
        for nid in (ic.node, ic.high_node, ic.low_node):
            if nid is not None and nid not in topology.nodes:
                raise TopologyError(f"instrument {ic.tag} references unknown node {nid!r}")
        lo, hi = _instrument_range_si(ic)
        instruments.append(Instrument(ic.tag, ic.type, ic.description, ic.node, ic.high_node, ic.low_node, lo, hi))

    return BuiltSystem(
        topology=topology,
        fluid=build_fluid(cfg.fluid),
        ipr=ipr,
        p_boundary=u.bara_to_pa(cfg.boundary.pressure_bara),
        t_boundary_fluid=u.c_to_k(cfg.boundary.fluid_temperature_c),
        instruments=instruments,
    )
