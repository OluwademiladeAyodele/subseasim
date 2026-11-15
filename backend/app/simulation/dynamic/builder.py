"""Build the dynamic hydraulic network from a scenario.

Production path (series topology) + branch subsystems (annulus, chemical
injection, crossover) + optional radial reservoir grid are reduced to one
graph of pressure nodes and flow links (see ``network``).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from app.core import units as u
from app.models.scenario import FluidZoneConfig, PipeElementConfig, ScenarioConfig
from app.simulation.build import BuiltSystem
from app.simulation.components.elements import (
    CheckValveElement,
    Element,
    InflowElement,
    PipeElement,
    RestrictionElement,
)
from app.simulation.dynamic.network import CHECK, LINEAR, ORIFICE, PIPE, RESTRICTION_LENGTH_M, HNode, HydraulicNetwork, Link
from app.simulation.fluid_properties.constant_liquid import ConstantPropertyLiquid

PRODUCTION = "production"


@dataclass
class Zone:
    name: str
    rho: float
    mu: float
    cp: float
    beta: float
    c_f: float  # 1/Pa


@dataclass
class PipeInfo:
    element: PipeElement
    zone: str
    segments: int
    #: Hydraulic node index at each segment boundary (len = segments + 1).
    node_idx: list[int]
    #: Link index of each segment.
    link_idx: list[int]
    area: float
    hydraulic_diameter: float
    wall_compliance: float  # 1/Pa
    wave_speed: float  # m/s
    volume: float
    capacitance: float  # m3/Pa (whole pipe)


@dataclass
class ReservoirInfo:
    radii: list[float]
    node_idx: list[int]  # r_0 (sandface node) .. r_n (outer boundary)
    link_idx: list[int]
    kh: float
    k: float
    diffusivity: float  # m2/s
    pore_volume: float


@dataclass
class DynamicLayout:
    network: HydraulicNetwork
    zones: dict[str, Zone]
    pipes: dict[str, PipeInfo]
    #: element id -> link index for restrictions / check valves / inflow
    element_link: dict[str, int]
    #: topology/branch node id -> hydraulic node index
    node_index: dict[str, int]
    reservoir: ReservoirInfo | None
    production_nodes: list[str]
    branch_node_zone: dict[str, str]
    cavity_ua: dict[str, tuple[float, float]] = field(default_factory=dict)  # node -> (UA, T_amb)
    cavity_mass: dict[str, float] = field(default_factory=dict)  # node -> solid heat capacity [J/K]


def _zone_from_cfg(name: str, z: FluidZoneConfig) -> Zone:
    return Zone(name, z.density_kg_m3, u.cp_to_pas(z.viscosity_cp), z.specific_heat_j_kgk, z.thermal_expansion_1_k,
                z.compressibility_1_bar / u.PA_PER_BAR)


def production_zone(fluid: ConstantPropertyLiquid) -> Zone:
    return Zone(PRODUCTION, fluid.rho, fluid.mu, fluid.cp, fluid.beta, fluid.compressibility)


def _pipe_cfg(cfg: ScenarioConfig) -> dict[str, PipeElementConfig]:
    out = {}
    for ec in [*cfg.elements, *cfg.subsystems.elements]:
        if isinstance(ec, PipeElementConfig):
            out[ec.id] = ec
    return out


def build_dynamic_layout(cfg: ScenarioConfig, built: BuiltSystem, fluid: ConstantPropertyLiquid) -> DynamicLayout:
    dyn = cfg.dynamics
    zones: dict[str, Zone] = {PRODUCTION: production_zone(fluid)}
    for name, z in cfg.subsystems.fluids.items():
        zones[name] = _zone_from_cfg(name, z)
    pcfg = _pipe_cfg(cfg)
    node_cfg = {n.id: n for n in [*cfg.nodes, *cfg.subsystems.nodes]}
    branch_zone = {n.id: n.zone for n in cfg.subsystems.nodes}

    topo = built.topology
    nodes: list[HNode] = []
    index: dict[str, int] = {}

    def add_node(nd: HNode) -> int:
        index[nd.id] = len(nodes)
        nodes.append(nd)
        return index[nd.id]

    def zone_of(nid: str) -> str:
        return branch_zone.get(nid, PRODUCTION)

    # ---- topology & branch nodes -----------------------------------------
    for nid in topo.node_order:
        n = topo.nodes[nid]
        nc = node_cfg[nid]
        add_node(HNode(nid, n.name, n.elevation, PRODUCTION, topo=nid,
                       initial_pressure=u.bara_to_pa(nc.initial_pressure_bara) if nc.initial_pressure_bara else None))
    for nid, n in built.branch_nodes.items():
        nc = node_cfg[nid]
        add_node(HNode(nid, n.name, n.elevation, zone_of(nid), topo=nid,
                       initial_pressure=u.bara_to_pa(nc.initial_pressure_bara) if nc.initial_pressure_bara else None))

    cavity_ua: dict[str, tuple[float, float]] = {}
    cavity_mass: dict[str, float] = {}
    for nid, nd in index.items():
        nc = node_cfg.get(nid)
        if nc is not None and nc.volume_m3 > 0:
            z = zones[nodes[nd].zone]
            nodes[nd].volume += nc.volume_m3
            nodes[nd].capacitance += nc.volume_m3 * z.c_f  # rigid cavity: fluid compressibility only
        if nc is not None and nc.heat_loss_ua_w_k > 0:
            cavity_ua[nid] = (nc.heat_loss_ua_w_k, u.c_to_k(nc.ambient_temperature_c))
        if nc is not None and nc.thermal_mass_j_k > 0:
            cavity_mass[nid] = nc.thermal_mass_j_k

    # fixed-pressure boundaries
    res_i = index[topo.reservoir_node]
    nodes[res_i].fixed, nodes[res_i].p_fixed = True, built.ipr.p_res
    bnd_i = index[topo.boundary_node]
    nodes[bnd_i].fixed, nodes[bnd_i].p_fixed = True, built.p_boundary
    for b in cfg.subsystems.boundaries:
        i = index[b.node]
        nodes[i].fixed, nodes[i].p_fixed = True, u.bara_to_pa(b.pressure_bara)

    links: list[Link] = []
    pipes: dict[str, PipeInfo] = {}
    element_link: dict[str, int] = {}
    reservoir: ReservoirInfo | None = None

    def add_link(l: Link) -> int:
        links.append(l)
        return len(links) - 1

    def build_pipe(e: PipeElement) -> None:
        c = pcfg[e.id]
        zname = zone_of(e.from_node) if e.from_node in branch_zone else zone_of(e.to_node)
        z = zones[zname]
        g = e.geometry
        area = c.flow_area_m2 or g.area
        dh = g.diameter
        if c.wall_compliance_1_bar is not None:
            c_wall = c.wall_compliance_1_bar / u.PA_PER_BAR
        else:
            e_wall = c.wall_thickness_m or dh / 12.0
            c_wall = dh / (c.youngs_modulus_gpa * 1e9 * e_wall)
        nseg = c.hydraulic_segments or max(1, math.ceil(g.length / dyn.segment_length_m))
        ids = [index[e.from_node]]
        z0 = nodes[ids[0]].elevation
        z1 = nodes[index[e.to_node]].elevation
        for k in range(1, nseg):
            f = k / nseg
            ids.append(add_node(HNode(f"{e.id}#{k}", f"{e.name} @ {g.length * f:.0f} m", z0 + (z1 - z0) * f, zname)))
        ids.append(index[e.to_node])
        dl = g.length / nseg
        v_seg = area * dl
        lids = []
        for k in range(nseg):
            for j in (ids[k], ids[k + 1]):
                nodes[j].volume += v_seg / 2
                nodes[j].capacitance += v_seg / 2 * (z.c_f + c_wall)
                nodes[j].beta = z.beta
            nodes[ids[k]].pipe_positions.append((e.id, k * dl))
            lids.append(add_link(Link(
                f"{e.id}/{k}", ids[k], ids[k + 1], PIPE, e.id, segment=k,
                inertance=z.rho * dl / area, gravity_dp=z.rho * u.G * (nodes[ids[k + 1]].elevation - nodes[ids[k]].elevation),
                length=dl, diameter=dh, area=area, roughness=g.roughness, rho=z.rho, mu=z.mu,
            )))
        nodes[ids[-1]].pipe_positions.append((e.id, g.length))
        wave = 1.0 / math.sqrt(z.rho * (z.c_f + c_wall))
        pipes[e.id] = PipeInfo(e, zname, nseg, ids, lids, area, dh, c_wall, wave, area * g.length, area * g.length * (z.c_f + c_wall))

    def build_restriction(e: Element) -> None:
        zname = zone_of(e.from_node) if e.from_node in branch_zone else zone_of(e.to_node)
        z = zones[zname]
        u_i, d_i = index[e.from_node], index[e.to_node]
        dz = nodes[d_i].elevation - nodes[u_i].elevation
        if isinstance(e, CheckValveElement):
            a_eq = max(e.capacity_open, 1e-9)
            li = add_link(Link(e.id, u_i, d_i, CHECK, e.id, inertance=z.rho * RESTRICTION_LENGTH_M / a_eq,
                               gravity_dp=z.rho * u.G * dz, rho=z.rho, capacity_open=e.capacity_open,
                               cracking_pressure=e.cracking_pressure))
        else:
            assert isinstance(e, RestrictionElement)
            a_eq = max(e.capacity_at(100.0), 1e-9)
            li = add_link(Link(e.id, u_i, d_i, ORIFICE, e.id, inertance=z.rho * RESTRICTION_LENGTH_M / a_eq,
                               gravity_dp=z.rho * u.G * dz, rho=z.rho, restriction=e))
        element_link[e.id] = li

    for e in topo.path:
        if isinstance(e, InflowElement):
            continue
        if isinstance(e, PipeElement):
            build_pipe(e)
        else:
            build_restriction(e)
    for e in built.branch_elements:
        if isinstance(e, PipeElement):
            build_pipe(e)
        else:
            build_restriction(e)

    # ---- reservoir inflow ------------------------------------------------
    inflow = topo.path[0]
    assert isinstance(inflow, InflowElement)
    sand_i = index[inflow.to_node]
    prod = zones[PRODUCTION]
    rcfg = dyn.reservoir
    if rcfg is None:
        li = add_link(Link("IPR", res_i, sand_i, LINEAR, inflow.id, conductance=built.ipr.j, rho=prod.rho))
        element_link[inflow.id] = li
    else:
        rw, re_, n = rcfg.wellbore_radius_m, rcfg.drainage_radius_m, rcfg.radial_cells
        if re_ <= rw * 2:
            raise ValueError("drainage radius must exceed twice the wellbore radius")
        ln_total = math.log(re_ / rw)
        kh = built.ipr.j * prod.mu * (ln_total + rcfg.skin) / (2.0 * math.pi)
        k_perm = kh / rcfg.net_thickness_m
        ct = rcfg.total_compressibility_1_bar / u.PA_PER_BAR
        phi, h = rcfg.porosity, rcfg.net_thickness_m
        radii = [rw * (re_ / rw) ** (i / n) for i in range(n + 1)]
        # control-volume faces: geometric means
        faces = [rw] + [math.sqrt(radii[i] * radii[i + 1]) for i in range(n)] + [re_]
        ridx = [sand_i]
        elev = nodes[sand_i].elevation
        for i in range(1, n):
            ridx.append(add_node(HNode(f"RES#{i}", f"Reservoir r = {radii[i]:.1f} m", elev, "reservoir")))
        ridx.append(res_i)
        pore_total = 0.0
        for i in range(n):  # pore volume of cells 0..n-1 (outer node is fixed)
            vp = phi * h * math.pi * (faces[i + 1] ** 2 - faces[i] ** 2)
            pore_total += vp
            nodes[ridx[i]].capacitance += vp * ct
            if i > 0:
                nodes[ridx[i]].volume += vp
        rlinks = []
        for i in range(n):
            res_r = prod.mu * math.log(radii[i + 1] / radii[i]) / (2.0 * math.pi * kh)
            if i == 0:
                res_r += prod.mu * rcfg.skin / (2.0 * math.pi * kh)
            # flow direction: outer (i+1) -> inner (i)
            rlinks.append(add_link(Link(f"RES/{i}", ridx[i + 1], ridx[i], LINEAR, inflow.id, segment=i,
                                        conductance=1.0 / res_r, rho=prod.rho)))
        element_link[inflow.id] = rlinks[0]
        reservoir = ReservoirInfo(radii, ridx, rlinks, kh, k_perm, k_perm / (phi * prod.mu * ct), pore_total)

    # minimum node volume (zero-volume junctions)
    vmin = dyn.minimum_node_volume_m3
    for nd in nodes:
        if nd.fixed or nd.zone == "reservoir":
            continue
        if nd.volume < vmin:
            z = zones[nd.zone]
            nd.capacitance += (vmin - nd.volume) * z.c_f
            nd.volume = vmin
        if nd.beta == 0.0 and nd.zone in zones:
            nd.beta = zones[nd.zone].beta

    net = HydraulicNetwork(nodes, links)
    return DynamicLayout(
        network=net, zones=zones, pipes=pipes, element_link=element_link, node_index=index,
        reservoir=reservoir, production_nodes=list(topo.node_order), branch_node_zone=branch_zone, cavity_ua=cavity_ua,
        cavity_mass=cavity_mass,
    )
