"""Build runtime simulation objects (SI units) from a scenario configuration."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core import units as u
from app.models.scenario import (
    CheckValveConfig,
    ChokeElementConfig,
    FluidConfig,
    InflowElementConfig,
    InstrumentConfig,
    PipeElementConfig,
    ScenarioConfig,
    ValveElementConfig,
)
from app.simulation.components.elements import (
    CheckValveElement,
    ChokeElement,
    Element,
    InflowElement,
    PipeElement,
    ValveElement,
)
from app.simulation.flowline.pipe import PipeGeometry
from app.simulation.fluid_properties.constant_liquid import ConstantPropertyLiquid
from app.simulation.inflow.ipr import LinearIPR
from app.simulation.instruments.instruments import Instrument, InstrumentResponse
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
    #: Branch subsystems (annulus, chemical injection...). Modelled by the
    #: dynamic network only; the series topology above is unchanged.
    branch_nodes: dict[str, Node] = field(default_factory=dict)
    branch_elements: list[Element] = field(default_factory=list)


def build_fluid(cfg: FluidConfig) -> ConstantPropertyLiquid:
    return ConstantPropertyLiquid(
        name=cfg.name,
        rho=cfg.density_kg_m3,
        mu=u.cp_to_pas(cfg.viscosity_cp),
        cp=cfg.specific_heat_j_kgk,
        beta=cfg.thermal_expansion_1_k,
        p_bubble=u.bara_to_pa(cfg.bubble_point_pressure_bara) if cfg.bubble_point_pressure_bara > 0 else 0.0,
        compressibility=cfg.compressibility_1_bar / u.PA_PER_BAR,
    )


def _instrument_range_si(cfg: InstrumentConfig) -> tuple[float, float]:
    if cfg.type == "concentration":
        f = 1e-6 if (cfg.unit or "ppm") == "ppm" else 1e-2
        return cfg.range_min * f, cfg.range_max * f
    conv = {
        "pressure": u.bara_to_pa,
        "differential_pressure": u.bar_to_pa_delta,
        "temperature": u.c_to_k,
        "flow": u.m3d_to_m3s,
    }[cfg.type]
    return conv(cfg.range_min), conv(cfg.range_max)


def _resolution_si(cfg: InstrumentConfig, res: float) -> float:
    if res <= 0:
        return 0.0
    if cfg.type == "concentration":
        return res * (1e-6 if (cfg.unit or "ppm") == "ppm" else 1e-2)
    return {
        "pressure": u.bar_to_pa_delta,
        "differential_pressure": u.bar_to_pa_delta,
        "temperature": lambda x: x,
        "flow": u.m3d_to_m3s,
    }[cfg.type](res)


def _actuator(ec: ValveElementConfig | ChokeElementConfig) -> Actuator:
    pos = ec.initial_position_pct
    return Actuator(pos, pos, ec.full_stroke_time_s, close_stroke_time_s=ec.close_stroke_time_s, delay_s=ec.actuation_delay_s)


def build_element(ec, node_elev: dict[str, float], ipr: LinearIPR | None) -> Element:
    base = dict(id=ec.id, name=ec.name, from_node=ec.from_node, to_node=ec.to_node)
    if isinstance(ec, InflowElementConfig):
        return InflowElement(**base, ipr=ipr)
    if isinstance(ec, PipeElementConfig):
        for nid in (ec.from_node, ec.to_node):
            if nid not in node_elev:
                raise TopologyError(f"element {ec.id!r} references unknown node {nid!r}")
        geom = PipeGeometry(
            length=ec.length_m,
            diameter=ec.inner_diameter_m,
            roughness=ec.roughness_m,
            dz=node_elev[ec.to_node] - node_elev[ec.from_node],
        )
        return PipeElement(
            **base, geometry=geom, role=ec.role, overall_htc=ec.overall_htc_w_m2k,
            ambient_in=u.c_to_k(ec.ambient_temperature_inlet_c),
            ambient_out=u.c_to_k(ec.ambient_temperature_outlet_c),
            thermal_cells=ec.thermal_cells,
        )
    if isinstance(ec, ValveElementConfig):
        if not ec.supports_intermediate and ec.initial_position_pct not in (0.0, 100.0):
            raise ValueError(f"{ec.tag}: discrete valve initial position must be 0 or 100 %")
        return ValveElement(
            **base, tag=ec.tag, subtype=ec.valve_type, actuator=_actuator(ec),
            characteristic=ec.characteristic, rangeability=ec.rangeability,
            supports_intermediate=ec.supports_intermediate, available=ec.available,
            bore_diameter=ec.bore_diameter_m, loss_coefficient_open=ec.loss_coefficient_open,
            seat_leak_capacity=ec.seat_leak_area_mm2 * 1e-6, nominal_stroke_time_s=ec.nominal_stroke_time_s,
        )
    if isinstance(ec, ChokeElementConfig):
        return ChokeElement(
            **base, tag=ec.tag, actuator=_actuator(ec),
            characteristic=ec.characteristic, rangeability=ec.rangeability,
            supports_intermediate=ec.supports_intermediate, available=ec.available,
            cv_max=ec.cv_max, service=ec.service,
            seat_leak_capacity=ec.seat_leak_area_mm2 * 1e-6, nominal_stroke_time_s=ec.nominal_stroke_time_s,
        )
    if isinstance(ec, CheckValveConfig):
        return CheckValveElement(
            **base, tag=ec.tag, cracking_pressure=u.bar_to_pa_delta(ec.cracking_pressure_bar),
            capacity_open=u.cv_to_capacity(ec.cv),
        )
    raise ValueError(f"unsupported element {ec!r}")


def build_instrument(ic: InstrumentConfig, cfg: ScenarioConfig) -> Instrument:
    lo, hi = _instrument_range_si(ic)
    resp = ic.response or cfg.dynamics.default_response.get(ic.type)
    response = None
    if resp is not None:
        response = InstrumentResponse(resp.time_constant_s, resp.update_interval_s, _resolution_si(ic, resp.resolution))
    return Instrument(
        ic.tag, ic.type, ic.description, ic.node, ic.high_node, ic.low_node, lo, hi,
        element=ic.element, distance_m=ic.distance_m, chemical=ic.chemical,
        display_unit=ic.unit or ("ppm" if ic.type == "concentration" else None), response=response,
    )


def build_system(cfg: ScenarioConfig) -> BuiltSystem:
    nodes = [Node(n.id, n.name, n.elevation_m) for n in cfg.nodes]
    node_elev = {n.id: n.elevation for n in nodes}
    ipr = LinearIPR(
        p_res=u.bara_to_pa(cfg.reservoir.pressure_bara),
        j=u.pi_m3d_per_bar_to_si(cfg.reservoir.productivity_index_m3d_per_bar),
        t_res=u.c_to_k(cfg.reservoir.temperature_c),
    )
    elements: list[Element] = [build_element(ec, node_elev, ipr) for ec in cfg.elements]
    topology = SeriesTopology.build(nodes, elements, cfg.reservoir_node, cfg.boundary.node)

    # ---- branch subsystems ------------------------------------------------
    sub = cfg.subsystems
    branch_nodes: dict[str, Node] = {}
    for n in sub.nodes:
        if n.id in topology.nodes or n.id in branch_nodes:
            raise TopologyError(f"duplicate node id {n.id!r}")
        if n.zone != "production" and n.zone not in sub.fluids:
            raise TopologyError(f"node {n.id!r} uses unknown fluid zone {n.zone!r}")
        branch_nodes[n.id] = Node(n.id, n.name, n.elevation_m)
    all_elev = {**node_elev, **{k: v.elevation for k, v in branch_nodes.items()}}
    ids = {e.id for e in elements}
    branch_elements: list[Element] = []
    for ec in sub.elements:
        if ec.id in ids:
            raise TopologyError(f"duplicate element id {ec.id!r}")
        ids.add(ec.id)
        el = build_element(ec, all_elev, None)
        for nid in (el.from_node, el.to_node):
            if nid not in all_elev:
                raise TopologyError(f"element {ec.id!r} references unknown node {nid!r}")
        if el.from_node not in branch_nodes and el.to_node not in branch_nodes:
            raise TopologyError(f"branch element {ec.id!r} must connect to at least one branch node")
        branch_elements.append(el)
    for b in sub.boundaries:
        if b.node not in branch_nodes:
            raise TopologyError(f"branch boundary references unknown branch node {b.node!r}")

    tags = (
        [e.tag for e in elements if hasattr(e, "tag")]
        + [e.tag for e in branch_elements if hasattr(e, "tag")]
        + [i.tag for i in cfg.instruments]
        + [i.tag for i in sub.instruments]
    )
    if len(tags) != len(set(tags)):
        raise ValueError("component and instrument tags must be unique")

    chem_ids = {c.id for c in cfg.chemicals}
    all_nodes = set(topology.nodes) | set(branch_nodes)
    all_element_ids = ids
    instruments = []
    for ic in [*cfg.instruments, *sub.instruments]:
        for nid in (ic.node, ic.high_node, ic.low_node):
            if nid is not None and nid not in all_nodes:
                raise TopologyError(f"instrument {ic.tag} references unknown node {nid!r}")
        if ic.element is not None and ic.element not in all_element_ids:
            raise TopologyError(f"instrument {ic.tag} references unknown element {ic.element!r}")
        if ic.chemical is not None and ic.chemical not in chem_ids:
            raise TopologyError(f"instrument {ic.tag} references unknown chemical {ic.chemical!r}")
        instruments.append(build_instrument(ic, cfg))

    return BuiltSystem(
        topology=topology,
        fluid=build_fluid(cfg.fluid),
        ipr=ipr,
        p_boundary=u.bara_to_pa(cfg.boundary.pressure_bara),
        t_boundary_fluid=u.c_to_k(cfg.boundary.fluid_temperature_c),
        instruments=instruments,
        branch_nodes=branch_nodes,
        branch_elements=branch_elements,
    )
